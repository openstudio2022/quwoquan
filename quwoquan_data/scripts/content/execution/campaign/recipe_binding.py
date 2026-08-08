"""Narrow task-recipe bridge for immutable campaign inputs."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from content.execution.campaign.external_input_runtime import (
    bind_runtime_external_input_context,
    resolve_runtime_external_input_context,
)
from content.execution.campaign.request_envelope import load_campaign_envelope
from content.execution.campaign.submission import write_submission
from core.paths import OUTPUT_ROOT


def submit_campaign_lane(
    args: Any,
    *,
    identity: Any,
    runtime_request: Any,
    root_execution_id: str,
) -> Path:
    try:
        envelope_value = str(
            getattr(args, "campaign_envelope", "") or ""
        ).strip()
        campaign_envelope = (
            load_campaign_envelope(Path(envelope_value).expanduser().resolve())
            if envelope_value
            else None
        )
        preflight_value = str(
            getattr(args, "semantic_preflight_receipt", "") or ""
        ).strip()
        preflight_path = Path(preflight_value).expanduser() if preflight_value else None
        if preflight_path is not None and not preflight_path.is_absolute():
            preflight_path = OUTPUT_ROOT / preflight_path
        return write_submission(
            root_execution_id=root_execution_id,
            execution_id=identity.execution_id,
            request=runtime_request,
            retry_of=str(getattr(args, "retry_of", "") or "").strip() or None,
            campaign_envelope=campaign_envelope,
            semantic_selection_id=(
                str(getattr(args, "semantic_selection_id", "") or "").strip()
                or None
            ),
            semantic_preflight_receipt=preflight_path,
        )
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        subprocess.SubprocessError,
    ) as exc:
        raise SystemExit(
            f"[task execute] GATE_BLOCK campaign submission: {exc}"
        ) from exc


def require_campaign_external_inputs(identity: Any) -> None:
    try:
        bind_runtime_external_input_context(
            resolve_runtime_external_input_context(
                identity.execution_id,
                identity.content_type.value,
            )
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise SystemExit(
            f"[task execute] GATE_BLOCK campaign external inputs: {exc}"
        ) from exc


__all__ = ["require_campaign_external_inputs", "submit_campaign_lane"]
