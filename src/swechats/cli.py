"""Command line tools for local SWE-chat exploration."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from swechats.cases import (
    candidate_pushbacks,
    dataset_eval_cases,
    eval_cases,
    conversation_window,
    pushback_counts,
    repo_session_counts,
)
from swechats.corpus_audit import corpus_replay_audit
from swechats.data import table_overview, table_schema
from swechats.export import write_jsonl
from swechats.replay import (
    audit_replay,
    case_for_pushback,
    materialize_fork_pair,
    run_claude_reentry_canary,
    write_case_bundle,
)

app = typer.Typer(help="Explore local SWE-chat data.")
console = Console()


DataDir = Annotated[
    Path,
    typer.Option(
        "--data-dir",
        "-d",
        help="Local Hugging Face dataset directory.",
    ),
]


def _print_frame(frame) -> None:
    console.print(frame)


@app.command()
def overview(data_dir: DataDir = Path("data/swe-chat")) -> None:
    """Show local table sizes, row counts, and transcript count."""

    _print_frame(table_overview(data_dir))


@app.command()
def schema(table: str, data_dir: DataDir = Path("data/swe-chat")) -> None:
    """Print the schema for one parquet table."""

    rich_table = Table(title=f"{table}.parquet schema")
    rich_table.add_column("column")
    rich_table.add_column("dtype")
    for column, dtype in table_schema(table, data_dir).items():
        rich_table.add_row(column, dtype)
    console.print(rich_table)


@app.command("repo-counts")
def repo_counts(
    data_dir: DataDir = Path("data/swe-chat"),
    limit: Annotated[int, typer.Option("--limit", "-n")] = 25,
) -> None:
    """Rank repositories by session count."""

    _print_frame(repo_session_counts(data_dir, limit=limit))


@app.command("pushback-counts")
def pushback_count_table(data_dir: DataDir = Path("data/swe-chat")) -> None:
    """Count prompt pushback labels."""

    _print_frame(pushback_counts(data_dir))


@app.command("pushbacks")
def pushbacks(
    data_dir: DataDir = Path("data/swe-chat"),
    repo: Annotated[str | None, typer.Option("--repo")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n")] = 50,
) -> None:
    """Show first-pass correction/rejection candidate rows."""

    _print_frame(candidate_pushbacks(data_dir, repo=repo, limit=limit))


@app.command("export-pushbacks")
def export_pushbacks(
    output: Annotated[Path, typer.Argument(help="JSONL output path.")],
    data_dir: DataDir = Path("data/swe-chat"),
    repo: Annotated[str | None, typer.Option("--repo")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n")] = 100,
) -> None:
    """Export first-pass correction/rejection candidates for review."""

    path = write_jsonl(candidate_pushbacks(data_dir, repo=repo, limit=limit), output)
    console.print(f"Wrote {path}")


@app.command("eval-cases")
def build_eval_cases(
    output: Annotated[Path, typer.Argument(help="JSONL output path.")],
    repo: Annotated[str, typer.Option("--repo", help="Repository id, e.g. entireio/cli.")],
    data_dir: DataDir = Path("data/swe-chat"),
    limit: Annotated[int, typer.Option("--limit", "-n")] = 50,
    max_per_session: Annotated[int, typer.Option("--max-per-session")] = 3,
) -> None:
    """Export explicit I/A/P eval cases with chronology boundary metadata."""

    cases = eval_cases(data_dir, repo=repo, limit=limit, max_per_session=max_per_session)
    path = write_jsonl(cases, output)
    console.print(f"Wrote {len(cases)} eval cases to {path}")


@app.command("eval-cases-dataset")
def build_dataset_eval_cases(
    output: Annotated[Path, typer.Argument(help="JSONL output path.")],
    data_dir: DataDir = Path("data/swe-chat"),
    repo: Annotated[
        str | None,
        typer.Option("--repo", help="Optional repository id, e.g. entireio/cli."),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", "-n")] = 1_500,
    max_per_repo: Annotated[int, typer.Option("--max-per-repo")] = 120,
    max_per_session: Annotated[int, typer.Option("--max-per-session")] = 4,
    min_prior_sessions: Annotated[int, typer.Option("--min-prior-sessions")] = 5,
    candidate_multiplier: Annotated[int, typer.Option("--candidate-multiplier")] = 5,
    window_before: Annotated[int, typer.Option("--window-before")] = 2,
    window_after: Annotated[int, typer.Option("--window-after")] = 2,
) -> None:
    """Export joined I/A/P eval cases with compact real chat windows."""

    cases = dataset_eval_cases(
        data_dir,
        repo=repo,
        limit=limit,
        max_per_repo=max_per_repo,
        max_per_session=max_per_session,
        min_prior_sessions=min_prior_sessions,
        candidate_multiplier=candidate_multiplier,
        window_before=window_before,
        window_after=window_after,
    )
    path = write_jsonl(cases, output)
    console.print(f"Wrote {len(cases)} dataset eval cases to {path}")


@app.command("corpus-audit")
def corpus_audit(
    data_dir: DataDir = Path("data/swe-chat"),
    repo: Annotated[
        str | None,
        typer.Option("--repo", help="Audit a single repository id."),
    ] = None,
    top: Annotated[
        int,
        typer.Option("--top", help="Audit the top N repositories by session count."),
    ] = 5,
    examples: Annotated[int, typer.Option("--examples")] = 8,
) -> None:
    """Count replayability filters and Bash/heredoc blockers across the corpus."""

    console.print_json(
        data=corpus_replay_audit(data_dir, repo=repo, top=top, examples=examples)
    )


@app.command("window")
def window(
    session_id: Annotated[str, typer.Argument(help="SWE-chat session id.")],
    turn_number: Annotated[int, typer.Argument(help="Target turn number.")],
    data_dir: DataDir = Path("data/swe-chat"),
    before: Annotated[int, typer.Option("--before")] = 2,
    after: Annotated[int, typer.Option("--after")] = 1,
) -> None:
    """Show a conversation window around a target turn."""

    _print_frame(
        conversation_window(
            data_dir,
            session_id=session_id,
            turn_number=turn_number,
            before=before,
            after=after,
        )
    )


@app.command("replay-audit")
def replay_audit(
    session_id: Annotated[str, typer.Argument(help="SWE-chat session id.")],
    pushback_turn_number: Annotated[
        int, typer.Argument(help="Correction/rejection user turn number.")
    ],
    data_dir: DataDir = Path("data/swe-chat"),
) -> None:
    """Audit whether published artifacts can support a certified replay."""

    case = case_for_pushback(session_id, pushback_turn_number, data_dir)
    console.print_json(data=audit_replay(case, data_dir))


@app.command("case-bundle")
def case_bundle(
    session_id: Annotated[str, typer.Argument(help="SWE-chat session id.")],
    pushback_turn_number: Annotated[
        int, typer.Argument(help="Correction/rejection user turn number.")
    ],
    output: Annotated[Path, typer.Argument(help="Bundle output directory.")],
    data_dir: DataDir = Path("data/swe-chat"),
) -> None:
    """Write replay evidence and a correction-derived judge rubric."""

    case = case_for_pushback(session_id, pushback_turn_number, data_dir)
    path = write_case_bundle(case, output, data_dir)
    console.print(f"Wrote case bundle to {path}")


@app.command("fork-pair")
def fork_pair(
    bundle: Annotated[Path, typer.Argument(help="Existing case bundle directory.")],
    repo: Annotated[Path, typer.Argument(help="Local Git repository or bare cache.")],
    base_ref: Annotated[str, typer.Argument(help="Certified or exploratory base ref.")],
    allow_exploratory: Annotated[
        bool,
        typer.Option(
            "--allow-exploratory",
            help="Materialize a non-primary-eligible case as a labeled smoke test.",
        ),
    ] = False,
    memory: Annotated[
        Path | None,
        typer.Option("--memory", help="Memory file to inject only into the warm arm."),
    ] = None,
    memory_target: Annotated[
        Path,
        typer.Option("--memory-target", help="Warm-arm relative destination."),
    ] = Path("AGENTS.md"),
    append_memory: Annotated[
        bool,
        typer.Option(
            "--append-memory",
            help="Append memory as a marked section to an existing target.",
        ),
    ] = False,
    data_dir: DataDir = Path("data/swe-chat"),
) -> None:
    """Materialize and hash-check paired cold/warm repository states."""

    result = materialize_fork_pair(
        bundle,
        repo,
        base_ref,
        allow_exploratory=allow_exploratory,
        memory=memory,
        memory_target=memory_target,
        append_memory=append_memory,
        data_dir=data_dir,
    )
    console.print_json(data=result)


@app.command("reentry-canary")
def reentry_canary(
    bundle: Annotated[Path, typer.Argument(help="Existing materialized case bundle.")],
    arm: Annotated[str, typer.Argument(help="Arm to verify: cold or warm.")],
    model: Annotated[str, typer.Option("--model")] = "sonnet",
    max_budget_usd: Annotated[float, typer.Option("--max-budget-usd")] = 0.30,
) -> None:
    """Resume rebased native history and verify access to history and workspace."""

    result = run_claude_reentry_canary(
        bundle, arm=arm, model=model, max_budget_usd=max_budget_usd
    )
    console.print_json(data=result)


if __name__ == "__main__":
    app()
