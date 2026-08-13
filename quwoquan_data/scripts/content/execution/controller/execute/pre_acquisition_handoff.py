"""Canonical pre-acquisition handoff API and injectable policy seams."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .pre_acquisition_handoff_document import (
    HANDOFF_SCHEMA,
    PreAcquisitionHandoffError,
    _file_digest,
    bind_pre_acquisition_handoff,
    build_pre_acquisition_handoff,
    load_pre_acquisition_handoff,
    pre_acquisition_handoff_path,
    write_pre_acquisition_handoff,
)
from .pre_acquisition_handoff_identity import (
    guard_acquisition_source_identity as _guard_acquisition_source_identity,
)
from .pre_acquisition_handoff_external_inputs import (
    freeze_carrier_pre_acquisition_inputs as _freeze_carrier_pre_acquisition_inputs,
    validate_carrier_external_input_requirements,
)


def freeze_carrier_pre_acquisition_inputs(
    carrier: str,
    declarations: Iterable[Mapping[str, Any]],
    *,
    acquisition_root: Path,
    handoff_ref: Path | None,
    scale: str,
    vertical: str,
    scope: str,
    region_ref: str,
    topic: str | None,
    run_date: str,
    campaign_sequence: int,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    handoff_output_root: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Freeze external refs against the canonical handoff binding."""
    return _freeze_carrier_pre_acquisition_inputs(
        carrier,
        declarations,
        acquisition_root=acquisition_root,
        handoff_ref=handoff_ref,
        scale=scale,
        vertical=vertical,
        scope=scope,
        region_ref=region_ref,
        topic=topic,
        run_date=run_date,
        campaign_sequence=campaign_sequence,
        source_revision=source_revision,
        source_digest=source_digest,
        entity_catalog_digest=entity_catalog_digest,
        handoff_output_root=handoff_output_root,
        bind_handoff=bind_pre_acquisition_handoff,
    )


def guard_acquisition_source_identity(
    manifest: Mapping[str, Any],
    *,
    handoff_ref: Path | None,
    repo_root: Path | None = None,
    frozen_external_input: bool = False,
) -> dict[str, Any]:
    """Reject stale manifest/handoff identity before any receipt or CAS write."""
    del repo_root  # compatibility-only call shape; frozen admission never reads it.
    return _guard_acquisition_source_identity(
        manifest,
        handoff_ref=handoff_ref,
        frozen_external_input=frozen_external_input,
    )


__all__ = [
    "HANDOFF_SCHEMA",
    "PreAcquisitionHandoffError",
    "bind_pre_acquisition_handoff",
    "build_pre_acquisition_handoff",
    "freeze_carrier_pre_acquisition_inputs",
    "guard_acquisition_source_identity",
    "load_pre_acquisition_handoff",
    "pre_acquisition_handoff_path",
    "validate_carrier_external_input_requirements",
    "write_pre_acquisition_handoff",
]
