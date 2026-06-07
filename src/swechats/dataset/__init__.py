"""Local SWE-chat dataset access: paths, parquet tables, export."""

from swechats.dataset.export import write_jsonl
from swechats.dataset.paths import DEFAULT_DATA_DIR, SweChatPaths
from swechats.dataset.tables import read_table, scan_table, table_overview, table_schema

__all__ = [
    "DEFAULT_DATA_DIR",
    "SweChatPaths",
    "read_table",
    "scan_table",
    "table_overview",
    "table_schema",
    "write_jsonl",
]
