"""Corpus-level replayability filters and shell-risk counts."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import re
from typing import Any

import polars as pl

from swechats.data import read_table
from swechats.replay import (
    NON_WORKSPACE_TOOLS,
    _is_read_only_bash,
    _without_quoted_strings,
)

PUSHBACK_VALUES = {"correction", "rejection"}
SUPPORTED_MUTATION_TOOLS = {"Edit", "Write", "edit", "write"}


def _json_list(value: Any) -> list[Any]:
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


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


def _commit_ok_by_session(data_dir: Path | str) -> dict[str, bool]:
    sessions = read_table("sessions", data_dir).select(
        ["session_id", "checkpoint_ids", "canonical_checkpoint_pk"]
    )
    commits = read_table("commits", data_dir).select(["checkpoint_pk", "status"])
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


def _repo_session_indices(data_dir: Path | str) -> dict[str, int]:
    sessions = (
        read_table("sessions", data_dir)
        .select(["repo_id", "session_id", "created_at"])
        .sort(["repo_id", "created_at", "session_id"])
    )
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


def _top_repos(data_dir: Path | str, limit: int) -> list[str]:
    sessions = read_table("sessions", data_dir)
    return (
        sessions.group_by("repo_id")
        .len()
        .sort("len", descending=True)
        .head(limit)
        .select("repo_id")
        .to_series()
        .to_list()
    )


def _cases_for_repos(data_dir: Path | str, repos: set[str]) -> list[dict[str, Any]]:
    conversations = (
        read_table("conversations", data_dir)
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
                "content",
                "prompt_intent",
                "prompt_pushback",
            ]
        )
        .sort(["session_id", "turn_number"])
    )
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
                        "p_content": turn.get("content"),
                    }
                )
        if turn["role"] == "user":
            last_user[session_id] = turn
        elif turn["role"] == "assistant":
            last_assistant[session_id] = turn
    return cases


def _pre_instruction_tool_rows(
    data_dir: Path | str, repos: set[str]
) -> dict[tuple[str, int], list[dict[str, Any]]]:
    tool_rows = (
        read_table("conversations", data_dir)
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
    sessions = read_table("sessions", data_dir)
    conversations = read_table("conversations", data_dir)
    session_counts = {
        row["repo_id"]: int(row["len"])
        for row in sessions.group_by("repo_id").len().to_dicts()
    }
    raw_pushback_counts = {
        row["repo_id"]: int(row["len"])
        for row in (
            conversations.filter(
                pl.col("repo_id").is_in(repos)
                & pl.col("prompt_pushback").is_in(sorted(PUSHBACK_VALUES))
                & (pl.col("role") == "user")
                & (pl.col("is_conversational") == True)
            )
            .group_by("repo_id")
            .len()
            .to_dicts()
        )
    }

    commit_ok = _commit_ok_by_session(data_dir)
    transcript_sessions = _transcript_sessions(data_dir)
    prior_index = _repo_session_indices(data_dir)
    cases = _cases_for_repos(data_dir, repo_set)
    session_created_at = {
        str(row["session_id"]): row["created_at"]
        for row in sessions.select(["session_id", "created_at"]).to_dicts()
    }
    tool_rows = (
        read_table("conversations", data_dir)
        .filter(
            pl.col("repo_id").is_in(repos)
            & (pl.col("turn_type") == "tool_use")
        )
        .select(["repo_id", "session_id", "turn_number", "tool_name", "command"])
        .sort(["session_id", "turn_number"])
    )
    tools_by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in tool_rows.to_dicts():
        tools_by_session[str(row["session_id"])].append(row)

    repo_stats: dict[str, Counter[str]] = {repo_id: Counter() for repo_id in repos}
    blocker_examples: list[dict[str, Any]] = []
    static_pool_examples: list[dict[str, Any]] = []
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

    bash_rows = conversations.filter(
        pl.col("repo_id").is_in(repos) & (pl.col("tool_name") == "Bash")
    ).select(["repo_id", "session_id", "turn_number", "bash_category", "command"])
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
    }
