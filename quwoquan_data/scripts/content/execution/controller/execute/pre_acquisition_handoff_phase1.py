"""Phase-one external-input binding for pre-acquisition handoffs."""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from .pre_acquisition_handoff_document import _typed


def validate_carrier_phase1_requirements(
    handoff: Mapping[str, Any],
    *,
    carrier: str,
    external_input_refs: Iterable[Mapping[str, Any]],
) -> None:
    requirements = handoff.get("carrierRequirements")
    if not isinstance(requirements, Mapping) or carrier not in requirements:
        raise _typed("INVALID", f"missing carrier requirement: {carrier}")
    requirement = requirements[carrier]
    if not isinstance(requirement, Mapping):
        raise _typed("INVALID", f"invalid carrier requirement: {carrier}")
    required = tuple(requirement.get("requiredExternalInputKinds") or ())
    observed = tuple(
        str(row.get("kind") or "")
        for row in external_input_refs
        if isinstance(row, Mapping)
    )
    if not required:
        if observed:
            raise _typed(
                "ARTICLE_EXTERNAL_INPUT_FORBIDDEN",
                "article READY must derive from governed sourceUnit freeze",
            )
        return
    if not observed or any(kind not in required for kind in observed):
        raise _typed(
            "EXTERNAL_INPUT_REQUIRED",
            f"{carrier} requires phase1 inputs of kind {', '.join(required)}",
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
    bind_handoff: Callable[..., tuple[dict[str, Any], dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Freeze external refs only while their governed handoff identity matches."""
    from content.execution.campaign.external_inputs import bind_external_input_refs

    frozen = bind_external_input_refs(
        carrier,
        declarations,
        acquisition_root=acquisition_root,
        source_revision=source_revision,
        source_digest=source_digest,
        entity_catalog_digest=entity_catalog_digest,
    )
    handoff, binding = bind_handoff(
        handoff_ref,
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
        output_root=handoff_output_root,
    )
    validate_carrier_phase1_requirements(
        handoff,
        carrier=carrier,
        external_input_refs=frozen,
    )
    return frozen, binding
