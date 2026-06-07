"""End-to-end smoke harness for the repo-memory counterfactual eval."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import Any

import dspy
import polars as pl

from swechats.data import read_table
from swechats.dspysigs import (
    CandidateAction,
    Judge,
    OraclePacket,
    RubricGenerator,
)
from swechats.replay import (
    EvalCase,
    audit_replay,
    case_for_pushback,
    directory_digest,
    git_state,
    history_prefix,
    materialize_fork_pair,
    original_trajectory,
    run_claude_reentry_canary,
    write_case_bundle,
)


SMOKE_SCHEMA_VERSION = "swechats-smoke-run-v1"
DEFAULT_SESSION_ID = "0158ecff-f487-4f8a-91cb-2352d929ee0c"
DEFAULT_PUSHBACK_TURN = 41
DEFAULT_BASE_REF = "bc0448c6c67cb8c5e90c46811487d1e2ad8a36fa"
DEFAULT_DSPY_MODEL = "openai/gpt-5.5"
DEFAULT_CLAUDE_MODEL = "sonnet"


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return str(value)


def stage_path(output: Path, index: int, name: str) -> Path:
    return output / "stages" / f"{index:02d}-{name}.json"


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=_json_default) + "\n",
        encoding="utf-8",
    )
    return path


def write_stage(output: Path, index: int, name: str, data: Any) -> Path:
    return write_json(stage_path(output, index, name), data)


def _run_capture(args: list[str], *, cwd: Path | None = None) -> dict[str, Any]:
    completed = subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, check=False
    )
    return {
        "args": args,
        "cwd": str(cwd) if cwd else None,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "ok": completed.returncode == 0,
    }


def dependency_report(
    *,
    data_dir: Path,
    repo_cache: Path,
    base_ref: str,
    dspy_model: str,
    claude_model: str,
) -> dict[str, Any]:
    """Record every local/runtime dependency needed by the smoke run."""

    parquet = {
        name: (data_dir / f"{name}.parquet").exists()
        for name in [
            "sessions",
            "conversations",
            "commits",
            "checkpoints",
            "repositories",
            "session_logs",
        ]
    }
    transcript_count = (
        sum(1 for _ in (data_dir / "transcripts").glob("*.jsonl"))
        if (data_dir / "transcripts").exists()
        else 0
    )
    claude = _run_capture(["claude", "--version"])
    git_base = (
        _run_capture(
            ["git", "-C", str(repo_cache), "rev-parse", f"{base_ref}^{{commit}}"]
        )
        if repo_cache.exists()
        else {"ok": False, "stderr": f"missing repo cache: {repo_cache}"}
    )
    return {
        "schema_version": "swechats-smoke-dependencies-v1",
        "data_dir": str(data_dir),
        "parquet_tables_present": parquet,
        "transcript_count": transcript_count,
        "repo_cache": str(repo_cache),
        "repo_cache_present": repo_cache.exists(),
        "base_ref": base_ref,
        "base_ref_available": bool(git_base.get("ok")),
        "base_ref_check": git_base,
        "claude_cli": {
            "path": shutil.which("claude"),
            "model": claude_model,
            "version_check": claude,
        },
        "dspy": {
            "model": dspy_model,
            "adapter": "XMLAdapter",
            "xml_adapter_available": hasattr(dspy, "XMLAdapter"),
            "openai_api_key_present": bool(os.environ.get("OPENAI_API_KEY")),
        },
    }


def _case_session_created_at(case: EvalCase, data_dir: Path) -> Any:
    sessions = read_table("sessions", data_dir)
    row = sessions.filter(pl.col("session_id") == case.session_id).select("created_at")
    return row.item() if not row.is_empty() else None


def prior_memory_source_rows(
    case: EvalCase,
    data_dir: Path,
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Find prior same-repo evidence for a small learned-memory artifact."""

    target_created_at = _case_session_created_at(case, data_dir)
    sessions = read_table("sessions", data_dir).select(
        ["session_id", "repo_id", "created_at"]
    )
    prior_sessions = sessions.filter(
        (pl.col("repo_id") == case.repo_id) & (pl.col("session_id") != case.session_id)
    )
    if target_created_at is not None:
        prior_sessions = prior_sessions.filter(pl.col("created_at") < target_created_at)
    prior_ids = prior_sessions.select("session_id")
    conversations = read_table("conversations", data_dir)
    terms = [
        "external contributor",
        "external contributors",
        "CODEOWNERS",
        "cli-maintainers",
    ]
    contains_term = pl.any_horizontal(
        [pl.col("content").str.contains(term, literal=True) for term in terms]
    )
    rows = (
        conversations.join(prior_ids, on="session_id", how="inner")
        .filter(
            (pl.col("repo_id") == case.repo_id)
            & (pl.col("role") != "metadata")
            & contains_term
        )
        .select(["session_id", "turn_number", "role", "turn_type", "content", "timestamp"])
        .sort("timestamp")
        .tail(limit)
        .to_dicts()
    )
    return rows


