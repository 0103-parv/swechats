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
from swechats.data import table_overview, table_schema
from swechats.export import write_jsonl

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


if __name__ == "__main__":
    app()
