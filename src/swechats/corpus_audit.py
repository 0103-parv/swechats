"""Corpus-level replayability filters and shell-risk counts."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import re
from typing import Any

import polars as pl

from swechats.data import scan_table
from swechats.native_state import (
    NATIVE_AGENT_MUTATION_TOOLS,
    parse_json_list,
    parse_json_object,
)
from swechats.replay import (
    NON_WORKSPACE_TOOLS,
    _is_read_only_bash,
    _without_quoted_strings,
)

PUSHBACK_VALUES = {"correction", "rejection"}
SUPPORTED_MUTATION_TOOLS = {"Edit", "Write", "edit", "write"}


def _collect(frame: pl.LazyFrame) -> pl.DataFrame:
    """Collect lazy parquet scans with lower memory pressure."""

    return frame.collect(engine="streaming")


def _json_list(value: Any) -> list[Any]:
    return parse_json_list(value)


def _has_heredoc(command: str) -> bool:
    return "<<" in command


def _has_write_redirect(command: str) -> bool:
    structural = _without_quoted_strings(command)
    return bool(re.search(r"(?<![<0-9])>(?![>&])|>>", structural))


def _classify_tool(row: dict[str, Any]) -> str:
    tool = str(row.get("tool_name") or "")
    if tool in NON_WORKSPACE_TOOLS:
        return "non_workspace"
    if tool in SUPPORTED_MUTATION_TOOLS:
        return "supported_mutation"
    if tool in {"Bash", "bash"}:
        command = str(row.get("command") or "")
        if _is_read_only_bash(command):
            return "bash_read_only"
        if _has_heredoc(command):
            return "bash_heredoc_blocker"
        if _has_write_redirect(command):
            return "bash_redirect_blocker"
        return "bash_other_blocker"
    return "unsupported_tool"


def _commit_ok_by_session(
    data_dir: Path | str,
    session_ids: set[str] | None = None,
) -> dict[str, bool]:
    sessions_lf = scan_table("sessions", data_dir).select(
        ["session_id", "checkpoint_ids", "canonical_checkpoint_pk"]
    )
    if session_ids is not None:
        sessions_lf = sessions_lf.filter(pl.col("session_id").is_in(sorted(session_ids)))
    sessions = _collect(sessions_lf)
    checkpoint_pks: set[str] = set()
    for row in sessions.to_dicts():
        checkpoint_pks.update(str(item) for item in _json_list(row.get("checkpoint_ids")))
        if row.get("canonical_checkpoint_pk"):
            checkpoint_pks.add(str(row["canonical_checkpoint_pk"]))
    commits_lf = scan_table("commits", data_dir).select(["checkpoint_pk", "status"])
    if checkpoint_pks:
        commits_lf = commits_lf.filter(pl.col("checkpoint_pk").is_in(sorted(checkpoint_pks)))
    else:
        commits_lf = commits_lf.head(0)
    commits = _collect(commits_lf)
    status_by_checkpoint: dict[str, list[str]] = defaultdict(list)
    for row in commits.to_dicts():
        status_by_checkpoint[str(row["checkpoint_pk"])].append(str(row["status"]))

    result: dict[str, bool] = {}
    for row in sessions.to_dicts():
        checkpoints = _json_list(row.get("checkpoint_ids"))
        if not checkpoints and row.get("canonical_checkpoint_pk"):
            checkpoints = [row["canonical_checkpoint_pk"]]
        statuses = [
            status
            for checkpoint in checkpoints
            for status in status_by_checkpoint.get(str(checkpoint), [])
        ]
        result[str(row["session_id"])] = bool(statuses) and all(
            status == "ok" for status in statuses
        )
    return result


def _transcript_sessions(data_dir: Path | str) -> set[str]:
    root = Path(data_dir) / "transcripts"
    return {path.stem for path in root.glob("*.jsonl")}


def _repo_session_indices(
    data_dir: Path | str,
    repos: set[str] | None = None,
) -> dict[str, int]:
    sessions_lf = (
        scan_table("sessions", data_dir)
        .select(["repo_id", "session_id", "created_at"])
    )
    if repos is not None:
        sessions_lf = sessions_lf.filter(pl.col("repo_id").is_in(sorted(repos)))
    sessions = _collect(sessions_lf.sort(["repo_id", "created_at", "session_id"]))
    result: dict[str, int] = {}
    current_repo: str | None = None
    index = 0
    for row in sessions.to_dicts():
        repo = str(row["repo_id"])
        if repo != current_repo:
            current_repo = repo
            index = 0
        result[str(row["session_id"])] = index
        index += 1
    return result


def _native_anchor_summaries(
    data_dir: Path | str,
    session_ids: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build lightweight native state anchor summaries keyed by session id."""

    sessions_lf = scan_table("sessions", data_dir).select(
        ["session_id", "checkpoint_ids", "canonical_checkpoint_pk"]
    )
    if session_ids is not None:
        sessions_lf = sessions_lf.filter(pl.col("session_id").is_in(sorted(session_ids)))
    sessions = _collect(sessions_lf)
    session_checkpoint_pks: dict[str, tuple[str, ...]] = {}
    checkpoint_to_sessions: dict[str, list[str]] = defaultdict(list)
    for row in sessions.to_dicts():
        checkpoint_pks = [str(item) for item in _json_list(row.get("checkpoint_ids"))]
        if row.get("canonical_checkpoint_pk"):
            checkpoint_pks.append(str(row["canonical_checkpoint_pk"]))
        unique_checkpoint_pks = tuple(dict.fromkeys(checkpoint_pks))
        session_id = str(row["session_id"])
        session_checkpoint_pks[session_id] = unique_checkpoint_pks
        for checkpoint_pk in unique_checkpoint_pks:
            checkpoint_to_sessions[checkpoint_pk].append(session_id)

    metadata_lf = scan_table("session_logs", data_dir).select(
        ["session_id", "session_metadata_raw"]
    )
    if session_ids is not None:
        metadata_lf = metadata_lf.filter(pl.col("session_id").is_in(sorted(session_ids)))
    metadata_by_session: dict[str, dict[str, Any]] = {}
    for row in _collect(metadata_lf).to_dicts():
        metadata_by_session[str(row["session_id"])] = parse_json_object(
            row.get("session_metadata_raw")
        )

    accumulators: dict[str, dict[str, Any]] = {
        session_id: {
            "status_counts": Counter(),
            "agent_change_tools": Counter(),
            "agent_change_count": 0,
            "file_attribution_entries": 0,
            "agent_version_files": 0,
            "committed_version_files": 0,
        }
        for session_id in session_checkpoint_pks
    }
    checkpoint_pks = set(checkpoint_to_sessions)
    commits_lf = scan_table("commits", data_dir).select(
        ["checkpoint_pk", "status", "agent_changes", "file_attribution"]
    )
    if checkpoint_pks:
        commits_lf = commits_lf.filter(pl.col("checkpoint_pk").is_in(sorted(checkpoint_pks)))
    else:
        commits_lf = commits_lf.head(0)
    for commit in _collect(commits_lf).to_dicts():
        session_ids_for_checkpoint = checkpoint_to_sessions.get(str(commit["checkpoint_pk"]), [])
        if not session_ids_for_checkpoint:
            continue
        status = str(commit.get("status"))
        agent_changes = [
            change
            for change in _json_list(commit.get("agent_changes"))
            if isinstance(change, dict)
        ]
        attribution_entries = [
            info
            for path, info in parse_json_object(commit.get("file_attribution")).items()
            if path != "__aggregate__" and isinstance(info, dict)
        ]
        for session_id in session_ids_for_checkpoint:
            accumulator = accumulators[session_id]
            accumulator["status_counts"][status] += 1
            accumulator["agent_change_count"] += len(agent_changes)
            for change in agent_changes:
                accumulator["agent_change_tools"][str(change.get("tool_name") or "")] += 1
            accumulator["file_attribution_entries"] += len(attribution_entries)
            accumulator["agent_version_files"] += sum(
                info.get("agent_version") is not None for info in attribution_entries
            )
            accumulator["committed_version_files"] += sum(
                info.get("committed_version") is not None for info in attribution_entries
            )

    summaries: dict[str, dict[str, Any]] = {}
    for session_id, checkpoint_pks in session_checkpoint_pks.items():
        accumulator = accumulators[session_id]
        status_counts = accumulator["status_counts"]
        agent_change_tools = accumulator["agent_change_tools"]
        agent_change_count = accumulator["agent_change_count"]
        file_attribution_entries = accumulator["file_attribution_entries"]
        agent_version_files = accumulator["agent_version_files"]
        committed_version_files = accumulator["committed_version_files"]
        metadata = metadata_by_session.get(session_id, {})
        unsupported_native_tools = tuple(
            sorted(
                tool
                for tool in agent_change_tools
                if tool not in NATIVE_AGENT_MUTATION_TOOLS
            )
        )
        has_ok_commit_anchor = status_counts["ok"] > 0
        has_agent_change_replay_log = agent_change_count > 0
        has_file_version_anchors = (
            agent_version_files > 0 or committed_version_files > 0
        )
        summaries[session_id] = {
            "checkpoint_count": len(checkpoint_pks),
            "commit_status_counts": dict(status_counts),
            "ok_commit_count": status_counts["ok"],
            "agent_change_count": agent_change_count,
            "agent_change_tool_counts": dict(agent_change_tools),
            "unsupported_native_agent_change_tools": unsupported_native_tools,
            "file_attribution_entry_count": file_attribution_entries,
            "agent_version_file_count": agent_version_files,
            "committed_version_file_count": committed_version_files,
            "has_ok_commit_anchor": has_ok_commit_anchor,
            "has_agent_change_replay_log": has_agent_change_replay_log,
            "has_file_version_anchors": has_file_version_anchors,
            "has_native_repo_visible_anchors": (
                has_ok_commit_anchor
                and has_agent_change_replay_log
                and has_file_version_anchors
            ),
            "has_transcript_boundary_metadata": any(
                metadata.get(key) not in (None, "", [])
                for key in [
                    "transcript_lines_at_start",
                    "checkpoint_transcript_start",
                    "transcript_identifier_at_start",
                    "transcript_uuid_at_start",
                ]
            ),
            "has_prompt_attributions": bool(metadata.get("prompt_attributions")),
            "has_initial_attribution": bool(metadata.get("initial_attribution")),
        }
    return summaries