def _truncate_one_line(text: str, limit: int = 700) -> str:
    normalized = " ".join(text.split())
    return normalized if len(normalized) <= limit else normalized[: limit - 1] + "…"


def format_learned_memory(
    case: EvalCase,
    *,
    source_rows: list[dict[str, Any]],
    codeowners: str,
) -> str:
    """Render a narrow repo-native memory artifact for the warm Claude arm."""

    sources = "\n".join(
        f"- `{row['session_id']}#{row['turn_number']}`: "
        f"{_truncate_one_line(str(row.get('content') or ''))}"
        for row in source_rows
    )
    if not sources:
        sources = "- No prior source rows matched; this memory is a smoke placeholder."
    return f"""# Learned Memory: release contributor checks

When preparing `entireio/cli` release notes or changelog thanks sections, do not
infer that every git author is an external contributor.

- Check `.github/CODEOWNERS`, org/team membership signals, prior release thanks,
  branch namespaces, and author email domains before calling someone external.
- A team-level CODEOWNERS entry such as `@entireio/cli-maintainers` means
  CODEOWNERS alone may not reveal individual maintainers.
- Treat maintainers/internal org members as internal, not external contributors.
- For the target task, preserve the user's release-note goal, but verify the
  contributor classification before editing or reporting the Thanks section.

## Source Evidence Used

{sources}

## Repository Anchor

```text
{codeowners.strip()}
```

## Leakage Boundary

This memory was built for `{case.case_id}` from prior same-repo sessions only.
The target session `{case.session_id}` and its pushback text were not used as
source evidence for this memory.
"""


def codeowners_at_ref(repo_cache: Path, base_ref: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_cache),
            "show",
            f"{base_ref}:.github/CODEOWNERS",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else ""


def _decode_prefix_lines(lines: tuple[bytes, ...]) -> str:
    return "".join(line.decode("utf-8", errors="replace") for line in lines).strip()


def build_oracle_packet(case: EvalCase, data_dir: Path) -> OraclePacket:
    trajectory = original_trajectory(case, data_dir)
    history = history_prefix(case, data_dir)
    downstream_user_rows = (
        read_table("conversations", data_dir)
        .filter(
            (pl.col("session_id") == case.session_id)
            & (pl.col("turn_number") >= case.pushback_turn_number)
            & pl.col("is_conversational")
            & (pl.col("role") == "user")
        )
        .sort("turn_number")
        .select(["turn_number", "role", "content"])
        .head(8)
        .to_dicts()
    )
    return OraclePacket(
        history=_decode_prefix_lines(history.lines),
        instruction=case.instruction,
        original_action=json.dumps(trajectory, ensure_ascii=False, default=str),
        pushback=case.pushback,
        downstream_user_messages=json.dumps(
            downstream_user_rows, ensure_ascii=False, default=str
        ),
    )


def _install_rebased_transcript(bundle: Path, arm: str) -> dict[str, Any]:
    forks = bundle / "forks"
    manifest = json.loads((forks / "manifest.json").read_text(encoding="utf-8"))
    workspace = (forks / arm).resolve()
    transcript_path = Path(manifest[f"{arm}_rebased_transcript"]["output"]).resolve()
    project_key = str(workspace).replace("/", "-")
    claude_project = Path.home() / ".claude" / "projects" / project_key
    claude_project.mkdir(parents=True, exist_ok=True)
    installed = claude_project / f"{manifest['session_id']}.jsonl"
    shutil.copy2(transcript_path, installed)
    return {
        "workspace": str(workspace),
        "source_transcript": str(transcript_path),
        "installed_transcript": str(installed),
        "session_id": manifest["session_id"],
    }


