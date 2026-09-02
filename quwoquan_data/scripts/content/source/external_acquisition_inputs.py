"""Typed campaign-capsule projections for acquired image and video inputs.

This seam accepts only an already validated runtime context.  It never reads
environment variables, scans acquisition directories, or performs network I/O.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from content.execution.campaign.external_input_runtime import (
        ExternalInputRuntimeContext,
    )


def external_input_error(code: str, detail: str) -> ValueError:
    from content.execution.source_pool.external_inputs import CampaignExternalInputError

    return CampaignExternalInputError(
        f"DATA.CAMPAIGN.EXTERNAL_INPUT_{code}",
        detail,
    )


def _required_context(
    execution_id: str,
    carrier: str,
    explicit: ExternalInputRuntimeContext | None,
) -> ExternalInputRuntimeContext:
    context = explicit
    if context is None:
        from content.execution.campaign.external_input_runtime import (
            bound_runtime_external_input_context,
        )

        context = bound_runtime_external_input_context(execution_id, carrier)
    if context is None:
        raise external_input_error(
            "UNBOUND",
            f"{carrier} acquisition receipt refs require a canonical capsule context",
        )
    if (
        context.envelope.get("executionId") != execution_id
        or context.envelope.get("carrier") != carrier
    ):
        raise external_input_error(
            "IDENTITY_DRIFT",
            f"{carrier} external input context drift",
        )
    return context


def _receipt_refs(data: object, *, media_kind: str) -> list[str]:
    if not isinstance(data, dict):
        return []
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    if "acquisitionReceiptRefs" in payload:
        raise ValueError(
            f"{media_kind} acquisitionReceiptRefs must use the canonical top-level field"
        )
    raw = data.get("acquisitionReceiptRefs") or []
    if not raw:
        return []
    if not isinstance(raw, list) or not all(
        isinstance(item, str) and item.strip() for item in raw
    ):
        raise ValueError(
            f"{media_kind} acquisitionReceiptRefs must be a non-empty string list"
        )
    return [str(item).strip() for item in raw]


def professional_video_plan_binding(
    data: object,
    *,
    execution_id: str,
    external_input_context: ExternalInputRuntimeContext | None,
) -> tuple[list[str], Path | None]:
    """Resolve an exact video receipt set and its frozen capsule root."""
    requested = _receipt_refs(data, media_kind="video")
    if not requested:
        return [], None
    from content.execution.source_pool.external_inputs import (
        PROFESSIONAL_VIDEO_ACQUISITION_KIND,
    )

    context = _required_context(execution_id, "video", external_input_context)
    refs = context.require_receipt_refs(
        PROFESSIONAL_VIDEO_ACQUISITION_KIND,
        requested,
    )
    return refs, context.acquisition_root(PROFESSIONAL_VIDEO_ACQUISITION_KIND)


def professional_video_context_binding(
    external_input_context: ExternalInputRuntimeContext | None,
) -> tuple[list[str], Path | None]:
    """Return the complete frozen video receipt set, when one is declared."""
    if external_input_context is None:
        return [], None
    from content.execution.source_pool.external_inputs import (
        PROFESSIONAL_VIDEO_ACQUISITION_KIND,
    )

    if not external_input_context.has_kind(PROFESSIONAL_VIDEO_ACQUISITION_KIND):
        return [], None
    refs = external_input_context.receipt_refs(PROFESSIONAL_VIDEO_ACQUISITION_KIND)
    return refs, external_input_context.acquisition_root(
        PROFESSIONAL_VIDEO_ACQUISITION_KIND
    )


def professional_image_context_enabled(
    external_input_context: ExternalInputRuntimeContext | None,
    selected_lanes: set[str],
) -> bool:
    """Detect the governed image input and reject cross-carrier consumption."""
    if external_input_context is None:
        return False
    kind = _professional_image_kind()
    enabled = external_input_context.has_kind(kind)
    if enabled and not selected_lanes <= {"homepage", "image"}:
        raise external_input_error(
            "INVALID",
            "professional image acquisition is admitted only for homepage/image lanes",
        )
    return enabled


def professional_image_specs_from_plan(
    data: object,
    *,
    execution_id: str,
    entity_id: str,
    carrier: str,
    external_input_context: ExternalInputRuntimeContext | None,
) -> list[dict[str, Any]]:
    """Project exact frozen image receipts into ordinary source-plan specs."""
    requested = _receipt_refs(data, media_kind="image")
    if not requested:
        if (
            external_input_context is not None
            and external_input_context.has_kind(_professional_image_kind())
        ):
            raise external_input_error(
                "UNDECLARED",
                "image source plan omitted the frozen acquisition receipt set",
            )
        return []
    refs, specs = professional_image_context_binding(
        execution_id=execution_id,
        entity_id=entity_id,
        carrier=carrier,
        external_input_context=external_input_context,
    )
    context = _required_context(execution_id, carrier, external_input_context)
    context.require_receipt_refs(
        _professional_image_kind(),
        requested,
    )
    if refs != requested:
        raise external_input_error(
            "UNDECLARED",
            "image source plan must bind the complete frozen receipt set",
        )
    return specs


def _professional_image_kind() -> str:
    from content.execution.source_pool.external_inputs import (
        PROFESSIONAL_IMAGE_ACQUISITION_KIND,
    )

    return PROFESSIONAL_IMAGE_ACQUISITION_KIND


def professional_image_context_binding(
    *,
    execution_id: str,
    entity_id: str,
    carrier: str,
    external_input_context: ExternalInputRuntimeContext | None,
    entity_aliases: tuple[str, ...] = (),
    verified_index: Any | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Project one lane's complete frozen image receipt set for one entity."""
    from content.source.professional_image_acquisition_index import (
        build_acquired_image_spec_index,
    )

    context = _required_context(execution_id, carrier, external_input_context)
    kind = _professional_image_kind()
    refs = context.receipt_refs(kind)
    context.require_receipt_refs(kind, refs)
    index = verified_index or build_acquired_image_spec_index(
        refs,
        root=context.acquisition_root(kind),
        descriptors=context.descriptors(kind),
    )
    specs = index.specs_for_names(
        tuple(dict.fromkeys([entity_id, *entity_aliases]))
    )
    for spec in specs:
        spec["url"] = context.blob_path(
            str(spec.get("contentSha256") or "")
        ).as_uri()
    return refs, specs


__all__ = [
    "external_input_error",
    "professional_image_context_binding",
    "professional_image_context_enabled",
    "professional_image_specs_from_plan",
    "professional_video_context_binding",
    "professional_video_plan_binding",
]