def _top_repos(data_dir: Path | str, limit: int) -> list[str]:
    repos = _collect(
        scan_table("sessions", data_dir)
        .group_by("repo_id")
        .len()
        .sort("len", descending=True)
        .head(limit)
        .select("repo_id")
    )
    return repos.to_series().to_list()


def _conversation_turns_for_repos(data_dir: Path | str, repos: set[str]) -> pl.DataFrame:
    return _collect(
        scan_table("conversations", data_dir)
        .filter(
            pl.col("repo_id").is_in(sorted(repos))
            & (pl.col("is_conversational") == True)
            & pl.col("role").is_in(["user", "assistant"])
        )
        .select(
            [
                "repo_id",
                "session_id",
                "turn_id",
                "checkpoint_pk",
                "turn_number",
                "role",
                "turn_type",
                "prompt_intent",
                "prompt_pushback",
            ]
        )
        .sort(["session_id", "turn_number"])
    )


def _cases_from_conversation_turns(conversations: pl.DataFrame) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    last_user: dict[str, dict[str, Any]] = {}
    last_assistant: dict[str, dict[str, Any]] = {}
    for turn in conversations.to_dicts():
        session_id = str(turn["session_id"])
        label = turn.get("prompt_pushback")
        if turn["role"] == "user" and label in PUSHBACK_VALUES:
            instruction = last_user.get(session_id)
            action = last_assistant.get(session_id)
            if instruction and action:
                cases.append(
                    {
                        "repo_id": turn["repo_id"],
                        "session_id": session_id,
                        "case_id": f"{turn['turn_id']}:{label}",
                        "checkpoint_pk": turn["checkpoint_pk"],
                        "i_turn_number": int(instruction["turn_number"]),
                        "a_turn_number": int(action["turn_number"]),
                        "p_turn_number": int(turn["turn_number"]),
                        "prompt_intent": turn.get("prompt_intent"),
                        "prompt_pushback": label,
                        "p_content": None,
                    }
                )
        if turn["role"] == "user":
            last_user[session_id] = turn
        elif turn["role"] == "assistant":
            last_assistant[session_id] = turn
    return cases