def run_claude_candidate(
    bundle: Path,
    *,
    arm: str,
    instruction: str,
    model: str,
    max_budget_usd: float,
    timeout_seconds: int = 900,
) -> dict[str, Any]:
    """Run the candidate agent once through Claude Code CLI and capture artifacts."""

    installed = _install_rebased_transcript(bundle, arm)
    workspace = Path(installed["workspace"])
    before_digest = directory_digest(workspace)
    before_git = git_state(workspace)
    command = [
        "claude",
        "--resume",
        installed["session_id"],
        "--fork-session",
        "--print",
        instruction,
        "--setting-sources",
        "local",
        "--strict-mcp-config",
        "--no-chrome",
        "--disable-slash-commands",
        "--permission-mode",
        "bypassPermissions",
        "--tools",
        "default",
        "--model",
        model,
        "--max-budget-usd",
        str(max_budget_usd),
        "--output-format",
        "json",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        completed = subprocess.CompletedProcess(
            command,
            returncode=124,
            stdout=exc.stdout or "",
            stderr=exc.stderr or f"timed out after {timeout_seconds}s",
        )
        timed_out = True
    after_digest = directory_digest(workspace)
    after_git = git_state(workspace)
    diff = _run_capture(["git", "-C", str(workspace), "diff", "--binary"])
    status = _run_capture(["git", "-C", str(workspace), "status", "--short"])
    parsed: Any = None
    if completed.stdout.strip():
        try:
            parsed = json.loads(completed.stdout)
        except json.JSONDecodeError:
            parsed = None
    result_text = ""
    if isinstance(parsed, dict):
        result_text = str(parsed.get("result") or parsed.get("structured_output") or "")
    if not result_text:
        result_text = completed.stdout
    rendered = render_candidate_for_judge(
        arm=arm,
        result_text=result_text,
        stderr=completed.stderr,
    )
    debug_rendered = "\n".join(
        part
        for part in [
            f"CLAUDE ARM: {arm}",
            f"STDOUT/RESULT:\n{result_text}".strip(),
            f"STDERR:\n{completed.stderr}".strip() if completed.stderr else "",
            f"GIT STATUS:\n{status['stdout']}".strip(),
            f"GIT DIFF:\n{diff['stdout']}".strip(),
        ]
        if part
    )
    return {
        "schema_version": "claude-candidate-run-v1",
        "arm": arm,
        "ok": completed.returncode == 0,
        "timed_out": timed_out,
        "command": command,
        "cwd": str(workspace),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "parsed_output": parsed,
        "result_text": result_text,
        "rendered": rendered,
        "debug_rendered": debug_rendered,
        "diff": diff["stdout"],
        "status": status["stdout"],
        "workspace_sha256_before": before_digest,
        "workspace_sha256_after": after_digest,
        "git_state_before": before_git,
        "git_state_after": after_git,
        "model_requested": model,
        "max_budget_usd": max_budget_usd,
        "installed_transcript": installed,
    }


def render_candidate_for_judge(*, arm: str, result_text: str, stderr: str = "") -> str:
    """Render only the regenerated turn, excluding harness git state and diffs."""

    return "\n".join(
        part
        for part in [
            f"CLAUDE ARM: {arm}",
            f"STDOUT/RESULT:\n{result_text}".strip(),
            f"STDERR:\n{stderr}".strip() if stderr else "",
        ]
        if part
    )


def configure_dspy_lm(model: str) -> dspy.LM:
    adapter = dspy.XMLAdapter()
    dspy.settings.configure(adapter=adapter)
    return dspy.LM(
        model,
        model_type="responses",
        temperature=1.0,
        reasoning_effort="medium",
        cache=False,
        max_tokens=4096,
    )


async def score_with_dspy(
    *,
    oracle: OraclePacket,
    cold: dict[str, Any],
    warm: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    lm = configure_dspy_lm(model)
    rubric_generator = RubricGenerator(lm=lm)
    judge = Judge(lm=lm)
    rubric = await rubric_generator.generate(oracle)
    cold_candidate = CandidateAction(
        rendered=str(cold.get("rendered") or ""), diff=str(cold.get("diff") or "")
    )
    warm_candidate = CandidateAction(
        rendered=str(warm.get("rendered") or ""), diff=str(warm.get("diff") or "")
    )
    cold_score = await judge.score(
        oracle.history, oracle.instruction, cold_candidate, rubric
    )
    warm_score = await judge.score(
        oracle.history, oracle.instruction, warm_candidate, rubric
    )
    return {
        "schema_version": "dspy-xml-scoring-v1",
        "adapter": "XMLAdapter",
        "model": model,
        "temperature": 1.0,
        "reasoning_effort": "medium",
        "rubric": rubric.model_dump(),
        "cold": cold_score.model_dump(),
        "warm": warm_score.model_dump(),
        "lift": warm_score.score - cold_score.score,
        "reproduced": cold_score.score < 1.0,
        "rescued": cold_score.score < 1.0 and warm_score.score >= 1.0,
    }


def render_run_html(run: dict[str, Any]) -> str:
    payload = json.dumps(run, ensure_ascii=False, default=_json_default).replace(
        "</script", "<\\/script"
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SWE-chat Replay Smoke</title>
  <style>
    :root {{ color-scheme: light dark; font-family: ui-sans-serif, system-ui, sans-serif; }}
    body {{ margin: 0; background: #f7f7f4; color: #1f2933; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 28px; }}
    h1 {{ font-size: 28px; margin: 0 0 8px; }}
    h2 {{ font-size: 17px; margin: 0 0 10px; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; margin: 18px 0; }}
    .tile, section {{ background: #fff; border: 1px solid #d7d7d0; border-radius: 8px; padding: 14px; }}
    .tile b {{ display: block; font-size: 12px; color: #64707d; text-transform: uppercase; }}
    .tile span {{ font-size: 20px; font-weight: 700; }}
    section {{ margin: 12px 0; }}
    pre {{ overflow: auto; white-space: pre-wrap; background: #111827; color: #f9fafb; padding: 12px; border-radius: 6px; font-size: 12px; }}
    button {{ border: 1px solid #99a1aa; background: #eef2f5; padding: 6px 10px; border-radius: 6px; cursor: pointer; }}
    .stage {{ display: flex; justify-content: space-between; gap: 12px; align-items: center; }}
    .ok {{ color: #157347; }}
    .bad {{ color: #b42318; }}
  </style>
</head>
<body>
<main>
  <h1>SWE-chat Replay Smoke</h1>
  <div id="app"></div>
</main>
<script id="run-json" type="application/json">{payload}</script>
<script>
const run = JSON.parse(document.getElementById('run-json').textContent);
const app = document.getElementById('app');
const esc = (s) => String(s ?? '').replace(/[&<>]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]));
const score = run.scoring || {{}};
app.innerHTML = `
  <div class="summary">
    <div class="tile"><b>Case</b><span>${{esc(run.case?.case_id)}}</span></div>
    <div class="tile"><b>DSPy</b><span>${{esc(score.model || run.config?.dspy_model)}}</span></div>
    <div class="tile"><b>Adapter</b><span>${{esc(score.adapter || 'XMLAdapter')}}</span></div>
    <div class="tile"><b>Lift</b><span>${{esc(score.lift ?? 'n/a')}}</span></div>
  </div>
  <section><h2>Stages</h2>${{(run.stages || []).map((s, i) => `
    <div class="stage"><span>${{i + 1}}. ${{esc(s.name)}}</span><code>${{esc(s.path)}}</code></div>
  `).join('')}}</section>
  <section><h2>Rubric / Scoring</h2><pre>${{esc(JSON.stringify(score, null, 2))}}</pre></section>
  <section><h2>Cold Candidate</h2><pre>${{esc(run.candidates?.cold?.rendered || '')}}</pre></section>
  <section><h2>Warm Candidate</h2><pre>${{esc(run.candidates?.warm?.rendered || '')}}</pre></section>
  <section><h2>Full Run JSON</h2><pre>${{esc(JSON.stringify(run, null, 2))}}</pre></section>
`;
</script>
</body>
</html>
"""


def write_html(output: Path, run: dict[str, Any]) -> Path:
    path = output / "index.html"
    path.write_text(render_run_html(run), encoding="utf-8")
    return path


def run_smoke(
    *,
    output: Path,
    data_dir: Path = Path("data/swe-chat"),
    repo_cache: Path = Path("data/repos/entireio-cli.git"),
    session_id: str = DEFAULT_SESSION_ID,
    pushback_turn: int = DEFAULT_PUSHBACK_TURN,
    base_ref: str = DEFAULT_BASE_REF,
    dspy_model: str = DEFAULT_DSPY_MODEL,
    claude_model: str = DEFAULT_CLAUDE_MODEL,
    claude_max_budget_usd: float = 2.0,
    run_claude: bool = True,
    run_dspy: bool = True,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    stages: list[dict[str, Any]] = []

    def record(index: int, name: str, data: Any) -> Any:
        path = write_stage(output, index, name, data)
        stages.append({"index": index, "name": name, "path": str(path)})
        return data

    deps = record(
        1,
        "dependencies",
        dependency_report(
            data_dir=data_dir,
            repo_cache=repo_cache,
            base_ref=base_ref,
            dspy_model=dspy_model,
            claude_model=claude_model,
        ),
    )
    case = case_for_pushback(session_id, pushback_turn, data_dir)
    record(2, "case", asdict(case))
    record(3, "audit", audit_replay(case, data_dir))
    bundle = output / "bundle"
    write_case_bundle(case, bundle, data_dir)
    history = history_prefix(case, data_dir)
    record(
        4,
        "reentry_context",
        {
            "history_sha256": history.sha256,
            "history_line_count": history.line_count,
            "instruction": case.instruction,
            "candidate_context_excludes": [
                "original_action",
                "pushback",
                "downstream",
                "rubric",
            ],
        },
    )
    oracle = build_oracle_packet(case, data_dir)
    record(5, "oracle_packet", oracle.model_dump())
    source_rows = prior_memory_source_rows(case, data_dir)
    codeowners = codeowners_at_ref(repo_cache, base_ref)
    memory = format_learned_memory(case, source_rows=source_rows, codeowners=codeowners)
    memory_path = output / "learned-memory.md"
    memory_path.write_text(memory, encoding="utf-8")
    record(
        6,
        "memory",
        {
            "memory_path": str(memory_path),
            "sha256": sha256(memory.encode()).hexdigest(),
            "target": "CLAUDE.md",
            "source_rows": source_rows,
            "source_row_count": len(source_rows),
            "target_session_excluded": all(
                row.get("session_id") != case.session_id for row in source_rows
            ),
        },
    )
    fork_result: dict[str, Any] | None = None
    if deps["repo_cache_present"] and deps["base_ref_available"]:
        fork_result = materialize_fork_pair(
            bundle,
            repo_cache,
            base_ref,
            allow_exploratory=True,
            memory=memory_path,
            memory_target=Path("CLAUDE.md"),
            append_memory=True,
            data_dir=data_dir,
        )
    record(7, "fork_pair", fork_result or {"ok": False, "reason": "missing repo cache"})

    canaries: dict[str, Any] = {}
    if fork_result and run_claude:
        for arm in ("cold", "warm"):
            try:
                canaries[arm] = run_claude_reentry_canary(
                    bundle, arm=arm, model=claude_model, max_budget_usd=0.30
                )
            except Exception as exc:  # pragma: no cover - integration path
                canaries[arm] = {"passed": False, "error": str(exc)}
    record(8, "reentry_canaries", canaries)

    candidates: dict[str, Any] = {}
    if fork_result and run_claude and all(
        canaries.get(arm, {}).get("passed") for arm in ("cold", "warm")
    ):
        for arm in ("cold", "warm"):
            candidates[arm] = run_claude_candidate(
                bundle,
                arm=arm,
                instruction=case.instruction,
                model=claude_model,
                max_budget_usd=claude_max_budget_usd,
            )
    else:
        candidates = {
            "cold": {"ok": False, "rendered": "", "reason": "candidate run skipped"},
            "warm": {"ok": False, "rendered": "", "reason": "candidate run skipped"},
        }
    record(9, "candidates", candidates)

    scoring: dict[str, Any] = {}
    if run_dspy and candidates.get("cold") and candidates.get("warm"):
        if candidates["cold"].get("rendered") and candidates["warm"].get("rendered"):
            try:
                scoring = asyncio.run(
                    score_with_dspy(
                        oracle=oracle,
                        cold=candidates["cold"],
                        warm=candidates["warm"],
                        model=dspy_model,
                    )
                )
            except Exception as exc:  # pragma: no cover - integration path
                scoring = {
                    "schema_version": "dspy-xml-scoring-v1",
                    "adapter": "XMLAdapter",
                    "model": dspy_model,
                    "ok": False,
                    "error": str(exc),
                }
        else:
            scoring = {
                "schema_version": "dspy-xml-scoring-v1",
                "adapter": "XMLAdapter",
                "model": dspy_model,
                "ok": False,
                "reason": "candidate action missing",
            }
    record(10, "dspy_scoring", scoring)

    run = {
        "schema_version": SMOKE_SCHEMA_VERSION,
        "config": {
            "data_dir": str(data_dir),
            "repo_cache": str(repo_cache),
            "base_ref": base_ref,
            "dspy_model": dspy_model,
            "dspy_temperature": 1.0,
            "dspy_reasoning_effort": "medium",
            "dspy_adapter": "XMLAdapter",
            "claude_model": claude_model,
            "claude_max_budget_usd": claude_max_budget_usd,
        },
        "case": asdict(case),
        "stages": stages,
        "candidates": candidates,
        "scoring": scoring,
        "artifact_paths": {
            "run_json": str(output / "run.json"),
            "html": str(output / "index.html"),
            "bundle": str(bundle),
            "memory": str(memory_path),
        },
    }
    write_json(output / "run.json", run)
    write_html(output, run)
    return run
