"""Validate produce command results."""
from __future__ import annotations

from _common.schema import validate_result
from _common.stage_reports import iter_stage_envelopes


def validate_produce_results(task_id: str, batch_id: str) -> list[str]:
    """Validate produce outputs at each step（对象优先，经 stage_reports 枚举）。"""
    errors: list[str] = []

    for step in ("quality_analysis", "compose", "review", "reverse_extract"):
        envelopes = iter_stage_envelopes(task_id, batch_id, "produce", step)
        if not envelopes:
            errors.append(f"No {step} result files")
            continue

        for ref, envelope in envelopes:
            payload = envelope.get("payload", envelope)
            for error in validate_result(payload, "produce", step):
                errors.append(f"{ref}.json: {error}")

    return errors
