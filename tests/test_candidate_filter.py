from __future__ import annotations

import httpx

from swechats import candidate_filter
from swechats.candidate_filter import (
    InferenceConfig,
    WandbInferenceClient,
    candidate_prompt,
    filter_candidates,
    normalize_verdict,
    parse_json_object,
    write_jsonl,
)


def test_parse_json_object_allows_fenced_json() -> None:
    assert parse_json_object('```json\n{"usable": true}\n```') == {"usable": True}


def test_normalize_verdict_bounds_confidence_and_decision() -> None:
    assert normalize_verdict({"usable": False, "confidence": "2.4"}) == {
        "case_id": "",
        "usable": False,
        "decision": "drop",
        "overall_score": 0,
        "scores": {
            "human_written_pushback": 0,
            "factual_correction": 0,
            "mistake_visible_in_A": 0,
            "binary_judgeable": 0,
            "durable_repo_memory_value": 0,
            "prior_learnability": 0,
            "demo_strength": 0,
        },
        "flags": {
            "ai_generated_suspect": False,
            "heavy_markdown_or_table": False,
            "vague_pushback": False,
            "style_only": False,
            "unverified_failure_report": False,
            "one_off_instruction": False,
            "leakage_risk": False,
        },
        "confidence": 1.0,
        "exclusion_reasons": [],
        "flaw_description": "",
        "repo_memory_candidate": "",
        "binary_judge_question": "",
        "evidence": {
            "quote_from_A": "",
            "quote_from_P": "",
            "why_memory_could_help": "",
            "prior_evidence_needed": "",
        },
    }


def test_normalize_verdict_structured_scores_and_flags() -> None:
    verdict = normalize_verdict(
        {
            "case_id": "case-1",
            "decision": "needs_review",
            "overall_score": 99,
            "scores": {
                "human_written_pushback": 3,
                "factual_correction": "2",
                "demo_strength": -4,
            },
            "flags": {"ai_generated_suspect": True},
            "exclusion_reasons": "maybe bot-like",
            "flaw_description": "wrong repo invariant",
            "repo_memory_candidate": "Remember the invariant.",
            "binary_judge_question": "Did it repeat the invariant error?",
            "evidence": {"quote_from_P": "nope"},
        }
    )

    assert verdict["decision"] == "needs_review"
    assert verdict["usable"] is False
    assert verdict["overall_score"] == 21
    assert verdict["scores"]["human_written_pushback"] == 3
    assert verdict["scores"]["factual_correction"] == 2
    assert verdict["scores"]["demo_strength"] == 0
    assert verdict["flags"]["ai_generated_suspect"] is True
    assert verdict["exclusion_reasons"] == ["maybe bot-like"]


def test_candidate_prompt_prefers_eval_case_triad() -> None:
    prompt = candidate_prompt(
        {
            "case_id": "case-1",
            "repo_id": "owner/repo",
            "i_content": "do the thing",
            "a_content": "done incorrectly",
            "p_content": "you missed the repo helper",
            "content": "raw fallback",
        }
    )

    assert '"instruction_I": "do the thing"' in prompt
    assert '"agent_action_A": "done incorrectly"' in prompt
    assert '"pushback_P": "you missed the repo helper"' in prompt


def test_wandb_client_retries_rate_limits(monkeypatch) -> None:
    calls = []
    request = httpx.Request("POST", "https://example.test/chat/completions")

    def fake_post(*args, **kwargs) -> httpx.Response:
        calls.append((args, kwargs))
        if len(calls) == 1:
            return httpx.Response(
                429,
                headers={"retry-after": "0"},
                json={"error": "slow down"},
                request=request,
            )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"decision": "drop"}'}}]},
            request=request,
        )

    monkeypatch.setattr(candidate_filter.httpx, "post", fake_post)
    monkeypatch.setattr(candidate_filter.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(candidate_filter.random, "uniform", lambda low, high: 0.0)

    client = WandbInferenceClient(
        api_key="test-key",
        config=InferenceConfig(max_retries=1),
    )

    assert client.complete_json([{"role": "user", "content": "hi"}]) == {
        "decision": "drop"
    }
    assert len(calls) == 2


def test_wandb_client_retries_malformed_json(monkeypatch) -> None:
    calls = []
    request = httpx.Request("POST", "https://example.test/chat/completions")

    def fake_post(*args, **kwargs) -> httpx.Response:
        calls.append((args, kwargs))
        content = '{"decision" "drop"}' if len(calls) == 1 else '{"decision": "drop"}'
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}}]},
            request=request,
        )

    monkeypatch.setattr(candidate_filter.httpx, "post", fake_post)
    monkeypatch.setattr(candidate_filter.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(candidate_filter.random, "uniform", lambda low, high: 0.0)

    client = WandbInferenceClient(
        api_key="test-key",
        config=InferenceConfig(max_retries=1),
    )

    assert client.complete_json([{"role": "user", "content": "hi"}]) == {
        "decision": "drop"
    }
    assert len(calls) == 2


def test_filter_candidates_resumes_existing_output(tmp_path, monkeypatch) -> None:
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "output.jsonl"
    write_jsonl([{"case_id": "a"}, {"case_id": "b"}, {"case_id": "c"}], input_path)
    write_jsonl(
        [
            {
                "case_id": "b",
                "filter_row_index": 1,
                "filter_verdict": {"decision": "keep"},
            }
        ],
        output_path,
    )

    scored_indexes = []

    def fake_score_candidate(*, row, config, row_index):
        scored_indexes.append(row_index)
        return {
            **row,
            "filter_row_index": row_index,
            "filter_verdict": {"decision": "drop"},
        }

    monkeypatch.setattr(candidate_filter, "_resolve_wandb_api_key", lambda api_key: "key")
    monkeypatch.setattr(candidate_filter.weave, "init", lambda project: None)
    monkeypatch.setattr(candidate_filter, "score_candidate", fake_score_candidate)

    rows = filter_candidates(
        input_path=input_path,
        output_path=output_path,
        config=InferenceConfig(),
    )

    assert scored_indexes == [0, 2]
    assert [row["filter_row_index"] for row in rows] == [0, 1, 2]
    assert output_path.read_text(encoding="utf-8").count("\n") == 3