def _cases_for_repos(data_dir: Path | str, repos: set[str]) -> list[dict[str, Any]]:
    return _cases_from_conversation_turns(_conversation_turns_for_repos(data_dir, repos))


def _pre_instruction_tool_rows(
    data_dir: Path | str, repos: set[str]
) -> dict[tuple[str, int], list[dict[str, Any]]]:
    tool_rows = _collect(
        scan_table("conversations", data_dir)
        .filter(
            pl.col("repo_id").is_in(sorted(repos))
            & (pl.col("turn_type") == "tool_use")
        )
        .select(
            [
                "repo_id",
                "session_id",
                "turn_number",
                "tool_name",
                "command",
                "file_path",
                "tool_input_json",
            ]
        )
        .sort(["session_id", "turn_number"])
    )
    by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in tool_rows.to_dicts():
        by_session[str(row["session_id"])].append(row)
    return {
        (session_id, int(row["turn_number"])): rows[: index + 1]
        for session_id, rows in by_session.items()
        for index, row in enumerate(rows)
    }


def _tools_before(
    by_session: dict[str, list[dict[str, Any]]],
    session_id: str,
    turn_number: int,
) -> list[dict[str, Any]]:
    return [
        row
        for row in by_session.get(session_id, [])
        if int(row["turn_number"]) < turn_number
    ]


