from __future__ import annotations

from swechats.dspysigs import Criterion, OraclePacket, _normalize_criterion_ids


def test_oracle_packet_uses_history_and_user_downstream_without_final_diff() -> None:
    packet = OraclePacket(
        history="prefix transcript",
        instruction="check contributors",
        original_action="bad action",
        pushback="that person is internal",
        downstream_user_messages="only thank @AlienKevin",
    )

    dumped = packet.model_dump()

    assert dumped["history"] == "prefix transcript"
    assert dumped["downstream_user_messages"] == "only thank @AlienKevin"
    assert "accepted_outcome" not in dumped
    assert "downstream" not in dumped


def test_normalize_criterion_ids_rejects_referential_set_criteria() -> None:
    criteria, failures = _normalize_criterion_ids(
        [
            Criterion(
                id=99,
                requirement=(
                    "Updates the changelog Thanks section so that it acknowledges "
                    "only the external contributor set for 0.4.6."
                ),
                rationale="The Thanks section should use the right set.",
            ),
            Criterion(
                id=100,
                requirement=(
                    "Identifies @AlienKevin as the only external contributor for "
                    "0.4.6 and excludes @gtrrz-victor, @pfleidi, and @toothbrush."
                ),
                rationale="This names the exact set and false positives.",
                admission_condition=(
                    "Candidate explicitly says only @AlienKevin is external."
                ),
            ),
        ]
    )

    assert [criterion.id for criterion in criteria] == [0]
    assert criteria[0].requirement.startswith("Identifies @AlienKevin")
    assert failures
    assert "external contributor set" in failures[0]
