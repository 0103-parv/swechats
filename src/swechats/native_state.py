"""Native SWE-chat state artifacts for repo-visible replay validation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import polars as pl

from swechats.data import scan_table


NATIVE_AGENT_MUTATION_TOOLS = {
    "Edit",
    "Write",
    "apply_patch",
    "replace",
    "write",
    "write_file",
    "mcp__acp__Write",
}


@dataclass(frozen=True)
class NativeStateEvidence:
    """Dataset-native state anchors available for one session/checkpoint."""

    session_id: str
    checkpoint_pks: tuple[str, ...]
    checkpoint_metadata: dict[str, Any]
    session_metadata: dict[str, Any]
    commit_status_counts: dict[str, int]
    ok_commit_count: int
    patch_count: int
    files_changed_count: int
    agent_change_count: int
    agent_change_tool_counts: dict[str, int]
    agent_change_file_count: int
    unsupported_agent_change_tools: tuple[str, ...]
    file_attribution_commit_count: int
    file_attribution_entry_count: int
    file_attribution_counts: dict[str, int]
    agent_version_file_count: int
    committed_version_file_count: int
    transcript_boundary: dict[str, Any]

    @property
    def has_ok_commit_anchor(self) -> bool:
        return self.ok_commit_count > 0

    @property
    def has_agent_change_replay_log(self) -> bool:
        return self.agent_change_count > 0

    @property
    def has_file_version_anchors(self) -> bool:
        return self.agent_version_file_count > 0 or self.committed_version_file_count > 0

    @property
    def has_native_repo_visible_anchors(self) -> bool:
        return (
            self.has_ok_commit_anchor
            and self.has_agent_change_replay_log
            and self.has_file_version_anchors
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "checkpoint_pks": list(self.checkpoint_pks),
            "checkpoint_metadata": self.checkpoint_metadata,
            "session_metadata": self.session_metadata,
            "commit_status_counts": self.commit_status_counts,
            "ok_commit_count": self.ok_commit_count,
            "patch_count": self.patch_count,
            "files_changed_count": self.files_changed_count,
            "agent_change_count": self.agent_change_count,
            "agent_change_tool_counts": self.agent_change_tool_counts,
            "agent_change_file_count": self.agent_change_file_count,
            "unsupported_agent_change_tools": list(self.unsupported_agent_change_tools),
            "file_attribution_commit_count": self.file_attribution_commit_count,
            "file_attribution_entry_count": self.file_attribution_entry_count,
            "file_attribution_counts": self.file_attribution_counts,
            "agent_version_file_count": self.agent_version_file_count,
            "committed_version_file_count": self.committed_version_file_count,
            "transcript_boundary": self.transcript_boundary,
            "has_ok_commit_anchor": self.has_ok_commit_anchor,
            "has_agent_change_replay_log": self.has_agent_change_replay_log,
            "has_file_version_anchors": self.has_file_version_anchors,
            "has_native_repo_visible_anchors": self.has_native_repo_visible_anchors,
        }


def parse_json_list(value: Any) -> list[Any]:
    """Parse a JSON-list string, returning an empty list on missing/bad data."""

    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def parse_json_object(value: Any) -> dict[str, Any]:
    """Parse a JSON-object string, returning an empty dict on missing/bad data."""

    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def checkpoint_pks_for_session(
    session_id: str,
    data_dir: Path | str = "data/swe-chat",
) -> tuple[str, ...]:
    """Return all checkpoint primary keys associated with a session."""

    sessions = (
        scan_table("sessions", data_dir)
        .filter(pl.col("session_id") == session_id)
        .select(["session_id", "checkpoint_ids", "canonical_checkpoint_pk"])
        .collect()
    )
    if sessions.is_empty():
        return ()
    row = sessions.to_dicts()[0]
    checkpoint_pks = [str(item) for item in parse_json_list(row.get("checkpoint_ids"))]
    canonical = row.get("canonical_checkpoint_pk")
    if canonical:
        checkpoint_pks.append(str(canonical))
    return tuple(dict.fromkeys(checkpoint_pks))


def commit_rows_for_session(
    session_id: str,
    data_dir: Path | str = "data/swe-chat",
) -> pl.DataFrame:
    """Return commit rows linked through the session's checkpoint ids."""

    checkpoint_pks = checkpoint_pks_for_session(session_id, data_dir)
    if not checkpoint_pks:
        return (
            scan_table("commits", data_dir)
            .select(
                [
                    "checkpoint_pk",
                    "status",
                    "patch",
                    "files_changed",
                    "agent_changes",
                    "file_attribution",
                ]
            )
            .head(0)
            .collect()
        )
    return (
        scan_table("commits", data_dir)
        .filter(pl.col("checkpoint_pk").is_in(list(checkpoint_pks)))
        .select(
            [
                "checkpoint_pk",
                "status",
                "patch",
                "files_changed",
                "agent_changes",
                "file_attribution",
            ]
        )
        .collect()
    )


def _session_metadata(session_id: str, data_dir: Path | str) -> dict[str, Any]:
    rows = (
        scan_table("session_logs", data_dir)
        .filter(pl.col("session_id") == session_id)
        .select("session_metadata_raw")
        .collect()
        .to_dicts()
    )
    return parse_json_object(rows[0]["session_metadata_raw"]) if rows else {}


