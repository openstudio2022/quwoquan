"""Validate post command results."""
from __future__ import annotations

from core.schema import validate_result
from content.execution.stage_reports import iter_stage_envelopes


def validate_post_results(execution_id: str) -> list[str]:
    """Validate post outputs at each step（对象优先，经 stage_reports 枚举）。"""
    errors: list[str] = []

    for step in ("quality_analysis", "compose", "review", "reverse_extract"):
        envelopes = iter_stage_envelopes(execution_id, "post", step)
        if not envelopes:
            errors.append(f"No {step} result files")
            continue

        for ref, envelope in envelopes:
            payload = envelope.get("payload", envelope)
            for error in validate_result(payload, "content", step):
                errors.append(f"{ref}.json: {error}")

    return errors
