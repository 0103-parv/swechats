"""Candidate eval-case extraction.

This module intentionally keeps heuristics narrow. SWE-chat's published labels
are useful for filtering, but final eval cases still need human review.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import polars as pl

from swechats.data import read_table


PUSHBACK_VALUES = {"correction", "rejection"}


def _first_existing(columns: Iterable[str], candidates: Iterable[str]) -> str | None:
    available = set(columns)
    return next((candidate for candidate in candidates if candidate in available), None)


def pushback_label_column(df: pl.DataFrame) -> str | None:
    """Find the most likely pushback-label column in a conversations table."""

    return _first_existing(
        df.columns,
        [
            "user_pushback",
            "pushback",
            "pushback_label",
            "user_pushback_label",
            "annotation_user_pushback",
            "prompt_pushback",
        ],
    )


def repository_column(df: pl.DataFrame) -> str | None:
    """Find the most likely repository identifier column."""

    return _first_existing(
        df.columns,
        [
            "repo_id",
            "repository",
            "repo",
            "repo_name",
            "repository_name",
            "repository_full_name",
            "full_name",
        ],
    )


def session_column(df: pl.DataFrame) -> str | None:
    """Find the most likely session identifier column."""

    return _first_existing(
        df.columns,
        ["session_id", "session", "conversation_id", "transcript_id"],
    )


def candidate_pushbacks(
    data_dir: Path | str = "data/swe-chat",
    *,
    limit: int = 50,
    repo: str | None = None,
) -> pl.DataFrame:
    """Return correction/rejection rows from `conversations.parquet`.

    The output is a first-pass triage table, not a final benchmark. If the
    current dataset schema changes, this function raises a clear error so the
    caller can inspect schemas instead of silently producing nonsense.
    """

    conversations = read_table("conversations", data_dir)
    label_col = pushback_label_column(conversations)
    if label_col is None:
        raise ValueError(
            "Could not find a pushback label column in conversations.parquet. "
            "Run `swechats schema conversations` and update cases.py."
        )

    filtered = conversations.filter(pl.col(label_col).is_in(sorted(PUSHBACK_VALUES)))

    repo_col = repository_column(filtered)
    if repo and repo_col:
        filtered = filtered.filter(pl.col(repo_col) == repo)

    preferred = [
        column
        for column in [
            repo_col,
            session_column(filtered),
            "turn_id",
            "checkpoint_pk",
            "turn_index",
            "turn_number",
            "conversation_turn_number",
            "message_index",
            "role",
            "turn_type",
            "content",
            "text",
            "prompt_intent",
            label_col,
            "created_at",
            "timestamp",
        ]
        if column and column in filtered.columns
    ]
    if preferred:
        filtered = filtered.select(preferred)

    return filtered.head(limit)


def eval_cases(
    data_dir: Path | str = "data/swe-chat",
    *,
    repo: str,
    limit: int = 50,
    max_per_session: int = 3,
) -> pl.DataFrame:
    """Build explicit I/A/P eval cases from conversational turns.

    `P` is a user correction/rejection. `A` is the preceding assistant turn.
    `I` is the latest user turn before `A`. The chronological boundary is the
    current session timestamp plus the count of earlier same-repo sessions that
    are eligible as memory sources.
    """

    conversations = read_table("conversations", data_dir)
    sessions = read_table("sessions", data_dir)
    label_col = pushback_label_column(conversations)
    if label_col is None:
        raise ValueError(
            "Could not find a pushback label column in conversations.parquet. "
            "Run `swechats schema conversations` and update cases.py."
        )

    repo_sessions = (
        sessions.filter(pl.col("repo_id") == repo)
        .select(["session_id", "repo_id", "created_at", "user_id", "agent"])
        .sort("created_at")
        .with_row_index("repo_session_index")
    )
    session_meta = {
        row["session_id"]: row
        for row in repo_sessions.select(
            ["session_id", "created_at", "user_id", "agent", "repo_session_index"]
        ).to_dicts()
    }

    turns = (
        conversations.filter(
            (pl.col("repo_id") == repo)
            & (pl.col("is_conversational") == True)
            & pl.col("role").is_in(["user", "assistant"])
        )
        .select(
            [
                "repo_id",
                "session_id",
                "turn_id",
                "checkpoint_pk",
                "turn_number",
                "conversation_turn_number",
                "role",
                "turn_type",
                "content",
                "prompt_intent",
                label_col,
                "timestamp",
            ]
        )
        .sort(["session_id", "turn_number"])
    )

    rows: list[dict[str, object]] = []
    per_session: dict[str, int] = {}
    last_user_by_session: dict[str, dict[str, object]] = {}
    last_assistant_by_session: dict[str, dict[str, object]] = {}

    for turn in turns.to_dicts():
        session_id = str(turn["session_id"])
        role = turn["role"]
        label = turn.get(label_col)

        if role == "user" and label in PUSHBACK_VALUES:
            if per_session.get(session_id, 0) >= max_per_session:
                last_user_by_session[session_id] = turn
                continue

            instruction = last_user_by_session.get(session_id)
            action = last_assistant_by_session.get(session_id)
            meta = session_meta.get(session_id)
            if instruction and action and meta:
                rows.append(
                    {
                        "case_id": f"{turn['turn_id']}:{label}",
                        "repo_id": repo,
                        "session_id": session_id,
                        "session_created_at": meta["created_at"],
                        "repo_session_index": meta["repo_session_index"],
                        "eligible_prior_sessions": meta["repo_session_index"],
                        "user_id": meta["user_id"],
                        "agent": meta["agent"],
                        "checkpoint_pk": turn["checkpoint_pk"],
                        "i_turn_id": instruction["turn_id"],
                        "i_turn_number": instruction["turn_number"],
                        "i_content": instruction["content"],
                        "a_turn_id": action["turn_id"],
                        "a_turn_number": action["turn_number"],
                        "a_content": action["content"],
                        "p_turn_id": turn["turn_id"],
                        "p_turn_number": turn["turn_number"],
                        "p_content": turn["content"],
                        "prompt_intent": turn.get("prompt_intent"),
                        "prompt_pushback": label,
                    }
                )
                per_session[session_id] = per_session.get(session_id, 0) + 1

        if role == "user":
            last_user_by_session[session_id] = turn
        elif role == "assistant":
            last_assistant_by_session[session_id] = turn

        if len(rows) >= limit:
            break

    return pl.DataFrame(rows)


def conversation_window(
    data_dir: Path | str = "data/swe-chat",
    *,
    session_id: str,
    turn_number: int,
    before: int = 2,
    after: int = 1,
) -> pl.DataFrame:
    """Return conversational turns around a target turn number."""

    conversations = read_table("conversations", data_dir)
    session_turns = (
        conversations.filter(
            (pl.col("session_id") == session_id) & (pl.col("is_conversational") == True)
        )
        .sort("turn_number")
        .with_row_index("conversation_index")
    )
    target = session_turns.filter(pl.col("turn_number") == turn_number)
    if target.is_empty():
        return target.drop("conversation_index")

    target_index = target.select("conversation_index").item()
    wanted = session_turns.filter(
        (pl.col("conversation_index") >= target_index - before)
        & (pl.col("conversation_index") <= target_index + after)
    )

    preferred = [
        column
        for column in [
            "conversation_index",
            "repo_id",
            "session_id",
            "turn_id",
            "turn_number",
            "conversation_turn_number",
            "role",
            "turn_type",
            "content",
            "prompt_intent",
            "prompt_pushback",
            "timestamp",
        ]
        if column in wanted.columns
    ]
    return wanted.select(preferred).sort("turn_number")


def repo_session_counts(data_dir: Path | str = "data/swe-chat", *, limit: int = 25) -> pl.DataFrame:
    """Rank repositories by available sessions."""

    sessions = read_table("sessions", data_dir)
    repo_col = repository_column(sessions)
    if repo_col is None:
        raise ValueError(
            "Could not find a repository column in sessions.parquet. "
            "Run `swechats schema sessions` and update cases.py."
        )

    counts = (
        sessions.group_by(repo_col)
        .len(name="sessions")
        .sort("sessions", descending=True)
        .head(limit)
    )

    try:
        repositories = read_table("repositories", data_dir)
    except FileNotFoundError:
        return counts

    if "repo_id" in repositories.columns and repo_col == "repo_id":
        display_cols = [
            column
            for column in ["repo_id", "url", "name", "num_sessions", "license_type"]
            if column in repositories.columns
        ]
        return counts.join(repositories.select(display_cols), on="repo_id", how="left")

    return counts


def pushback_counts(data_dir: Path | str = "data/swe-chat") -> pl.DataFrame:
    """Count prompt pushback labels across the conversations table."""

    conversations = read_table("conversations", data_dir)
    label_col = pushback_label_column(conversations)
    if label_col is None:
        raise ValueError(
            "Could not find a pushback label column in conversations.parquet. "
            "Run `swechats schema conversations` and update cases.py."
        )

    return (
        conversations.select(label_col)
        .drop_nulls()
        .group_by(label_col)
        .len(name="count")
        .sort("count", descending=True)
    )
