"""Export helpers for hand-reviewed hackathon artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl


def write_jsonl(frame: pl.DataFrame, output: Path) -> Path:
    """Write a Polars frame as newline-delimited JSON."""

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in frame.to_dicts():
            handle.write(json.dumps(row, default=str, ensure_ascii=False))
            handle.write("\n")
    return output
