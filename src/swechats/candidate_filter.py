"""LLM-backed filtering for SWE-chat eval-case candidates."""

from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable

import httpx
import weave


DEFAULT_WANDB_BASE_URL = "https://api.inference.wandb.ai/v1"
DEFAULT_MODEL = "moonshotai/Kimi-K2.6"
DEFAULT_TIMEOUT_SECONDS = 120.0


SCORE_KEYS = (
    "human_written_pushback",
    "factual_correction",
    "mistake_visible_in_A",
    "binary_judgeable",
    "durable_repo_memory_value",
    "prior_learnability",
    "demo_strength",
)

FLAG_KEYS = (
    "ai_generated_suspect",
    "heavy_markdown_or_table",
    "vague_pushback",
    "style_only",
    "unverified_failure_report",
    "one_off_instruction",
    "leakage_risk",
)


SYSTEM_PROMPT = """You are filtering SWE-chat correction cases for a repo-memory evaluation.

We are testing this thesis:

If an agent has useful repository-local memory, injected as repo-native instructions
such as CLAUDE.md, it should avoid mistakes that caused real users to correct
prior agent outputs.

You receive one candidate case with:
- I: the user instruction before the problematic agent action
- A: the original agent action/answer that received pushback
- P: the user pushback/correction
- optional original trajectory/diff/context
- native_state evidence
- optional prior same-repo evidence snippets

Decide whether this is a strong eval case.

A strong case must satisfy ALL of these:
1. P appears human-written, not AI-generated or copied from an automated review.
2. P corrects a real factual, semantic, architectural, API, workflow, or repo-convention mistake.
3. The mistake is visible in A, the trajectory, or the resulting diff.
4. P is specific enough that a binary judge can decide whether a new answer repeats the flaw.
5. The correction reflects a durable repo-local invariant, convention, workflow, API fact, test harness rule, or agent-specific format.
6. A repo memory could plausibly prevent the mistake in a future cold/warm rerun.
7. The case is not mainly subjective taste, wording preference, vague follow-up, generic "continue", or broad planning.
8. The case is not merely a failure report like "it still doesn't work" unless the flaw is directly visible without executing the code.
9. The case does not leak from the held-out session into memory. If the only source of the rule is P itself, mark prior_learnability as weak.

Hard reject if:
- P looks AI-generated, bot-generated, or copied from a code review tool.
- P contains markdown tables, severity labels, "High Severity", "Medium Severity", "Copilot says", "review feedback", or highly structured issue-report formatting.
- P is mostly a pasted checklist or long generated markdown block.
- P is too vague to judge.
- P is only style/taste.
- A does not contain or imply the mistake.
- The correction is a one-off instruction that would not belong in durable repo memory.

Score generously only when the case would make a convincing demo:
"Here is a real correction. We learned this repo rule from prior history. Cold repeats the mistake. Warm avoids it."

Return ONLY valid JSON matching this schema:
{
  "case_id": "string",
  "decision": "keep" | "drop" | "needs_review",
  "overall_score": 0,
  "scores": {
    "human_written_pushback": 0,
    "factual_correction": 0,
    "mistake_visible_in_A": 0,
    "binary_judgeable": 0,
    "durable_repo_memory_value": 0,
    "prior_learnability": 0,
    "demo_strength": 0
  },
  "flags": {
    "ai_generated_suspect": false,
    "heavy_markdown_or_table": false,
    "vague_pushback": false,
    "style_only": false,
    "unverified_failure_report": false,
    "one_off_instruction": false,
    "leakage_risk": false
  },
  "exclusion_reasons": [],
  "flaw_description": "string",
  "repo_memory_candidate": "string",
  "binary_judge_question": "string",
  "evidence": {
    "quote_from_A": "string",
    "quote_from_P": "string",
    "why_memory_could_help": "string",
    "prior_evidence_needed": "string"
  },
  "confidence": 0.0
}

Scoring rules:
- Each score is 0 to 3.
- overall_score is the sum of the seven score fields, max 21.
- Use decision = "keep" only if:
  - overall_score >= 16
  - human_written_pushback >= 2
  - factual_correction >= 2
  - mistake_visible_in_A >= 2
  - binary_judgeable >= 2
  - durable_repo_memory_value >= 2
  - no hard reject flags are true
- Use decision = "needs_review" for promising but uncertain cases.
- Use decision = "drop" for weak, vague, AI-looking, stylistic, or non-memory cases.

Be strict. We want fewer, better cases.
"""


