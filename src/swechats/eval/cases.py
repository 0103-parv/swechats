"""Candidate eval-case extraction.

This module intentionally keeps heuristics narrow. SWE-chat's published labels
are useful for filtering, but final eval cases still need human review.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import polars as pl

from swechats.data import read_table, scan_table


PUSHBACK_VALUES = {'correction', 'rejection'}

DEFAULT_CASE_TEXT_CHARS = 4_000
DEFAULT_CHAT_TEXT_CHARS = 1_600


def _first_existing(columns: Iterable[str], candidates: Iterable[str]) -> str | None:
    available = set(columns)
    return next((candidate for candidate in candidates if candidate in available), None)


def pushback_label_column(df: pl.DataFrame) -> str | None:
    """Find the most likely pushback-label column in a conversations table."""

    return _first_existing(
        df.columns,
        [
            'user_pushback',
            'pushback',
            'pushback_label',
            'user_pushback_label',
            'annotation_user_pushback',
            'prompt_pushback',
        ],
    )


def repository_column(df: pl.DataFrame) -> str | None:
    """Find the most likely repository identifier column."""

    return _first_existing(
        df.columns,
        [
            'repo_id',
            'repository',
            'repo',
            'repo_name',
            'repository_name',
            'repository_full_name',
            'full_name',
        ],
    )


def session_column(df: pl.DataFrame) -> str | None:
    """Find the most likely session identifier column."""

    return _first_existing(
        df.columns,
        ['session_id', 'session', 'conversation_id', 'transcript_id'],
    )


def candidate_pushbacks(
    data_dir: Path | str = 'data/swe-chat',
    *,
    limit: int = 50,
    repo: str | None = None,
) -> pl.DataFrame:
    """Return correction/rejection rows from `conversations.parquet`.

    The output is a first-pass triage table, not a final benchmark. If the
    current dataset schema changes, this function raises a clear error so the
    caller can inspect schemas instead of silently producing nonsense.
    """

    conversations = read_table('conversations', data_dir)
    label_col = pushback_label_column(conversations)
    if label_col is None:
        raise ValueError(
            'Could not find a pushback label column in conversations.parquet. '
            'Run `swechats schema conversations` and update cases.py.'
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
            'turn_id',
            'checkpoint_pk',
            'turn_index',
            'turn_number',
            'conversation_turn_number',
            'message_index',
            'role',
            'turn_type',
            'content',
            'text',
            'prompt_intent',
            label_col,
            'created_at',
            'timestamp',
        ]
        if column and column in filtered.columns
    ]
    if preferred:
        filtered = filtered.select(preferred)

    return filtered.head(limit)


def eval_cases(
    data_dir: Path | str = 'data/swe-chat',
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

    conversations = read_table('conversations', data_dir)
    sessions = read_table('sessions', data_dir)
    label_col = pushback_label_column(conversations)
    if label_col is None:
        raise ValueError(
            'Could not find a pushback label column in conversations.parquet. '
            'Run `swechats schema conversations` and update cases.py.'
        )

    repo_sessions = (
        sessions
        .filter(pl.col('repo_id') == repo)
        .select(['session_id', 'repo_id', 'created_at', 'user_id', 'agent'])
        .sort('created_at')
        .with_row_index('repo_session_index')
    )
    session_meta = {
        row['session_id']: row
        for row in repo_sessions.select([
            'session_id',
            'created_at',
            'user_id',
            'agent',
            'repo_session_index',
        ]).to_dicts()
    }

    turns = (
        conversations
        .filter(
            (pl.col('repo_id') == repo)
            & (pl.col('is_conversational') == True)
            & pl.col('role').is_in(['user', 'assistant'])
        )
        .select([
            'repo_id',
            'session_id',
            'turn_id',
            'checkpoint_pk',
            'turn_number',
            'conversation_turn_number',
            'role',
            'turn_type',
            'content',
            'prompt_intent',
            label_col,
            'timestamp',
        ])
        .sort(['session_id', 'turn_number'])
    )

    rows: list[dict[str, object]] = []
    per_session: dict[str, int] = {}
    last_user_by_session: dict[str, dict[str, object]] = {}
    last_assistant_by_session: dict[str, dict[str, object]] = {}

    for turn in turns.to_dicts():
        session_id = str(turn['session_id'])
        role = turn['role']
        label = turn.get(label_col)

        if role == 'user' and label in PUSHBACK_VALUES:
            if per_session.get(session_id, 0) >= max_per_session:
                last_user_by_session[session_id] = turn
                continue

            instruction = last_user_by_session.get(session_id)
            action = last_assistant_by_session.get(session_id)
            meta = session_meta.get(session_id)
            if instruction and action and meta:
                rows.append({
                    'case_id': f'{turn["turn_id"]}:{label}',
                    'repo_id': repo,
                    'session_id': session_id,
                    'session_created_at': meta['created_at'],
                    'repo_session_index': meta['repo_session_index'],
                    'eligible_prior_sessions': meta['repo_session_index'],
                    'user_id': meta['user_id'],
                    'agent': meta['agent'],
                    'checkpoint_pk': turn['checkpoint_pk'],
                    'i_turn_id': instruction['turn_id'],
                    'i_turn_number': instruction['turn_number'],
                    'i_content': instruction['content'],
                    'a_turn_id': action['turn_id'],
                    'a_turn_number': action['turn_number'],
                    'a_content': action['content'],
                    'p_turn_id': turn['turn_id'],
                    'p_turn_number': turn['turn_number'],
                    'p_content': turn['content'],
                    'prompt_intent': turn.get('prompt_intent'),
                    'prompt_pushback': label,
                })
                per_session[session_id] = per_session.get(session_id, 0) + 1

        if role == 'user':
            last_user_by_session[session_id] = turn
        elif role == 'assistant':
            last_assistant_by_session[session_id] = turn

        if len(rows) >= limit:
            break

    return pl.DataFrame(rows)


def dataset_eval_cases(
    data_dir: Path | str = 'data/swe-chat',
    *,
    limit: int = 1_500,
    repo: str | None = None,
    min_prior_sessions: int = 5,
    max_per_repo: int = 120,
    max_per_session: int = 4,
    candidate_multiplier: int = 5,
    window_before: int = 2,
    window_after: int = 2,
    case_text_chars: int = DEFAULT_CASE_TEXT_CHARS,
    chat_text_chars: int = DEFAULT_CHAT_TEXT_CHARS,
) -> pl.DataFrame:
    """Build a compact, joined I/A/P artifact from the full dataset.

    This is the browser-facing dataset path. It scans parquet with Polars,
    selects a bounded set of real correction/rejection turns, then joins only
    the sessions needed to recover the prior user instruction, assistant action,
    and a small surrounding chat window. The output is intentionally JSONL-sized
    rather than a direct web dependency on the 1GB+ conversations table.
    """

    if limit <= 0:
        return pl.DataFrame()

    candidate_limit = max(limit * candidate_multiplier, limit)
    conversations = scan_table('conversations', data_dir)
    sessions = read_table('sessions', data_dir)
    label_col = _first_existing(
        conversations.collect_schema().names(),
        [
            'user_pushback',
            'pushback',
            'pushback_label',
            'user_pushback_label',
            'annotation_user_pushback',
            'prompt_pushback',
        ],
    )
    if label_col is None:
        raise ValueError(
            'Could not find a pushback label column in conversations.parquet. '
            'Run `swechats schema conversations` and update cases.py.'
        )

    candidate_expr = (
        (pl.col('role') == 'user')
        & (pl.col('is_conversational') == True)
        & pl.col(label_col).is_in(sorted(PUSHBACK_VALUES))
    )
    if repo:
        candidate_expr = candidate_expr & (pl.col('repo_id') == repo)

    candidate_rows = (
        conversations
        .filter(candidate_expr)
        .select([
            'repo_id',
            'session_id',
            'turn_id',
            'turn_number',
            'timestamp',
            label_col,
        ])
        .sort('timestamp')
        .head(candidate_limit)
        .collect()
        .to_dicts()
    )
    if not candidate_rows:
        return pl.DataFrame()

    wanted_turn_ids = {str(row['turn_id']) for row in candidate_rows}
    wanted_sessions = sorted({str(row['session_id']) for row in candidate_rows})
    session_meta = _session_meta(sessions)

    turns = (
        conversations
        .filter(
            pl.col('session_id').is_in(wanted_sessions)
            & (pl.col('is_conversational') == True)
            & pl.col('role').is_in(['user', 'assistant'])
        )
        .select([
            'repo_id',
            'session_id',
            'turn_id',
            'checkpoint_pk',
            'turn_number',
            'conversation_turn_number',
            'role',
            'turn_type',
            'content',
            'prompt_intent',
            label_col,
            'timestamp',
        ])
        .sort(['session_id', 'turn_number'])
        .collect()
    )

    turns_by_session: dict[str, list[dict[str, object]]] = {}
    for turn in turns.to_dicts():
        turns_by_session.setdefault(str(turn['session_id']), []).append(turn)

    rows_by_turn_id: dict[str, dict[str, object]] = {}
    for session_id, session_turns in turns_by_session.items():
        _collect_session_cases(
            session_id=session_id,
            session_turns=session_turns,
            session_meta=session_meta,
            wanted_turn_ids=wanted_turn_ids,
            rows_by_turn_id=rows_by_turn_id,
            label_col=label_col,
            min_prior_sessions=min_prior_sessions,
            window_before=window_before,
            window_after=window_after,
            case_text_chars=case_text_chars,
            chat_text_chars=chat_text_chars,
        )

    rows: list[dict[str, object]] = []
    per_repo: dict[str, int] = {}
    per_session: dict[str, int] = {}
    seen_case_ids: set[str] = set()

    for candidate in candidate_rows:
        turn_id = str(candidate['turn_id'])
        row = rows_by_turn_id.get(turn_id)
        if row is None:
            continue

        case_id = str(row['case_id'])
        if case_id in seen_case_ids:
            continue

        row_repo = str(row['repo_id'])
        row_session = str(row['session_id'])
        if per_repo.get(row_repo, 0) >= max_per_repo:
            continue
        if per_session.get(row_session, 0) >= max_per_session:
            continue

        rows.append(row)
        seen_case_ids.add(case_id)
        per_repo[row_repo] = per_repo.get(row_repo, 0) + 1
        per_session[row_session] = per_session.get(row_session, 0) + 1

        if len(rows) >= limit:
            break

    return pl.DataFrame(rows)


def conversation_window(
    data_dir: Path | str = 'data/swe-chat',
    *,
    session_id: str,
    turn_number: int,
    before: int = 2,
    after: int = 1,
) -> pl.DataFrame:
    """Return conversational turns around a target turn number."""

    conversations = read_table('conversations', data_dir)
    session_turns = (
        conversations
        .filter(
            (pl.col('session_id') == session_id) & (pl.col('is_conversational') == True)
        )
        .sort('turn_number')
        .with_row_index('conversation_index')
    )
    target = session_turns.filter(pl.col('turn_number') == turn_number)
    if target.is_empty():
        return target.drop('conversation_index')

    target_index = target.select('conversation_index').item()
    wanted = session_turns.filter(
        (pl.col('conversation_index') >= target_index - before)
        & (pl.col('conversation_index') <= target_index + after)
    )

    preferred = [
        column
        for column in [
            'conversation_index',
            'repo_id',
            'session_id',
            'turn_id',
            'turn_number',
            'conversation_turn_number',
            'role',
            'turn_type',
            'content',
            'prompt_intent',
            'prompt_pushback',
            'timestamp',
        ]
        if column in wanted.columns
    ]
    return wanted.select(preferred).sort('turn_number')


def _session_meta(sessions: pl.DataFrame) -> dict[str, dict[str, object]]:
    repo_sessions = (
        sessions
        .select(['session_id', 'repo_id', 'created_at', 'user_id', 'agent'])
        .sort(['repo_id', 'created_at'])
        .with_columns(
            pl.int_range(pl.len()).over('repo_id').alias('repo_session_index')
        )
    )
    return {
        str(row['session_id']): row
        for row in repo_sessions.select([
            'session_id',
            'repo_id',
            'created_at',
            'user_id',
            'agent',
            'repo_session_index',
        ]).to_dicts()
    }


def _collect_session_cases(
    *,
    session_id: str,
    session_turns: list[dict[str, object]],
    session_meta: dict[str, dict[str, object]],
    wanted_turn_ids: set[str],
    rows_by_turn_id: dict[str, dict[str, object]],
    label_col: str,
    min_prior_sessions: int,
    window_before: int,
    window_after: int,
    case_text_chars: int,
    chat_text_chars: int,
) -> None:
    meta = session_meta.get(session_id)
    if meta is None:
        return

    repo_session_index = int(meta['repo_session_index'])
    if repo_session_index < min_prior_sessions:
        return

    last_user_index: int | None = None
    last_assistant_index: int | None = None

    for index, turn in enumerate(session_turns):
        role = turn['role']
        label = turn.get(label_col)
        turn_id = str(turn['turn_id'])

        if role == 'user' and label in PUSHBACK_VALUES and turn_id in wanted_turn_ids:
            if last_user_index is not None and last_assistant_index is not None:
                instruction = session_turns[last_user_index]
                action = session_turns[last_assistant_index]
                if int(instruction['turn_number']) < int(action['turn_number']):
                    rows_by_turn_id[turn_id] = _make_eval_case_row(
                        pushback=turn,
                        instruction=instruction,
                        action=action,
                        session_turns=session_turns,
                        pushback_index=index,
                        instruction_index=last_user_index,
                        action_index=last_assistant_index,
                        meta=meta,
                        repo_session_index=repo_session_index,
                        label_col=label_col,
                        window_before=window_before,
                        window_after=window_after,
                        case_text_chars=case_text_chars,
                        chat_text_chars=chat_text_chars,
                    )

        if role == 'user':
            last_user_index = index
        elif role == 'assistant':
            last_assistant_index = index


def _make_eval_case_row(
    *,
    pushback: dict[str, object],
    instruction: dict[str, object],
    action: dict[str, object],
    session_turns: list[dict[str, object]],
    pushback_index: int,
    instruction_index: int,
    action_index: int,
    meta: dict[str, object],
    repo_session_index: int,
    label_col: str,
    window_before: int,
    window_after: int,
    case_text_chars: int,
    chat_text_chars: int,
) -> dict[str, object]:
    label = str(pushback[label_col])
    start = max(0, min(instruction_index, action_index, pushback_index) - window_before)
    stop = min(len(session_turns), pushback_index + window_after + 1)
    chat_window = [
        _chat_turn(
            turn,
            marker=_marker_for_turn(
                str(turn['turn_id']),
                instruction_id=str(instruction['turn_id']),
                action_id=str(action['turn_id']),
                pushback_id=str(pushback['turn_id']),
            ),
            max_chars=chat_text_chars,
        )
        for turn in session_turns[start:stop]
    ]

    return {
        'case_id': f'{pushback["turn_id"]}:{label}',
        'repo_id': pushback['repo_id'],
        'session_id': pushback['session_id'],
        'session_created_at': meta['created_at'],
        'repo_session_index': repo_session_index,
        'eligible_prior_sessions': repo_session_index,
        'user_id': meta['user_id'],
        'agent': meta['agent'],
        'checkpoint_pk': pushback['checkpoint_pk'],
        'i_turn_id': instruction['turn_id'],
        'i_turn_number': instruction['turn_number'],
        'i_content': _clip(str(instruction['content']), case_text_chars),
        'a_turn_id': action['turn_id'],
        'a_turn_number': action['turn_number'],
        'a_content': _clip(str(action['content']), case_text_chars),
        'p_turn_id': pushback['turn_id'],
        'p_turn_number': pushback['turn_number'],
        'p_content': _clip(str(pushback['content']), case_text_chars),
        'prompt_intent': pushback.get('prompt_intent') or 'other',
        'prompt_pushback': label,
        'chat_window': chat_window,
    }


def _chat_turn(
    turn: dict[str, object],
    *,
    marker: str | None,
    max_chars: int,
) -> dict[str, object]:
    return {
        'turn_id': turn['turn_id'],
        'turn_number': turn['turn_number'],
        'role': turn['role'],
        'turn_type': turn['turn_type'],
        'content': _clip(str(turn['content']), max_chars),
        'prompt_intent': turn.get('prompt_intent'),
        'prompt_pushback': turn.get('prompt_pushback'),
        'marker': marker,
    }


def _marker_for_turn(
    turn_id: str,
    *,
    instruction_id: str,
    action_id: str,
    pushback_id: str,
) -> str | None:
    if turn_id == instruction_id:
        return 'I'
    if turn_id == action_id:
        return 'A'
    if turn_id == pushback_id:
        return 'P'
    return None


def _clip(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return f'{value[: max_chars - 3].rstrip()}...'


def repo_session_counts(
    data_dir: Path | str = 'data/swe-chat', *, limit: int = 25
) -> pl.DataFrame:
    """Rank repositories by available sessions."""

    sessions = read_table('sessions', data_dir)
    repo_col = repository_column(sessions)
    if repo_col is None:
        raise ValueError(
            'Could not find a repository column in sessions.parquet. '
            'Run `swechats schema sessions` and update cases.py.'
        )

    counts = (
        sessions
        .group_by(repo_col)
        .len(name='sessions')
        .sort('sessions', descending=True)
        .head(limit)
    )

    try:
        repositories = read_table('repositories', data_dir)
    except FileNotFoundError:
        return counts

    if 'repo_id' in repositories.columns and repo_col == 'repo_id':
        display_cols = [
            column
            for column in ['repo_id', 'url', 'name', 'num_sessions', 'license_type']
            if column in repositories.columns
        ]
        return counts.join(repositories.select(display_cols), on='repo_id', how='left')

    return counts


def pushback_counts(data_dir: Path | str = 'data/swe-chat') -> pl.DataFrame:
    """Count prompt pushback labels across the conversations table."""

    conversations = read_table('conversations', data_dir)
    label_col = pushback_label_column(conversations)
    if label_col is None:
        raise ValueError(
            'Could not find a pushback label column in conversations.parquet. '
            'Run `swechats schema conversations` and update cases.py.'
        )

    return (
        conversations
        .select(label_col)
        .drop_nulls()
        .group_by(label_col)
        .len(name='count')
        .sort('count', descending=True)
    )
