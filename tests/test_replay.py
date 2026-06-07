from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

import pytest

from swechats.native_state import native_state_evidence, parse_json_list, parse_json_object
from swechats.replay import (
    EvalCase,
    _message_text,
    _parse_timestamp,
    directory_digest,
    judge_rubric,
    materialize_fork_pair,
    _is_read_only_bash,
)


def test_native_state_evidence_reads_commit_and_file_anchors(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "transcripts").mkdir()
    pl = pytest.importorskip("polars")
    pl.DataFrame(
        [
            {
                "session_id": "s1",
                "checkpoint_ids": '["repo/name#cp1"]',
                "canonical_checkpoint_pk": "repo/name#cp1",
            }
        ]
    ).write_parquet(data_dir / "sessions.parquet")
    pl.DataFrame(
        [
            {
                "checkpoint_pk": "repo/name#cp1",
                "checkpoint_metadata_raw": json.dumps(
                    {
                        "checkpoint_id": "cp1",
                        "branch": "main",
                        "sessions": [
                            {
                                "transcript": "/cp/full.jsonl",
                                "content_hash": "/cp/hash.txt",
                                "context": "/cp/context.md",
                                "prompt": "/cp/prompt.txt",
                            }
                        ],
                    }
                ),
            }
        ]
    ).write_parquet(data_dir / "checkpoints.parquet")
    pl.DataFrame(
        [
            {
                "checkpoint_pk": "repo/name#cp1",
                "status": "ok",
                "patch": "diff --git a/a.txt b/a.txt\n",
                "files_changed": "M\ta.txt\n",
                "agent_changes": json.dumps(
                    [
                        {
                            "tool_name": "Edit",
                            "file_path": "/repo/a.txt",
                            "old_string": "old",
                            "new_string": "new",
                        }
                    ]
                ),
                "file_attribution": json.dumps(
                    {
                        "a.txt": {
                            "attribution": "agent_only",
                            "agent_version": "new",
                            "committed_version": "new",
                        },
                        "__aggregate__": {"agent_percentage": 100.0},
                    }
                ),
            }
        ]
    ).write_parquet(data_dir / "commits.parquet")
    pl.DataFrame(
        [
            {
                "session_id": "s1",
                "session_metadata_raw": json.dumps(
                    {
                        "transcript_lines_at_start": 12,
                        "initial_attribution": {"agent_lines": 1},
                        "prompt_attributions": [{"checkpoint_number": 1}],
                    }
                ),
            }
        ]
    ).write_parquet(data_dir / "session_logs.parquet")

    evidence = native_state_evidence("s1", data_dir)

    assert evidence.has_native_repo_visible_anchors
    assert evidence.ok_commit_count == 1
    assert evidence.agent_change_tool_counts == {"Edit": 1}
    assert evidence.file_attribution_counts == {"agent_only": 1}
    assert evidence.transcript_boundary["transcript_lines_at_start"] == 12


def test_json_helpers_fail_closed() -> None:
    assert parse_json_list('["a"]') == ["a"]
    assert parse_json_list('{"not": "a list"}') == []
    assert parse_json_object('{"ok": true}') == {"ok": True}
    assert parse_json_object('["not", "an", "object"]') == {}


def test_message_text_ignores_tool_results() -> None:
    event = {
        "type": "user",
        "message": {
            "content": [
                {"type": "tool_result", "content": "not a conversational prompt"}
            ]
        },
    }

    assert _message_text(event) is None


def test_message_text_reads_text_blocks() -> None:
    event = {
        "type": "user",
        "message": {
            "content": [
                {"type": "text", "text": "first"},
                {"type": "text", "text": "second"},
            ]
        },
    }

    assert _message_text(event) == "first\nsecond"


def test_parse_timestamp_normalizes_zulu_time() -> None:
    assert _parse_timestamp("2026-02-24T09:15:29.752Z") == datetime(
        2026, 2, 24, 9, 15, 29, 752000, tzinfo=timezone.utc
    )