def _checkpoint_metadata(checkpoint_pks: tuple[str, ...], data_dir: Path | str) -> dict[str, Any]:
    if not checkpoint_pks:
        return {
            "checkpoint_count": 0,
            "has_checkpoint_metadata": False,
            "checkpoint_ids": [],
            "branches": [],
            "session_refs": 0,
            "content_hash_refs": 0,
            "transcript_refs": 0,
            "context_refs": 0,
            "prompt_refs": 0,
            "migration_source_commit_count": 0,
            "combined_attribution_count": 0,
        }
    rows = (
        scan_table("checkpoints", data_dir)
        .filter(pl.col("checkpoint_pk").is_in(list(checkpoint_pks)))
        .select("checkpoint_metadata_raw")
        .collect()
        .to_dicts()
    )
    checkpoint_ids: list[str] = []
    branches: list[str] = []
    session_refs = 0
    content_hash_refs = 0
    transcript_refs = 0
    context_refs = 0
    prompt_refs = 0
    migration_source_commit_count = 0
    combined_attribution_count = 0
    for row in rows:
        metadata = parse_json_object(row.get("checkpoint_metadata_raw"))
        if metadata.get("checkpoint_id"):
            checkpoint_ids.append(str(metadata["checkpoint_id"]))
        if metadata.get("branch"):
            branches.append(str(metadata["branch"]))
        if metadata.get("migration_source_commit"):
            migration_source_commit_count += 1
        if metadata.get("combined_attribution"):
            combined_attribution_count += 1
        for session_ref in metadata.get("sessions") or []:
            if not isinstance(session_ref, dict):
                continue
            session_refs += 1
            content_hash_refs += int(bool(session_ref.get("content_hash")))
            transcript_refs += int(bool(session_ref.get("transcript")))
            context_refs += int(bool(session_ref.get("context")))
            prompt_refs += int(bool(session_ref.get("prompt")))
    return {
        "checkpoint_count": len(rows),
        "has_checkpoint_metadata": bool(rows),
        "checkpoint_ids": checkpoint_ids,
        "branches": sorted(set(branches)),
        "session_refs": session_refs,
        "content_hash_refs": content_hash_refs,
        "transcript_refs": transcript_refs,
        "context_refs": context_refs,
        "prompt_refs": prompt_refs,
        "migration_source_commit_count": migration_source_commit_count,
        "combined_attribution_count": combined_attribution_count,
    }


def native_state_evidence(
    session_id: str,
    data_dir: Path | str = "data/swe-chat",
) -> NativeStateEvidence:
    """Summarize all dataset-native repo-visible state anchors for a session."""

    checkpoint_pks = checkpoint_pks_for_session(session_id, data_dir)
    commits = commit_rows_for_session(session_id, data_dir)
    status_counts = Counter(str(row["status"]) for row in commits.select("status").to_dicts())
    ok_commits = commits.filter(pl.col("status") == "ok")

    agent_change_tools: Counter[str] = Counter()
    agent_change_files: set[str] = set()
    agent_change_count = 0
    for row in commits.select("agent_changes").to_dicts():
        for change in parse_json_list(row.get("agent_changes")):
            if not isinstance(change, dict):
                continue
            agent_change_count += 1
            tool = str(change.get("tool_name") or "")
            agent_change_tools[tool] += 1
            if change.get("file_path"):
                agent_change_files.add(str(change["file_path"]))

    attribution_counts: Counter[str] = Counter()
    file_attribution_entry_count = 0
    agent_version_file_count = 0
    committed_version_file_count = 0
    file_attribution_commit_count = 0
    for row in ok_commits.select("file_attribution").to_dicts():
        attribution = parse_json_object(row.get("file_attribution"))
        if not attribution:
            continue
        file_attribution_commit_count += 1
        for path, info in attribution.items():
            if path == "__aggregate__" or not isinstance(info, dict):
                continue
            file_attribution_entry_count += 1
            attribution_counts[str(info.get("attribution"))] += 1
            agent_version_file_count += int(info.get("agent_version") is not None)
            committed_version_file_count += int(info.get("committed_version") is not None)

    session_metadata = _session_metadata(session_id, data_dir)
    transcript_boundary = {
        key: session_metadata.get(key)
        for key in [
            "transcript_path",
            "transcript_identifier_at_start",
            "transcript_lines_at_start",
            "checkpoint_transcript_start",
            "transcript_uuid_at_start",
            "turn_id",
        ]
        if session_metadata.get(key) not in (None, "", [])
    }
    unsupported_tools = tuple(
        sorted(tool for tool in agent_change_tools if tool not in NATIVE_AGENT_MUTATION_TOOLS)
    )

    return NativeStateEvidence(
        session_id=session_id,
        checkpoint_pks=checkpoint_pks,
        checkpoint_metadata=_checkpoint_metadata(checkpoint_pks, data_dir),
        session_metadata={
            "has_session_metadata": bool(session_metadata),
            "has_initial_attribution": bool(session_metadata.get("initial_attribution")),
            "has_prompt_attributions": bool(session_metadata.get("prompt_attributions")),
            "has_summary": bool(session_metadata.get("summary")),
            "has_session_metrics": bool(session_metadata.get("session_metrics")),
            "model": session_metadata.get("model"),
            "agent": session_metadata.get("agent"),
            "strategy": session_metadata.get("strategy"),
        },
        commit_status_counts=dict(status_counts),
        ok_commit_count=ok_commits.height,
        patch_count=ok_commits.filter(
            pl.col("patch").is_not_null() & (pl.col("patch") != "")
        ).height,
        files_changed_count=ok_commits.filter(
            pl.col("files_changed").is_not_null() & (pl.col("files_changed") != "")
        ).height,
        agent_change_count=agent_change_count,
        agent_change_tool_counts=dict(agent_change_tools),
        agent_change_file_count=len(agent_change_files),
        unsupported_agent_change_tools=unsupported_tools,
        file_attribution_commit_count=file_attribution_commit_count,
        file_attribution_entry_count=file_attribution_entry_count,
        file_attribution_counts=dict(attribution_counts),
        agent_version_file_count=agent_version_file_count,
        committed_version_file_count=committed_version_file_count,
        transcript_boundary=transcript_boundary,
    )
