"""Path helpers for local SWE-chat data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_DATA_DIR = Path("data/swe-chat")


@dataclass(frozen=True)
class SweChatPaths:
    """Resolved paths for the local Hugging Face dataset mirror."""

    root: Path

    @classmethod
    def from_root(cls, root: Path | str = DEFAULT_DATA_DIR) -> SweChatPaths:
        return cls(Path(root))

    @property
    def transcripts_dir(self) -> Path:
        return self.root / "transcripts"

    def table(self, name: str) -> Path:
        filename = name if name.endswith(".parquet") else f"{name}.parquet"
        return self.root / filename

    def require_table(self, name: str) -> Path:
        path = self.table(name)
        if not path.exists():
            raise FileNotFoundError(
                f"Missing {path}. Download with: "
                "hf download SALT-NLP/SWE-chat --repo-type dataset "
                "--local-dir data/swe-chat"
            )
        return path

    def available_tables(self) -> list[Path]:
        return sorted(self.root.glob("*.parquet"))

    def transcript_count(self) -> int:
        if not self.transcripts_dir.exists():
            return 0
        return sum(1 for _ in self.transcripts_dir.glob("*.jsonl"))
