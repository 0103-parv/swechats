from __future__ import annotations

import json
from pathlib import Path

from swechats.replay import EvalCase
from swechats.smoke import (
    build_oracle_packet,
    format_learned_memory,
    render_candidate_for_judge,
    render_run_html,
    stage_path,
    write_stage,
)


def _case() -> EvalCase:
    return EvalCase(
        case_id="session#41:correction",
        repo_id="entireio/cli",
        session_id="session",
        checkpoint_pk="entireio/cli#checkpoint",
        instruction_turn_id="session#24",
        instruction_turn_number=24,
        instruction="check external contributors",
        original_action_turn_id="session#37",
        original_action_turn_number=37,
        original_action="thanked internal people as external",
        pushback_turn_id="session#41",
        pushback_turn_number=41,
        pushback="@pfleidi and @toothbrush are also internal",
        pushback_label="correction",
    )


def test_write_stage_uses_ordered_json_file(tmp_path: Path) -> None:
    path = write_stage(tmp_path, 3, "oracle_packet", {"b": 2, "a": 1})

    assert path == tmp_path / "stages/03-oracle_packet.json"
    assert json.loads(path.read_text()) == {"b": 2, "a": 1}
    assert stage_path(tmp_path, 3, "oracle_packet") == path


def test_format_learned_memory_records_sources_without_target_session() -> None:
    memory = format_learned_memory(
        _case(),
        source_rows=[
            {
                "session_id": "prior",
                "turn_number": 41,
                "content": "CODEOWNERS alone is not enough; branch namespace matters.",
            }
        ],
        codeowners="# Default code owners\n* @entireio/cli-maintainers\n",
    )

    assert "target session `session`" in memory
    assert "prior#41" in memory
    assert "CODEOWNERS" in memory
    assert "external contributors" in memory


def test_render_run_html_embeds_parseable_json(tmp_path: Path) -> None:
    run = {
        "schema_version": "swechats-smoke-run-v1",
        "case": {"case_id": "case-1"},
        "stages": [{"name": "deps", "path": "stages/01-deps.json"}],
    }
    html = render_run_html(run)

    assert "application/json" in html
    embedded = html.split('<script id="run-json" type="application/json">', 1)[1]
    embedded = embedded.split("</script>", 1)[0]
    assert json.loads(embedded)["case"]["case_id"] == "case-1"


def test_render_candidate_for_judge_excludes_git_state_and_diff() -> None:
    rendered = render_candidate_for_judge(
        arm="warm",
        result_text="Fixed. Thanks to @AlienKevin.",
        stderr="",
    )

    assert "Fixed. Thanks to @AlienKevin." in rendered
    assert "GIT STATUS" not in rendered
    assert "GIT DIFF" not in rendered


def test_build_oracle_packet_uses_history_and_user_only_downstream(monkeypatch) -> None:
    case = _case()

    class Prefix:
        lines = (b'{"type":"message","role":"user","content":"prior"}\n',)

    def fake_read_table(name, data_dir):
        import polars as pl

        assert name == "conversations"
        return pl.DataFrame(
            [
                {
                    "session_id": "session",
                    "turn_number": 41,
                    "role": "user",
                    "content": "@pfleidi and @toothbrush are internal",
                    "is_conversational": True,
                },
                {
                    "session_id": "session",
                    "turn_number": 42,
                    "role": "assistant",
                    "content": "Updated.",
                    "is_conversational": True,
                },
                {
                    "session_id": "session",
                    "turn_number": 43,
                    "role": "user",
                    "content": "only @AlienKevin should be thanked",
                    "is_conversational": True,
                },
            ]
        )

    monkeypatch.setattr("swechats.smoke.history_prefix", lambda _case, _data_dir: Prefix())
    monkeypatch.setattr("swechats.smoke.original_trajectory", lambda _case, _data_dir: [])
    monkeypatch.setattr("swechats.smoke.read_table", fake_read_table)

    oracle = build_oracle_packet(case, Path("data/swe-chat"))

    assert oracle.history == '{"type":"message","role":"user","content":"prior"}'
    downstream = json.loads(oracle.downstream_user_messages)
    assert [row["turn_number"] for row in downstream] == [41, 43]
    assert "accepted_outcome" not in oracle.model_dump()
