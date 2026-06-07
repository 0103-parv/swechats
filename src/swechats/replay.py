"""Fail-closed replay audits and counterfactual case bundles."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import stat
import subprocess
from typing import Any

import polars as pl

from swechats.data import read_table
from swechats.paths import SweChatPaths


FILE_MUTATION_TOOLS = {
    "Edit",
    "MultiEdit",
    "NotebookEdit",
    "Write",
    "apply_patch",
}
NON_WORKSPACE_TOOLS = {
    "Agent",
    "AskUserQuestion",
    "EnterPlanMode",
    "ExitPlanMode",
    "Glob",
    "Grep",
    "LS",
    "LSP",
    "Read",
    "Skill",
    "Task",
    "TaskCreate",
    "TaskList",
    "TaskOutput",
    "TaskStop",
    "TaskUpdate",
    "ToolSearch",
    "TodoWrite",
    "WebFetch",
    "WebSearch",
    "glob",
    "grep",
    "read",
    "mcp__linear-server__create_comment",
    "mcp__linear-server__create_issue",
    "mcp__linear-server__get_issue",
    "mcp__linear-server__list_issues",
    "mcp__linear-server__list_projects",
    "mcp__linear-server__update_issue",
    "mcp__plugin_entire-engineering_context7__query-docs",
    "mcp__plugin_entire-engineering_pw__browser_evaluate",
    "mcp__plugin_entire-engineering_pw__browser_run_code",
    "mcp__plugin_entire-engineering_pw__browser_take_screenshot",
}
READ_ONLY_BASH_PREFIXES = (
    "cat ",
    "find ",
    "gh pr view ",
    "grep ",
    "git branch ",
    "git diff ",
    "git log ",
    "git ls-files",
    "git rev-parse ",
    "git show ",
    "git status",
    "git tag ",
    "head ",
    "ls ",
    "pwd",
    "rg ",
    "tail ",
    "wc ",
    "which ",
)


@dataclass(frozen=True)
class EvalCase:
    """One correction/rejection case at the rerun boundary before A."""

    case_id: str
    repo_id: str
    session_id: str
    checkpoint_pk: str
    instruction_turn_id: str
    instruction_turn_number: int
    instruction: str
    original_action_turn_id: str
    original_action_turn_number: int
    original_action: str
    pushback_turn_id: str
    pushback_turn_number: int
    pushback: str
    pushback_label: str


@dataclass(frozen=True)
class TranscriptPrefix:
    """Exact native transcript bytes through the rerun instruction."""

    source_path: Path
    target_line_index: int
    line_count: int
    sha256: str
    full_transcript_sha256: str
    lines: tuple[bytes, ...]


def _one_row(frame: pl.DataFrame, description: str) -> dict[str, Any]:
    rows = frame.to_dicts()
    if len(rows) != 1:
        raise ValueError(f"Expected one {description}, found {len(rows)}.")
    return rows[0]


def case_for_pushback(
    session_id: str,
    pushback_turn_number: int,
    data_dir: Path | str = "data/swe-chat",
) -> EvalCase:
    """Resolve I/A/P for one conversational pushback turn."""

    turns = (
        read_table("conversations", data_dir)
        .filter(
            (pl.col("session_id") == session_id)
            & (pl.col("is_conversational") == True)
            & pl.col("role").is_in(["user", "assistant"])
        )
        .sort("turn_number")
    )
    pushback = _one_row(
        turns.filter(pl.col("turn_number") == pushback_turn_number),
        "pushback turn",
    )
    label = pushback.get("prompt_pushback")
    if pushback["role"] != "user" or label not in {"correction", "rejection"}:
        raise ValueError(
            f"Turn {pushback_turn_number} is not a correction/rejection user turn."
        )

    before_pushback = turns.filter(pl.col("turn_number") < pushback_turn_number)
    action = _one_row(
        before_pushback.filter(pl.col("role") == "assistant").tail(1),
        "preceding assistant action",
    )
    instruction = _one_row(
        before_pushback.filter(
            (pl.col("role") == "user")
            & (pl.col("turn_number") < action["turn_number"])
        ).tail(1),
        "preceding user instruction",
    )

    return EvalCase(
        case_id=f"{pushback['turn_id']}:{label}",
        repo_id=str(pushback["repo_id"]),
        session_id=session_id,
        checkpoint_pk=str(pushback["checkpoint_pk"]),
        instruction_turn_id=str(instruction["turn_id"]),
        instruction_turn_number=int(instruction["turn_number"]),
        instruction=str(instruction["content"]),
        original_action_turn_id=str(action["turn_id"]),
        original_action_turn_number=int(action["turn_number"]),
        original_action=str(action["content"]),
        pushback_turn_id=str(pushback["turn_id"]),
        pushback_turn_number=pushback_turn_number,
        pushback=str(pushback["content"]),
        pushback_label=str(label),
    )


def _message_text(event: dict[str, Any]) -> str | None:
    if event.get("type") != "user":
        return None
    content = event.get("message", {}).get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None

    text_blocks = [
        block.get("text")
        for block in content
        if isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    ]
    return "\n".join(text_blocks) if text_blocks else None


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def transcript_prefix(
    case: EvalCase,
    data_dir: Path | str = "data/swe-chat",
) -> TranscriptPrefix:
    """Return exact native transcript bytes through I, before original A."""

    path = SweChatPaths.from_root(data_dir).require_transcript(case.session_id)
    raw_lines = tuple(path.read_bytes().splitlines(keepends=True))
    target_timestamp = _one_row(
        read_table("conversations", data_dir).filter(
            pl.col("turn_id") == case.instruction_turn_id
        ),
        "instruction turn",
    )["timestamp"]

    content_matches: list[int] = []
    timestamp_matches: list[int] = []
    for index, raw_line in enumerate(raw_lines):
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if _message_text(event) != case.instruction:
            continue
        content_matches.append(index)
        raw_timestamp = _parse_timestamp(event.get("timestamp"))
        if raw_timestamp == target_timestamp:
            timestamp_matches.append(index)

    matches = timestamp_matches or content_matches
    if len(matches) != 1:
        raise ValueError(
            "Could not uniquely match instruction in native transcript: "
            f"{len(timestamp_matches)} timestamp matches, "
            f"{len(content_matches)} content matches."
        )

    target_index = matches[0]
    prefix_lines = raw_lines[: target_index + 1]
    return TranscriptPrefix(
        source_path=path,
        target_line_index=target_index,
        line_count=len(prefix_lines),
        sha256=sha256(b"".join(prefix_lines)).hexdigest(),
        full_transcript_sha256=sha256(b"".join(raw_lines)).hexdigest(),
        lines=prefix_lines,
    )


def history_prefix(
    case: EvalCase,
    data_dir: Path | str = "data/swe-chat",
) -> TranscriptPrefix:
    """Return native history before I; I itself is submitted by the candidate run."""

    through_instruction = transcript_prefix(case, data_dir)
    target_event = json.loads(through_instruction.lines[-1])
    target_uuid = target_event.get("uuid")
    history_lines: list[bytes] = []
    for raw_line in through_instruction.lines[:-1]:
        event = json.loads(raw_line)
        if (
            event.get("type") == "file-history-snapshot"
            and event.get("messageId") == target_uuid
        ):
            continue
        history_lines.append(raw_line)
    return TranscriptPrefix(
        source_path=through_instruction.source_path,
        target_line_index=through_instruction.target_line_index,
        line_count=len(history_lines),
        sha256=sha256(b"".join(history_lines)).hexdigest(),
        full_transcript_sha256=through_instruction.full_transcript_sha256,
        lines=tuple(history_lines),
    )


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


def audit_replay(
    case: EvalCase,
    data_dir: Path | str = "data/swe-chat",
) -> dict[str, Any]:
    """Audit the maximum replay fidelity supported by published artifacts.

    This deliberately does not infer exactness from a successful commit mapping.
    A commit identifies a Git state, but does not prove the worktree, untracked
    files, index, or other environmental state at the rerun boundary.
    """

    session = _one_row(
        read_table("sessions", data_dir).filter(pl.col("session_id") == case.session_id),
        "session",
    )
    prefix: TranscriptPrefix | None = None
    transcript_error: str | None = None
    try:
        prefix = transcript_prefix(case, data_dir)
    except (FileNotFoundError, ValueError) as exc:
        transcript_error = str(exc)
    conversations = read_table("conversations", data_dir).filter(
        pl.col("session_id") == case.session_id
    )
    before_instruction = conversations.filter(
        pl.col("turn_number") < case.instruction_turn_number
    )
    prior_user_prompts = before_instruction.filter(
        (pl.col("role") == "user") & (pl.col("turn_type") == "user_prompt")
    ).height
    mutation_rows = before_instruction.filter(
        (pl.col("turn_type") == "tool_use")
        & pl.col("tool_name").is_in(sorted(FILE_MUTATION_TOOLS))
    )
    bash_rows = before_instruction.filter(
        (pl.col("turn_type") == "tool_use") & (pl.col("tool_name") == "Bash")
    )

    checkpoint_pks = _json_list(session.get("checkpoint_ids"))
    if not checkpoint_pks and session.get("canonical_checkpoint_pk"):
        checkpoint_pks = [session["canonical_checkpoint_pk"]]
    commits = read_table("commits", data_dir).filter(
        pl.col("checkpoint_pk").is_in(checkpoint_pks)
    )
    commit_rows = commits.select(
        ["commit_sha", "checkpoint_pk", "status", "commit_message"]
    ).to_dicts()
    statuses = sorted({str(row["status"]) for row in commit_rows})

    blockers = [
        "No published temporary shadow checkpoint exists at the instruction boundary.",
        "Published artifacts do not prove the original worktree/index/untracked-file state.",
        "Published artifacts do not capture the original dependency, process, service, or OS state.",
    ]
    if transcript_error:
        blockers.append(f"Native transcript prefix is not certifiable: {transcript_error}")
    warnings: list[str] = []
    if prior_user_prompts:
        warnings.append(
            "This is an intermediate prompt; reconstructing it requires replaying "
            "earlier actions and any out-of-band human edits."
        )
    if mutation_rows.height:
        warnings.append(
            f"{mutation_rows.height} explicit file-mutation tool calls occur before I."
        )
    if bash_rows.height:
        warnings.append(
            f"{bash_rows.height} Bash calls occur before I; their side effects need "
            "case-specific classification."
        )

    if transcript_error:
        tier = "R"
    elif not commit_rows:
        tier = "R"
        blockers.append("No commit mapping is available for the session checkpoints.")
    elif any(status != "ok" for status in statuses):
        tier = "R"
        blockers.append(f"Commit mapping contains non-ok statuses: {statuses}.")
    else:
        tier = "C"

    return {
        "schema_version": "replay-audit-v1",
        "case": asdict(case),
        "fork_boundary": {
            "definition": "after instruction I, before original action A",
            "instruction_turn_number": case.instruction_turn_number,
            "is_first_user_prompt": prior_user_prompts == 0,
        },
        "published_evidence": {
            "native_transcript_prefix": {
                "available": prefix is not None,
                "source_path": str(prefix.source_path) if prefix else None,
                "line_count": prefix.line_count if prefix else None,
                "target_line_index": prefix.target_line_index if prefix else None,
                "sha256": prefix.sha256 if prefix else None,
                "full_transcript_sha256": (
                    prefix.full_transcript_sha256 if prefix else None
                ),
                "error": transcript_error,
            },
            "temporary_shadow_snapshot": {
                "available": False,
                "reason": "Entire shadow branches are local, temporary, and not in SWE-chat.",
            },
            "session": {
                "agent": session.get("agent"),
                "strategy": session.get("strategy"),
                "branch": session.get("branch"),
                "canonical_checkpoint_pk": session.get("canonical_checkpoint_pk"),
                "checkpoint_ids": checkpoint_pks,
            },
            "commit_rows": commit_rows,
            "pre_fork_explicit_file_mutations": mutation_rows.height,
            "pre_fork_bash_calls": bash_rows.height,
        },
        "fidelity": {
            "maximum_supported_tier": tier,
            "primary_benchmark_eligible": False,
            "tiers": {
                "S": "Exact native snapshot at fork boundary.",
                "A": "Exact base commit plus proof of a clean worktree at boundary.",
                "B": "Replay from exact base, validated against independent state anchors.",
                "C": "Approximate reconstruction; exploratory only.",
                "R": "Reject because required published evidence is missing or inconsistent.",
            },
            "blockers": blockers,
            "warnings": warnings,
        },
        "cache_contract": {
            "provider_prompt_cache_is_semantic_state": False,
            "treatment": "Do not clone it; hold transcript/model/config constant instead.",
        },
    }


def judge_rubric(case: EvalCase) -> dict[str, Any]:
    """Build the narrow binary correction-recurrence rubric."""

    return {
        "schema_version": "correction-recurrence-judge-v1",
        "claim": "Measure whether the candidate repeats the flaw described by P.",
        "instruction": case.instruction,
        "original_action_context": case.original_action,
        "original_trajectory_context": "original-trajectory.jsonl",
        "pushback_flaw_description": case.pushback,
        "question": (
            "Does the candidate response or resulting diff still exhibit the "
            "specific flaw described by the user's pushback?"
        ),
        "labels": {
            "1": "passes_flaw_avoided",
            "0": "fails_flaw_recurs",
        },
        "requirements": [
            "Return a binary label and concrete evidence.",
            "Use downstream context only to interpret intent, not as a literal checklist.",
            "Abstain outside scoring if the candidate lacks enough observable evidence.",
        ],
    }


def original_trajectory(
    case: EvalCase,
    data_dir: Path | str = "data/swe-chat",
) -> list[dict[str, Any]]:
    """Return normalized rows after I and before P for judge calibration."""

    frame = (
        read_table("conversations", data_dir)
        .filter(
            (pl.col("session_id") == case.session_id)
            & (pl.col("turn_number") > case.instruction_turn_number)
            & (pl.col("turn_number") < case.pushback_turn_number)
        )
        .sort("turn_number")
    )
    columns = [
        column
        for column in [
            "turn_id",
            "turn_number",
            "role",
            "turn_type",
            "is_conversational",
            "content",
            "tool_name",
            "tool_call_id",
            "file_path",
            "command",
            "tool_input_json",
            "timestamp",
        ]
        if column in frame.columns
    ]
    return frame.select(columns).to_dicts()


def write_case_bundle(
    case: EvalCase,
    output: Path,
    data_dir: Path | str = "data/swe-chat",
) -> Path:
    """Write immutable history, audit, and judge inputs for one case."""

    output.mkdir(parents=True, exist_ok=True)
    prefix = transcript_prefix(case, data_dir)
    history = history_prefix(case, data_dir)
    audit = audit_replay(case, data_dir)

    (output / "history-prefix.jsonl").write_bytes(b"".join(history.lines))
    (output / "transcript-through-instruction.jsonl").write_bytes(b"".join(prefix.lines))
    (output / "instruction.txt").write_text(case.instruction + "\n", encoding="utf-8")
    (output / "original-action.txt").write_text(
        case.original_action + "\n", encoding="utf-8"
    )
    with (output / "original-trajectory.jsonl").open("w", encoding="utf-8") as handle:
        for row in original_trajectory(case, data_dir):
            handle.write(json.dumps(row, default=str, ensure_ascii=False) + "\n")
    (output / "pushback.txt").write_text(case.pushback + "\n", encoding="utf-8")
    (output / "judge-rubric.json").write_text(
        json.dumps(judge_rubric(case), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output / "run-spec.json").write_text(
        json.dumps(
            {
                "schema_version": "counterfactual-run-spec-v1",
                "case_id": case.case_id,
                "fork_boundary": "after instruction I, before original action A",
                "candidate_invocation": "resume history-prefix.jsonl, then submit instruction.txt",
                "arms": {
                    "cold": {"learned_repo_memory": False},
                    "warm": {"learned_repo_memory": True},
                },
                "must_match_between_arms": [
                    "pre-intervention repository hash",
                    "native history-prefix hash",
                    "model and model configuration",
                    "system instructions and tools",
                    "permissions and working directory",
                    "dependency, service, and environment configuration",
                ],
                "provider_prompt_cache": "nonsemantic_not_forked",
                "judge_rubric": "judge-rubric.json",
                "original_trajectory_for_calibration": "original-trajectory.jsonl",
                "candidate_observation_contract": [
                    "final assistant response",
                    "resulting repository diff",
                    "tool/action trajectory",
                ],
                "unresolved_before_execution": [
                    "model",
                    "model configuration",
                    "runner/system/tool configuration",
                    "environment variables and services",
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (output / "manifest.json").write_text(
        json.dumps(audit, indent=2, default=str, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output


def directory_digest(root: Path) -> str:
    """Hash relative paths, executable bits, symlinks, and file bytes."""

    digest = sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if relative == ".git" or relative.startswith(".git/"):
            continue
        mode = path.lstat().st_mode
        if path.is_symlink():
            kind = "symlink"
            payload = path.readlink().as_posix().encode()
        elif path.is_file():
            kind = "file"
            payload = path.read_bytes()
        elif path.is_dir():
            kind = "dir"
            payload = b""
        else:
            raise ValueError(f"Unsupported filesystem entry in fork: {path}")
        executable = bool(mode & stat.S_IXUSR)
        digest.update(f"{kind}\0{relative}\0{int(executable)}\0".encode())
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def _run_git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def git_state(repo: Path) -> dict[str, Any]:
    """Return path-independent Git state required by the candidate task."""

    top_level = Path(_run_git(repo, "rev-parse", "--show-toplevel").strip()).resolve()
    if top_level != repo.resolve():
        raise RuntimeError(
            f"Fork is not its own Git repository: expected {repo.resolve()}, "
            f"Git resolved {top_level}."
        )
    head = _run_git(repo, "rev-parse", "HEAD").strip()
    tree = _run_git(repo, "rev-parse", "HEAD^{tree}").strip()
    status = _run_git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    index = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "--stage", "-z"],
        check=True,
        capture_output=True,
    ).stdout
    refs = _run_git(repo, "show-ref")
    return {
        "top_level": str(top_level),
        "head": head,
        "head_tree": tree,
        "status": status,
        "index_sha256": sha256(index).hexdigest(),
        "refs_sha256": sha256(refs.encode()).hexdigest(),
        "tag_count": len(_run_git(repo, "tag").splitlines()),
    }


def _clone_at_ref(source: Path, destination: Path, resolved_commit: str) -> None:
    subprocess.run(
        [
            "git",
            "clone",
            "--quiet",
            "--no-checkout",
            "--no-hardlinks",
            str(source.resolve()),
            str(destination),
        ],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(destination), "checkout", "--quiet", "--detach", resolved_commit],
        check=True,
    )


def _without_quoted_strings(command: str) -> str:
    result: list[str] = []
    quote: str | None = None
    escaped = False
    for char in command:
        if escaped:
            escaped = False
            if quote is None:
                result.append(char)
            else:
                result.append(" ")
            continue
        if char == "\\":
            escaped = True
            result.append(" " if quote else char)
            continue
        if quote:
            if char == quote:
                quote = None
            result.append(" ")
            continue
        if char in {"'", '"'}:
            quote = char
            result.append(" ")
            continue
        result.append(char)
    return "".join(result)


def _split_unquoted_pipe(command: str) -> list[str]:
    segments: list[str] = []
    start = 0
    quote: str | None = None
    escaped = False
    for index, char in enumerate(command):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char == "|":
            segments.append(command[start:index])
            start = index + 1
    segments.append(command[start:])
    return segments


def _is_read_only_bash(command: str) -> bool:
    normalized = command.strip()
    structural = _without_quoted_strings(normalized)
    if any(token in structural for token in ["&&", "||", ";", "\n", ">>", "<<"]):
        return False
    if re.search(r"(?<![0-9])>(?!&)", structural):
        return False
    segments = [segment.strip() for segment in _split_unquoted_pipe(normalized)]
    for index, segment in enumerate(segments):
        segment = segment.replace("2>/dev/null", "").strip()
        if index > 0 and segment.startswith(("sort", "head", "tail", "grep", "rg")):
            continue
        if not segment.startswith(READ_ONLY_BASH_PREFIXES):
            return False
    return True


def _mapped_path(original: str, original_root: Path, target_root: Path) -> Path:
    path = Path(original)
    try:
        relative = path.relative_to(original_root)
    except ValueError as exc:
        raise ValueError(f"Observed path is outside historical workspace: {path}") from exc
    target = target_root / relative
    if not target.resolve(strict=False).is_relative_to(target_root.resolve()):
        raise ValueError(f"Mapped path escapes target workspace: {target}")
    return target


def _apply_edit(path: Path, tool_input: dict[str, Any]) -> tuple[str, str]:
    before = path.read_text(encoding="utf-8")
    old = tool_input["old_string"]
    new = tool_input["new_string"]
    count = before.count(old)
    replace_all = bool(tool_input.get("replace_all", False))
    if count == 0:
        raise ValueError(f"Edit precondition missing in {path}")
    if not replace_all and count != 1:
        raise ValueError(f"Edit precondition is ambiguous in {path}: {count} matches")
    after = before.replace(old, new, -1 if replace_all else 1)
    path.write_text(after, encoding="utf-8")
    return sha256(before.encode()).hexdigest(), sha256(after.encode()).hexdigest()


def replay_observed_agent_actions(
    case: EvalCase,
    workspace: Path,
    data_dir: Path | str = "data/swe-chat",
) -> dict[str, Any]:
    """Replay every observed pre-boundary agent workspace mutation or reject."""

    prefix = history_prefix(case, data_dir)
    cwds = {
        event["cwd"]
        for raw_line in prefix.lines
        for event in [json.loads(raw_line)]
        if isinstance(event.get("cwd"), str)
    }
    if len(cwds) != 1:
        raise ValueError(f"Expected one historical cwd, found {sorted(cwds)}")
    original_root = Path(next(iter(cwds)))

    calls = (
        read_table("conversations", data_dir)
        .filter(
            (pl.col("session_id") == case.session_id)
            & (pl.col("turn_number") < case.instruction_turn_number)
            & (pl.col("turn_type") == "tool_use")
        )
        .sort("turn_number")
    )
    ledger: list[dict[str, Any]] = []
    for row in calls.to_dicts():
        tool = str(row["tool_name"])
        record: dict[str, Any] = {
            "turn_number": row["turn_number"],
            "tool_call_id": row["tool_call_id"],
            "tool_name": tool,
        }
        if tool in NON_WORKSPACE_TOOLS:
            record["classification"] = "non_workspace"
        elif tool in {"Bash", "bash"}:
            command = str(row.get("command") or "")
            if not _is_read_only_bash(command):
                raise ValueError(
                    f"Unsupported or potentially mutating Bash at turn "
                    f"{row['turn_number']}: {command}"
                )
            record.update({"classification": "read_only", "command": command})
        elif tool in {"Edit", "edit"}:
            tool_input = json.loads(row["tool_input_json"])
            target = _mapped_path(tool_input["file_path"], original_root, workspace)
            before, after = _apply_edit(target, tool_input)
            record.update(
                {
                    "classification": "replayed_mutation",
                    "relative_path": target.relative_to(workspace).as_posix(),
                    "before_sha256": before,
                    "after_sha256": after,
                }
            )
        elif tool in {"Write", "write"}:
            tool_input = json.loads(row["tool_input_json"])
            target = _mapped_path(tool_input["file_path"], original_root, workspace)
            before = target.read_bytes() if target.exists() else b""
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(tool_input["content"], encoding="utf-8")
            record.update(
                {
                    "classification": "replayed_mutation",
                    "relative_path": target.relative_to(workspace).as_posix(),
                    "before_sha256": sha256(before).hexdigest(),
                    "after_sha256": sha256(target.read_bytes()).hexdigest(),
                }
            )
        else:
            raise ValueError(
                f"Unsupported observed tool before boundary at turn "
                f"{row['turn_number']}: {tool}"
            )
        ledger.append(record)

    return {
        "schema_version": "observed-agent-replay-v1",
        "historical_workspace_root": str(original_root),
        "target_workspace_root": str(workspace.resolve()),
        "unknown_human_changes_included": False,
        "observed_tool_calls": len(ledger),
        "replayed_mutations": sum(
            record["classification"] == "replayed_mutation" for record in ledger
        ),
        "ledger": ledger,
    }


def rebase_transcript(
    prefix: TranscriptPrefix,
    historical_root: Path,
    target_root: Path,
    output: Path,
) -> dict[str, Any]:
    """Rebase path-bound native history into an isolated workspace."""

    original = b"".join(prefix.lines)
    source = str(historical_root).encode()
    target = str(target_root.resolve()).encode()
    replacements = original.count(source)
    if replacements == 0:
        raise ValueError(f"Historical root is absent from transcript: {historical_root}")
    rebased = original.replace(source, target)
    if source != target and source in rebased:
        raise RuntimeError("Historical workspace path remains after transcript rebasing.")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rebased)
    return {
        "source_sha256": prefix.sha256,
        "rebased_sha256": sha256(rebased).hexdigest(),
        "historical_root": str(historical_root),
        "target_root": str(target_root.resolve()),
        "replacement_count": replacements,
        "output": str(output),
    }


def materialize_fork_pair(
    bundle: Path,
    repo: Path,
    base_ref: str,
    *,
    allow_exploratory: bool = False,
    memory: Path | None = None,
    memory_target: Path = Path("AGENTS.md"),
    append_memory: bool = False,
    data_dir: Path | str = "data/swe-chat",
) -> dict[str, Any]:
    """Create byte-identical cold/warm trees, then optionally inject warm memory."""

    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    eligible = bool(manifest["fidelity"]["primary_benchmark_eligible"])
    if not eligible and not allow_exploratory:
        raise ValueError(
            "Replay audit is not primary-benchmark eligible. "
            "Pass --allow-exploratory only for an explicitly labeled smoke test."
        )

    forks = bundle / "forks"
    if forks.exists():
        raise FileExistsError(f"Fork output already exists: {forks}")

    cold = forks / "cold"
    warm = forks / "warm"
    forks.mkdir(parents=True)
    resolved_commit = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", f"{base_ref}^{{commit}}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _clone_at_ref(repo, cold, resolved_commit)
    _clone_at_ref(repo, warm, resolved_commit)
    case = EvalCase(**manifest["case"])
    cold_replay = replay_observed_agent_actions(case, cold, data_dir)
    warm_replay = replay_observed_agent_actions(case, warm, data_dir)
    if cold_replay["ledger"] != warm_replay["ledger"]:
        raise RuntimeError("Cold and warm observed-agent replay ledgers differ.")
    prefix = history_prefix(case, data_dir)
    reentry = forks / "reentry"
    historical_root = Path(cold_replay["historical_workspace_root"])
    cold_transcript = rebase_transcript(
        prefix, historical_root, cold, reentry / "cold.jsonl"
    )
    warm_transcript = rebase_transcript(
        prefix, historical_root, warm, reentry / "warm.jsonl"
    )

    cold_pre = directory_digest(cold)
    warm_pre = directory_digest(warm)
    if cold_pre != warm_pre:
        raise RuntimeError("Cold and warm pre-intervention fork hashes differ.")
    cold_git = git_state(cold)
    warm_git = git_state(warm)
    semantic_git_keys = {
        "head",
        "head_tree",
        "status",
        "index_sha256",
        "refs_sha256",
        "tag_count",
    }
    if any(cold_git[key] != warm_git[key] for key in semantic_git_keys):
        raise RuntimeError("Cold and warm pre-intervention Git states differ.")

    memory_record: dict[str, Any] | None = None
    if memory:
        if memory_target.is_absolute() or ".." in memory_target.parts:
            raise ValueError("Memory target must be a safe path relative to the warm fork.")
        destination = warm / memory_target
        if destination.exists() and not append_memory:
            raise FileExistsError(f"Refusing to overwrite existing warm memory: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_bytes = memory.read_bytes()
        before_bytes = destination.read_bytes() if destination.exists() else b""
        if append_memory:
            separator = b"" if not before_bytes or before_bytes.endswith(b"\n") else b"\n"
            injected = (
                separator
                + b"\n<!-- SWECHATS_LEARNED_MEMORY_START -->\n"
                + source_bytes.rstrip(b"\n")
                + b"\n<!-- SWECHATS_LEARNED_MEMORY_END -->\n"
            )
            destination.write_bytes(before_bytes + injected)
        else:
            shutil.copy2(memory, destination)
        memory_record = {
            "source": str(memory),
            "target": memory_target.as_posix(),
            "mode": "append_marked_section" if append_memory else "create",
            "source_sha256": sha256(source_bytes).hexdigest(),
            "target_before_sha256": sha256(before_bytes).hexdigest(),
            "target_after_sha256": sha256(destination.read_bytes()).hexdigest(),
        }

    fork_manifest = {
        "schema_version": "fork-pair-v1",
        "case_id": manifest["case"]["case_id"],
        "session_id": manifest["case"]["session_id"],
        "replay_tier": manifest["fidelity"]["maximum_supported_tier"],
        "primary_benchmark_eligible": eligible,
        "exploratory_override": allow_exploratory and not eligible,
        "repo": str(repo.resolve()),
        "base_ref": base_ref,
        "resolved_commit": resolved_commit,
        "base_ref_evidence": "operator_supplied; certification belongs in replay audit",
        "workspace_construction": "independent_git_clone_plus_observed_agent_replay",
        "cold_git_state_before_memory": cold_git,
        "warm_git_state_before_memory": warm_git,
        "cold_observed_agent_replay": cold_replay,
        "warm_observed_agent_replay": warm_replay,
        "cold_rebased_transcript": cold_transcript,
        "warm_rebased_transcript": warm_transcript,
        "cold_pre_intervention_sha256": cold_pre,
        "warm_pre_intervention_sha256": warm_pre,
        "pre_intervention_identical": cold_pre == warm_pre,
        "cold_post_intervention_sha256": directory_digest(cold),
        "warm_post_intervention_sha256": directory_digest(warm),
        "memory_intervention": memory_record,
        "prerequisite_assertions": {
            "independent_git_repositories": True,
            "base_commit_equal": cold_git["head"] == warm_git["head"] == resolved_commit,
            "git_state_equal_before_memory": all(
                cold_git[key] == warm_git[key] for key in semantic_git_keys
            ),
            "observed_agent_action_coverage_complete": True,
            "unsupported_or_ambiguous_observed_actions": 0,
            "unknown_human_changes_included": False,
            "path_mapping_recorded": True,
            "native_history_rebased_without_future_turns": True,
            "cold_warm_workspace_equal_before_memory": cold_pre == warm_pre,
            "memory_is_only_intentional_workspace_difference": memory_record is not None,
            "native_claude_reentry_canary_passed": False,
            "ready_for_scored_reconstructed_experiment": False,
        },
    }
    (forks / "manifest.json").write_text(
        json.dumps(fork_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return fork_manifest


def _parse_claude_structured_result(result: dict[str, Any]) -> dict[str, Any]:
    payload = result.get("structured_output", result.get("result"))
    if isinstance(payload, dict):
        return payload
    if not isinstance(payload, str):
        raise ValueError("Claude result did not contain structured output.")
    text = payload.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Claude structured result was not an object.")
    return parsed


def run_claude_reentry_canary(
    bundle: Path,
    *,
    arm: str,
    model: str = "sonnet",
    max_budget_usd: float = 0.30,
) -> dict[str, Any]:
    """Verify native Claude resume can access both history and reconstructed state."""

    if arm not in {"cold", "warm"}:
        raise ValueError("Arm must be 'cold' or 'warm'.")
    forks = bundle / "forks"
    manifest_path = forks / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    workspace = (forks / arm).resolve()
    replay = manifest[f"{arm}_observed_agent_replay"]
    replayed = [
        record
        for record in replay["ledger"]
        if record["classification"] == "replayed_mutation"
    ]
    if replayed:
        probe_relative = replayed[-1]["relative_path"]
    else:
        candidates = [
            path.relative_to(workspace).as_posix()
            for path in sorted(workspace.rglob("*"))
            if path.is_file() and ".git" not in path.relative_to(workspace).parts
        ]
        if not candidates:
            raise ValueError("No workspace file is available for the re-entry canary.")
        probe_relative = candidates[0]
    probe = workspace / probe_relative
    current_lines = probe.read_text(encoding="utf-8").splitlines()
    expected_probe_line = next((line for line in current_lines if line.strip()), "")
    probe_line_number = current_lines.index(expected_probe_line) + 1
    probe_demonstrates_replay = False
    if replayed:
        try:
            base_lines = _run_git(workspace, "show", f"HEAD:{probe_relative}").splitlines()
        except subprocess.CalledProcessError:
            base_lines = []
        for index in range(max(len(base_lines), len(current_lines))):
            base_line = base_lines[index] if index < len(base_lines) else None
            current_line = current_lines[index] if index < len(current_lines) else None
            if current_line is not None and current_line != base_line:
                probe_line_number = index + 1
                expected_probe_line = current_line
                probe_demonstrates_replay = True
                break
    case_manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    case = EvalCase(**case_manifest["case"])
    prior_user = (
        read_table("conversations")
        .filter(
            (pl.col("session_id") == case.session_id)
            & (pl.col("turn_number") < case.instruction_turn_number)
            & (pl.col("turn_type") == "user_prompt")
            & (pl.col("role") == "user")
        )
        .sort("turn_number")
        .tail(1)
    )
    expected_instruction = (
        str(prior_user.select("content").item()) if not prior_user.is_empty() else ""
    )

    transcript_path = Path(manifest[f"{arm}_rebased_transcript"]["output"]).resolve()
    project_key = str(workspace).replace("/", "-")
    claude_project = Path.home() / ".claude" / "projects" / project_key
    claude_project.mkdir(parents=True, exist_ok=True)
    installed_transcript = claude_project / f"{manifest['session_id']}.jsonl"
    shutil.copy2(transcript_path, installed_transcript)

    before_digest = directory_digest(workspace)
    before_git = git_state(workspace)
    schema = json.dumps(
        {
            "type": "object",
            "properties": {
                "previous_user_instruction": {"type": "string"},
                "probe_line": {"type": "string"},
            },
            "required": ["previous_user_instruction", "probe_line"],
            "additionalProperties": False,
        }
    )
    prompt = (
        "This is a read-only re-entry canary. Use the resumed history and Read tool. "
        "Return the exact prior user instruction from the resumed history immediately "
        "before this message, or an empty string if none exists, and the "
        f"exact content of line {probe_line_number} of {probe_relative}. "
        "Do not modify anything."
    )
    command = [
        "claude",
        "--resume",
        manifest["session_id"],
        "--fork-session",
        "--print",
        prompt,
        "--tools",
        "Read",
        "--setting-sources",
        "local",
        "--settings",
        "{}",
        "--strict-mcp-config",
        "--no-chrome",
        "--disable-slash-commands",
        "--permission-mode",
        "dontAsk",
        "--model",
        model,
        "--max-budget-usd",
        str(max_budget_usd),
        "--json-schema",
        schema,
        "--output-format",
        "json",
    ]
    completed = subprocess.run(
        command,
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    raw_result = json.loads(completed.stdout)
    answer = _parse_claude_structured_result(raw_result)
    after_digest = directory_digest(workspace)
    after_git = git_state(workspace)
    checks = {
        "previous_instruction_exact": (
            answer.get("previous_user_instruction") == expected_instruction
        ),
        "workspace_probe_exact": (
            answer.get("probe_line") == expected_probe_line
        ),
        "workspace_unchanged": before_digest == after_digest,
        "git_state_unchanged": before_git == after_git,
        "forked_session_created": raw_result.get("session_id") != manifest["session_id"],
    }
    passed = all(checks.values())
    result = {
        "schema_version": "claude-reentry-canary-v1",
        "arm": arm,
        "passed": passed,
        "checks": checks,
        "probe_relative_path": probe_relative,
        "probe_line_number": probe_line_number,
        "expected_probe_line": expected_probe_line,
        "probe_demonstrates_replayed_mutation": probe_demonstrates_replay,
        "expected_previous_user_instruction": expected_instruction,
        "answer": answer,
        "model_requested": model,
        "model_usage": raw_result.get("modelUsage"),
        "cost_usd": raw_result.get("total_cost_usd"),
        "source_session_id": manifest["session_id"],
        "forked_session_id": raw_result.get("session_id"),
        "transcript_sha256": manifest[f"{arm}_rebased_transcript"]["rebased_sha256"],
        "workspace_sha256_before": before_digest,
        "workspace_sha256_after": after_digest,
    }
    output = forks / "reentry" / f"{arm}-canary.json"
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    canaries = manifest.setdefault("reentry_canaries", {})
    canaries[arm] = {"passed": passed, "artifact": str(output)}
    both_passed = all(canaries.get(name, {}).get("passed") for name in ("cold", "warm"))
    assertions = manifest["prerequisite_assertions"]
    assertions["native_claude_reentry_canary_passed"] = both_passed
    assertions["ready_for_scored_reconstructed_experiment"] = bool(
        both_passed
        and assertions["independent_git_repositories"]
        and assertions["base_commit_equal"]
        and assertions["git_state_equal_before_memory"]
        and assertions["observed_agent_action_coverage_complete"]
        and assertions["unsupported_or_ambiguous_observed_actions"] == 0
        and assertions["path_mapping_recorded"]
        and assertions["native_history_rebased_without_future_turns"]
        and assertions["cold_warm_workspace_equal_before_memory"]
        and assertions["memory_is_only_intentional_workspace_difference"]
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if not passed:
        raise RuntimeError(f"Claude re-entry canary failed for {arm}: {checks}")
    return result
