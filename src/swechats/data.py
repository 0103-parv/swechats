"""Thin data-loading helpers for SWE-chat parquet files."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from swechats.paths import SweChatPaths


def scan_table(name: str, data_dir: Path | str = "data/swe-chat") -> pl.LazyFrame:
    """Return a lazy scan for a SWE-chat parquet table."""

    paths = SweChatPaths.from_root(data_dir)
    return pl.scan_parquet(paths.require_table(name))


def read_table(
    name: str,
    data_dir: Path | str = "data/swe-chat",
    *,
    n_rows: int | None = None,
) -> pl.DataFrame:
    """Read a SWE-chat parquet table, optionally limiting rows."""

    paths = SweChatPaths.from_root(data_dir)
    return pl.read_parquet(paths.require_table(name), n_rows=n_rows)


def table_schema(name: str, data_dir: Path | str = "data/swe-chat") -> dict[str, str]:
    """Return a simple stringified schema for CLI display."""

    schema = scan_table(name, data_dir).collect_schema()
    return {column: str(dtype) for column, dtype in schema.items()}


def table_overview(data_dir: Path | str = "data/swe-chat") -> pl.DataFrame:
    """Summarize local parquet tables and transcript count."""

    paths = SweChatPaths.from_root(data_dir)
    rows: list[dict[str, object]] = []
    for path in paths.available_tables():
        try:
            schema = pl.scan_parquet(path).collect_schema()
            row_count = pl.scan_parquet(path).select(pl.len()).collect().item()
        except Exception as exc:  # pragma: no cover - defensive CLI path
            rows.append(
                {
                    "table": path.name,
                    "rows": None,
                    "columns": None,
                    "size_mb": round(path.stat().st_size / 1_000_000, 2),
                    "error": str(exc),
                }
            )
            continue

        rows.append(
            {
                "table": path.name,
                "rows": row_count,
                "columns": len(schema),
                "size_mb": round(path.stat().st_size / 1_000_000, 2),
                "error": "",
            }
        )

    rows.append(
        {
            "table": "transcripts/*.jsonl",
            "rows": paths.transcript_count(),
            "columns": None,
            "size_mb": None,
            "error": "",
        }
    )
    return pl.DataFrame(rows)