def test_directory_digest_changes_with_executable_bit(tmp_path: Path) -> None:
    script = tmp_path / "run.sh"
    script.write_text("echo hello\n", encoding="utf-8")
    plain_digest = directory_digest(tmp_path)
    script.chmod(0o755)

    assert directory_digest(tmp_path) != plain_digest


def test_materialize_fork_pair_is_identical_before_warm_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", repo], check=True)
    subprocess.run(["git", "-C", repo, "config", "user.name", "Test"], check=True)
    subprocess.run(
        ["git", "-C", repo, "config", "user.email", "test@example.com"], check=True
    )
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "-C", repo, "add", "README.md"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-qm", "base"], check=True)

    bundle = tmp_path / "bundle"
    bundle.mkdir()
    case = {
        "case_id": "case-1",
        "repo_id": "owner/repo",
        "session_id": "session-1",
        "checkpoint_pk": "owner/repo#checkpoint",
        "instruction_turn_id": "i",
        "instruction_turn_number": 1,
        "instruction": "Do the task",
        "original_action_turn_id": "a",
        "original_action_turn_number": 2,
        "original_action": "Done",
        "pushback_turn_id": "p",
        "pushback_turn_number": 3,
        "pushback": "That edit is wrong",
        "pushback_label": "correction",
    }
    (bundle / "manifest.json").write_text(
        json.dumps(
            {
                "case": case,
                "fidelity": {
                    "maximum_supported_tier": "C",
                    "primary_benchmark_eligible": False,
                },
            }
        ),
        encoding="utf-8",
    )
    memory = tmp_path / "memory.md"
    memory.write_text("# Memory\n", encoding="utf-8")
    cold_path = bundle / "forks/cold"
    monkeypatch.setattr(
        "swechats.replay.replay_observed_agent_actions",
        lambda case, workspace, data_dir: {
            "historical_workspace_root": str(cold_path.resolve()),
            "ledger": [],
        },
    )
    monkeypatch.setattr(
        "swechats.replay.history_prefix",
        lambda case, data_dir: type(
            "Prefix",
            (),
            {
                "lines": (f'{{"cwd":"{cold_path.resolve()}"}}\n'.encode(),),
                "sha256": "source-hash",
            },
        )(),
    )

    with pytest.raises(ValueError, match="not primary-benchmark eligible"):
        materialize_fork_pair(bundle, repo, "HEAD")

    result = materialize_fork_pair(
        bundle,
        repo,
        "HEAD",
        allow_exploratory=True,
        memory=memory,
    )

    assert result["pre_intervention_identical"] is True
    assert result["cold_pre_intervention_sha256"] == result["warm_pre_intervention_sha256"]
    assert result["cold_post_intervention_sha256"] != result["warm_post_intervention_sha256"]
    assert not (bundle / "forks/cold/AGENTS.md").exists()
    assert (bundle / "forks/warm/AGENTS.md").read_text(encoding="utf-8") == "# Memory\n"


def test_judge_rubric_requires_original_trajectory_context() -> None:
    case = EvalCase(
        case_id="case-1",
        repo_id="owner/repo",
        session_id="session-1",
        checkpoint_pk="owner/repo#checkpoint",
        instruction_turn_id="i",
        instruction_turn_number=1,
        instruction="Do the task",
        original_action_turn_id="a",
        original_action_turn_number=2,
        original_action="Done",
        pushback_turn_id="p",
        pushback_turn_number=3,
        pushback="That edit is wrong",
        pushback_label="correction",
    )

    assert judge_rubric(case)["original_trajectory_context"] == "original-trajectory.jsonl"


def test_read_only_bash_classifier_fails_closed() -> None:
    assert _is_read_only_bash('git log v1..v2 --format="%an" | sort -u')
    assert _is_read_only_bash("gh pr view 123 --json author")
    assert not _is_read_only_bash("git status && rm -rf build")
    assert not _is_read_only_bash("git show HEAD > snapshot.txt")