@dataclass(frozen=True)
class InferenceConfig:
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_WANDB_BASE_URL
    temperature: float = 1.0
    max_tokens: int | None = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = 8
    initial_retry_delay_seconds: float = 1.0
    max_retry_delay_seconds: float = 60.0
    retry_jitter_seconds: float = 0.25


class WandbInferenceClient:
    """Small OpenAI-compatible client for W&B Inference chat completions."""

    def __init__(self, *, api_key: str, config: InferenceConfig) -> None:
        self.api_key = api_key
        self.config = config

    def complete_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "response_format": {"type": "json_object"},
        }
        if self.config.max_tokens is not None:
            payload["max_tokens"] = self.config.max_tokens

        attempt = 0
        while True:
            response: httpx.Response | None = None
            try:
                response = httpx.post(
                    f"{self.config.base_url.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=self.config.timeout_seconds,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt >= self.config.max_retries:
                    raise RuntimeError(
                        "W&B Inference request failed after "
                        f"{attempt + 1} attempts: {exc}"
                    ) from exc
                _sleep_before_retry(config=self.config, attempt=attempt)
                attempt += 1
                continue

            if _is_retryable_status(response.status_code):
                if attempt >= self.config.max_retries:
                    raise RuntimeError(
                        "W&B Inference request failed after "
                        f"{attempt + 1} attempts with HTTP {response.status_code}: "
                        f"{_response_error_text(response)}"
                    )
                _sleep_before_retry(
                    config=self.config,
                    attempt=attempt,
                    retry_after_seconds=_retry_after_seconds(response),
                )
                attempt += 1
                continue

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(
                    "W&B Inference request failed with "
                    f"HTTP {response.status_code}: {_response_error_text(response)}"
                ) from exc

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            try:
                return parse_json_object(content)
            except (json.JSONDecodeError, ValueError) as exc:
                if attempt >= self.config.max_retries:
                    excerpt = content.strip().replace("\n", "\\n")[:500]
                    raise RuntimeError(
                        "W&B Inference returned malformed JSON after "
                        f"{attempt + 1} attempts: {excerpt}"
                    ) from exc
                _sleep_before_retry(config=self.config, attempt=attempt)
                attempt += 1


def parse_json_object(content: str) -> dict[str, Any]:
    """Parse a JSON object, allowing fenced JSON from less obedient models."""

    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end < start:
            raise
        parsed = json.loads(stripped[start : end + 1])

    if not isinstance(parsed, dict):
        raise ValueError("Model response was not a JSON object.")
    return parsed


def _response_error_text(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
    else:
        text = json.dumps(payload, ensure_ascii=False)
    return text[:800] if text else response.reason_phrase


def _is_retryable_status(status_code: int) -> bool:
    return status_code in {408, 409, 425, 429, 500, 502, 503, 504}


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, retry_at.timestamp() - time.time())


def _sleep_before_retry(
    *,
    config: InferenceConfig,
    attempt: int,
    retry_after_seconds: float | None = None,
) -> None:
    backoff = min(
        config.max_retry_delay_seconds,
        config.initial_retry_delay_seconds * (2**attempt),
    )
    delay = retry_after_seconds if retry_after_seconds is not None else backoff
    delay += random.uniform(0.0, config.retry_jitter_seconds)
    time.sleep(delay)


def load_jsonl(path: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
                if limit is not None and len(rows) >= limit:
                    break
    return rows


def write_jsonl(rows: Iterable[dict[str, Any]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str))
            handle.write("\n")
    return path


def append_jsonl(row: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, default=str))
        handle.write("\n")
        handle.flush()


def load_scored_rows_by_index(path: Path) -> dict[int, dict[str, Any]]:
    rows_by_index: dict[int, dict[str, Any]] = {}
    if not path.exists():
        return rows_by_index
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                index = int(row["filter_row_index"])
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if row.get("filter_verdict") and not row.get("filter_error"):
                rows_by_index[index] = row
    return rows_by_index


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Load simple KEY=VALUE entries without printing or overriding env vars."""

    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _resolve_wandb_api_key(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    _load_dotenv()
    env_key = os.environ.get("WANDB_API_KEY")
    if env_key:
        return env_key
    try:
        import wandb
    except ModuleNotFoundError:
        return None
    return getattr(getattr(wandb, "api", None), "api_key", None)


def _resolve_weave_project(explicit: str | None = None) -> str:
    _load_dotenv()
    return (
        explicit
        or os.environ.get("WEAVE_PROJECT")
        or os.environ.get("WANDB_PROJECT")
        or "swechats"
    )


def filter_candidates(
    *,
    input_path: Path,
    output_path: Path,
    config: InferenceConfig,
    limit: int | None = None,
    weave_project: str | None = None,
    api_key: str | None = None,
    concurrency: int = 1,
) -> list[dict[str, Any]]:
    """Run W&B inference over candidate JSONL rows and write scored JSONL."""

    resolved_key = _resolve_wandb_api_key(api_key)
    if not resolved_key:
        raise RuntimeError("Set WANDB_API_KEY or pass an API key before filtering.")

    os.environ.setdefault("WANDB_API_KEY", resolved_key)
    resolved_weave_project = _resolve_weave_project(weave_project)
    weave.init(resolved_weave_project)

    rows = load_jsonl(input_path, limit=limit)
    scored_by_index = load_scored_rows_by_index(output_path)
    pending_rows = [
        (index, row)
        for index, row in enumerate(rows)
        if index not in scored_by_index
    ]
    if concurrency <= 1:
        for index, row in pending_rows:
            scored_row = score_candidate(row=row, config=config, row_index=index)
            append_jsonl(scored_row, output_path)
            scored_by_index[index] = scored_row
    else:
        pending_iter = iter(pending_rows)
        futures: dict[Future[dict[str, Any]], int] = {}
        executor = ThreadPoolExecutor(max_workers=concurrency)

        def submit_until_full() -> None:
            while len(futures) < concurrency:
                try:
                    index, row = next(pending_iter)
                except StopIteration:
                    return
                futures[
                    executor.submit(
                        score_candidate,
                        row=row,
                        config=config,
                        row_index=index,
                    )
                ] = index

        try:
            submit_until_full()
            while futures:
                done, _ = wait(futures, return_when=FIRST_COMPLETED)
                for future in done:
                    index = futures.pop(future)
                    scored_row = future.result()
                    append_jsonl(scored_row, output_path)
                    scored_by_index[index] = scored_row
                submit_until_full()
        except Exception:
            for future in futures:
                future.cancel()
            executor.shutdown(wait=True, cancel_futures=True)
            raise
        else:
            executor.shutdown(wait=True)
    scored = [scored_by_index[index] for index in range(len(rows))]
    return scored


@weave.op()
def score_candidate(
    *,
    row: dict[str, Any],
    config: InferenceConfig,
    row_index: int,
) -> dict[str, Any]:
    api_key = os.environ.get("WANDB_API_KEY")
    if not api_key:
        raise RuntimeError("Set WANDB_API_KEY before filtering.")

    client = WandbInferenceClient(api_key=api_key, config=config)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": candidate_prompt(row)},
    ]
    verdict = normalize_verdict(client.complete_json(messages))
    return {
        **row,
        "filter_model": config.model,
        "filter_temperature": config.temperature,
        "filter_max_tokens": config.max_tokens,
        "filter_row_index": row_index,
        "filter_verdict": verdict,
    }


def candidate_prompt(row: dict[str, Any]) -> str:
    """Build a compact prompt that works for eval-case and raw-candidate rows."""

    fields = {
        "case_id": row.get("case_id") or row.get("turn_id"),
        "repo_id": row.get("repo_id"),
        "session_id": row.get("session_id"),
        "session_created_at": row.get("session_created_at"),
        "repo_session_index": row.get("repo_session_index"),
        "eligible_prior_sessions": row.get("eligible_prior_sessions"),
        "pushback_label": row.get("prompt_pushback"),
        "prompt_intent": row.get("prompt_intent"),
        "instruction_I": row.get("I") or row.get("i_content") or row.get("i_preview"),
        "agent_action_A": row.get("A") or row.get("a_content") or row.get("a_preview"),
        "pushback_P": (
            row.get("P") or row.get("p_content") or row.get("p_preview") or row.get("content")
        ),
        "native_state": row.get("native_state"),
        "prior_same_repo_evidence_snippets": row.get("prior_same_repo_evidence_snippets", []),
        "original_trajectory_summary": row.get("original_trajectory_summary"),
    }
    return json.dumps(fields, ensure_ascii=False, default=str)


def normalize_verdict(verdict: dict[str, Any]) -> dict[str, Any]:
    case_id = str(verdict.get("case_id") or "")
    decision = str(verdict.get("decision") or "").strip().lower()
    if decision not in {"keep", "drop", "needs_review"}:
        usable = bool(verdict.get("usable", decision == "keep"))
        decision = "keep" if usable else "drop"

    try:
        confidence = float(verdict.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    raw_scores = verdict.get("scores", {})
    if not isinstance(raw_scores, dict):
        raw_scores = {}
    scores: dict[str, int] = {}
    for key in SCORE_KEYS:
        try:
            value = int(raw_scores.get(key, 0))
        except (TypeError, ValueError):
            value = 0
        scores[key] = max(0, min(3, value))

    raw_flags = verdict.get("flags", {})
    if not isinstance(raw_flags, dict):
        raw_flags = {}
    flags = {key: bool(raw_flags.get(key, False)) for key in FLAG_KEYS}

    try:
        overall_score = int(verdict.get("overall_score", sum(scores.values())))
    except (TypeError, ValueError):
        overall_score = sum(scores.values())
    overall_score = max(0, min(21, overall_score))

    exclusion_reasons = (
        verdict.get("exclusion_reasons")
        or verdict.get("drop_reasons")
        or []
    )
    if not isinstance(exclusion_reasons, list):
        exclusion_reasons = [str(exclusion_reasons)]

    evidence = verdict.get("evidence", {})
    if not isinstance(evidence, dict):
        evidence = {}

    return {
        "case_id": case_id,
        "usable": decision == "keep",
        "decision": decision,
        "overall_score": overall_score,
        "scores": scores,
        "flags": flags,
        "confidence": max(0.0, min(1.0, confidence)),
        "exclusion_reasons": [str(reason) for reason in exclusion_reasons],
        "flaw_description": str(
            verdict.get("flaw_description") or verdict.get("flaw") or ""
        ),
        "repo_memory_candidate": str(
            verdict.get("repo_memory_candidate")
            or verdict.get("memory_candidate")
            or ""
        ),
        "binary_judge_question": str(verdict.get("binary_judge_question") or ""),
        "evidence": {
            "quote_from_A": str(evidence.get("quote_from_A") or ""),
            "quote_from_P": str(evidence.get("quote_from_P") or ""),
            "why_memory_could_help": str(evidence.get("why_memory_could_help") or ""),
            "prior_evidence_needed": str(evidence.get("prior_evidence_needed") or ""),
        },
    }