def corpus_replay_audit(
    data_dir: Path | str = "data/swe-chat",
    *,
    top: int = 5,
    repo: str | None = None,
    examples: int = 8,
) -> dict[str, Any]:
    """Return replayability counts for the top repos or one selected repo."""

    repos = [repo] if repo else _top_repos(data_dir, top)
    repo_set = set(repos)
    sessions = _collect(
        scan_table("sessions", data_dir)
        .filter(pl.col("repo_id").is_in(repos))
        .select(["repo_id", "session_id", "created_at"])
    )
    session_counts = {
        row["repo_id"]: int(row["len"])
        for row in sessions.group_by("repo_id").len().to_dicts()
    }
    conversation_turns = _conversation_turns_for_repos(data_dir, repo_set)
    raw_pushback_counts = {
        row["repo_id"]: int(row["len"])
        for row in (
            conversation_turns.filter(
                pl.col("prompt_pushback").is_in(sorted(PUSHBACK_VALUES))
                & (pl.col("role") == "user")
            )
            .group_by("repo_id")
            .len()
            .to_dicts()
        )
    }

    cases = _cases_from_conversation_turns(conversation_turns)
    case_session_ids = {str(case["session_id"]) for case in cases}
    commit_ok = _commit_ok_by_session(data_dir, case_session_ids)
    native_anchors = _native_anchor_summaries(data_dir, case_session_ids)
    transcript_sessions = _transcript_sessions(data_dir)
    prior_index = _repo_session_indices(data_dir, repo_set)
    session_created_at = {
        str(row["session_id"]): row["created_at"]
        for row in sessions.select(["session_id", "created_at"]).to_dicts()
    }
    tool_rows = _collect(
        scan_table("conversations", data_dir)
        .filter(
            pl.col("repo_id").is_in(repos)
            & (pl.col("turn_type") == "tool_use")
        )
        .select(
            [
                "repo_id",
                "session_id",
                "turn_number",
                "tool_name",
                "bash_category",
                "command",
            ]
        )
        .sort(["session_id", "turn_number"])
    )
    tools_by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in tool_rows.to_dicts():
        tools_by_session[str(row["session_id"])].append(row)

    repo_stats: dict[str, Counter[str]] = {repo_id: Counter() for repo_id in repos}
    blocker_examples: list[dict[str, Any]] = []
    static_pool_examples: list[dict[str, Any]] = []
    native_pool_examples: list[dict[str, Any]] = []
    for repo_id in repos:
        repo_stats[repo_id]["sessions"] = session_counts.get(repo_id, 0)
        repo_stats[repo_id]["correction_rejection_user_turns"] = raw_pushback_counts.get(
            repo_id, 0
        )

    for case in cases:
        repo_id = str(case["repo_id"])
        session_id = str(case["session_id"])
        stats = repo_stats[repo_id]
        stats["iap_cases"] += 1
        if prior_index.get(session_id, 0) > 0:
            stats["has_prior_repo_memory"] += 1
        if case["i_turn_number"] <= 1:
            stats["first_prompt_boundary"] += 1
        if commit_ok.get(session_id, False):
            stats["session_commit_mapping_ok"] += 1
        if session_id in transcript_sessions:
            stats["native_transcript_present"] += 1
        native = native_anchors.get(session_id, {})
        if native.get("has_ok_commit_anchor"):
            stats["native_ok_commit_anchor"] += 1
        if native.get("has_agent_change_replay_log"):
            stats["native_agent_change_replay_log"] += 1
        if native.get("has_file_version_anchors"):
            stats["native_file_version_anchors"] += 1
        if native.get("has_native_repo_visible_anchors"):
            stats["native_repo_visible_anchors"] += 1
        if native.get("has_transcript_boundary_metadata"):
            stats["native_transcript_boundary_metadata"] += 1
        if native.get("has_prompt_attributions"):
            stats["native_prompt_attributions"] += 1

        before = _tools_before(tools_by_session, session_id, int(case["i_turn_number"]))
        if not before:
            stats["zero_pre_i_tool_calls"] += 1
        classifications = [_classify_tool(row) for row in before]
        counts = Counter(classifications)
        for key, value in counts.items():
            stats[f"pre_i_{key}"] += value
        if any(row.get("tool_name") == "Bash" for row in before):
            stats["cases_with_pre_i_bash"] += 1
        if any(classification.startswith("bash_") and classification.endswith("blocker") for classification in classifications):
            stats["cases_with_pre_i_bash_blocker"] += 1
        if counts["bash_heredoc_blocker"]:
            stats["cases_with_pre_i_bash_heredoc"] += 1
        if counts["unsupported_tool"]:
            stats["cases_with_pre_i_unsupported_tool"] += 1
        if counts["supported_mutation"]:
            stats["cases_with_pre_i_supported_mutation"] += 1

        static_gate_w = (
            counts["unsupported_tool"] == 0
            and counts["bash_heredoc_blocker"] == 0
            and counts["bash_redirect_blocker"] == 0
            and counts["bash_other_blocker"] == 0
        )
        prereq_static = (
            static_gate_w
            and commit_ok.get(session_id, False)
            and session_id in transcript_sessions
            and prior_index.get(session_id, 0) > 0
        )
        prereq_native_repo_visible = (
            bool(native.get("has_native_repo_visible_anchors"))
            and session_id in transcript_sessions
            and prior_index.get(session_id, 0) > 0
        )
        if static_gate_w:
            stats["static_gate_w_classifiable"] += 1
        if prereq_static:
            stats["static_reconstructed_candidate_pool"] += 1
            if len(static_pool_examples) < examples:
                static_pool_examples.append(
                    {
                        "repo_id": repo_id,
                        "session_id": session_id,
                        "session_created_at": str(session_created_at.get(session_id)),
                        "p_turn_number": case["p_turn_number"],
                        "i_turn_number": case["i_turn_number"],
                        "prompt_pushback": case["prompt_pushback"],
                        "prompt_intent": case["prompt_intent"],
                        "zero_pre_i_tool_calls": not before,
                        "pre_i_tool_calls": len(before),
                        "p_content": case["p_content"],
                    }
                )
        if prereq_native_repo_visible:
            stats["native_repo_visible_candidate_pool"] += 1
            if not static_gate_w:
                stats["native_pool_with_gate_w_blocker"] += 1
            if native.get("has_transcript_boundary_metadata"):
                stats["native_pool_with_boundary_metadata"] += 1
            if len(native_pool_examples) < examples:
                native_pool_examples.append(
                    {
                        "repo_id": repo_id,
                        "session_id": session_id,
                        "session_created_at": str(session_created_at.get(session_id)),
                        "p_turn_number": case["p_turn_number"],
                        "i_turn_number": case["i_turn_number"],
                        "prompt_pushback": case["prompt_pushback"],
                        "prompt_intent": case["prompt_intent"],
                        "static_gate_w_classifiable": static_gate_w,
                        "pre_i_tool_calls": len(before),
                        "native_ok_commit_count": native.get("ok_commit_count", 0),
                        "native_agent_change_count": native.get(
                            "agent_change_count", 0
                        ),
                        "native_file_attribution_entries": native.get(
                            "file_attribution_entry_count", 0
                        ),
                        "has_transcript_boundary_metadata": native.get(
                            "has_transcript_boundary_metadata", False
                        ),
                        "p_content": case["p_content"],
                    }
                )

        if len(blocker_examples) < examples and not static_gate_w:
            blocker = next(
                (
                    row
                    for row, classification in zip(before, classifications, strict=False)
                    if classification
                    in {
                        "bash_heredoc_blocker",
                        "bash_redirect_blocker",
                        "bash_other_blocker",
                        "unsupported_tool",
                    }
                ),
                None,
            )
            if blocker:
                blocker_examples.append(
                    {
                        "repo_id": repo_id,
                        "session_id": session_id,
                        "p_turn_number": case["p_turn_number"],
                        "tool_turn_number": blocker["turn_number"],
                        "tool_name": blocker["tool_name"],
                        "classification": _classify_tool(blocker),
                        "command": blocker.get("command"),
                    }
                )

    bash_rows = tool_rows.filter(pl.col("tool_name") == "Bash")
    bash_corpus = Counter()
    heredoc_by_repo = Counter()
    heredoc_examples: list[dict[str, Any]] = []
    for row in bash_rows.to_dicts():
        command = str(row.get("command") or "")
        bash_corpus["bash_tool_calls"] += 1
        category = row.get("bash_category")
        if category:
            bash_corpus[f"bash_category:{category}"] += 1
        if _is_read_only_bash(command):
            bash_corpus["read_only_by_current_classifier"] += 1
        else:
            bash_corpus["blocked_by_current_classifier"] += 1
        if _has_heredoc(command):
            bash_corpus["commands_with_heredoc"] += 1
            heredoc_by_repo[str(row["repo_id"])] += 1
            if len(heredoc_examples) < examples:
                heredoc_examples.append(
                    {
                        "repo_id": row["repo_id"],
                        "session_id": row["session_id"],
                        "turn_number": row["turn_number"],
                        "bash_category": row.get("bash_category"),
                        "command": command,
                    }
                )
        if _has_write_redirect(command):
            bash_corpus["commands_with_write_redirect"] += 1

    return {
        "schema_version": "corpus-replay-audit-v1",
        "filters": [
            "repo selected from top session counts unless --repo is provided",
            "P is conversational user prompt with prompt_pushback in correction/rejection",
            "I/A/P are resolvable as previous user instruction, previous assistant action, pushback",
            "memory source requires at least one prior same-repo session",
            "session commit mapping must exist and all statuses must be ok",
            "native transcript file must exist",
            "static Gate W requires every pre-I tool call to be non-workspace, supported Edit/Write mutation, or Bash proven read-only by current classifier",
            "native repo-visible pool requires transcript, prior same-repo memory, ok commit anchor, structured agent_changes, and file_attribution file-version anchors; it does not claim exact mid-turn worktree equality",
        ],
        "repos": repos,
        "repo_summary": [
            {"repo_id": repo_id, **dict(repo_stats[repo_id])} for repo_id in repos
        ],
        "bash_corpus": dict(bash_corpus),
        "heredoc_by_repo": dict(heredoc_by_repo),
        "heredoc_examples": heredoc_examples,
        "blocker_examples": blocker_examples,
        "static_pool_examples": static_pool_examples,
        "native_pool_examples": native_pool_examples,
    }
