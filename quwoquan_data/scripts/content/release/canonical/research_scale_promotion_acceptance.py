"""Final-only Alpha M100 acceptance gate for M1000 promotion."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.execution.campaign.m100_alpha_acceptance import (
    M100AlphaAcceptanceError,
    bind_m100_alpha_acceptance,
    validate_m100_alpha_acceptance_binding,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
)


class ResearchScalePromotionAcceptanceError(ValueError):
    """The final M1000 product-stage acceptance proof is missing or drifting."""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _document_digest(document: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(document), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def validate_acceptance_input_mode(
    *,
    target_scale: str,
    predecessor_promotion_path: Path | None,
    readiness_receipt_path: Path | None,
    app_uat_receipt_path: Path | None,
    binding_path: Path | None,
) -> None:
    supplied = (
        readiness_receipt_path is not None
        or app_uat_receipt_path is not None
        or binding_path is not None
    )
    if target_scale != "M1000":
        if supplied:
            raise ResearchScalePromotionAcceptanceError(
                "DATA.SCALE.ALPHA_M100_ACCEPTANCE_UNEXPECTED: Alpha M100 "
                "acceptance only gates M1000 promotion"
            )
        return
    # Preserve the predecessor-specific error when the M100 receipt itself is
    # absent. Once it is explicit, fail before release/campaign IO if the
    # product acceptance evidence is missing.
    if predecessor_promotion_path is None:
        return
    if binding_path is not None and (
        readiness_receipt_path is not None or app_uat_receipt_path is not None
    ):
        raise ResearchScalePromotionAcceptanceError(
            "DATA.SCALE.ALPHA_M100_ACCEPTANCE_AMBIGUOUS: pass either one exact "
            "binding or the Alpha readiness and App UAT receipts"
        )
    if binding_path is None and (
        readiness_receipt_path is None or app_uat_receipt_path is None
    ):
        raise ResearchScalePromotionAcceptanceError(
            "DATA.SCALE.ALPHA_M100_ACCEPTANCE_MISSING: M1000 promotion requires "
            "the M100 promotion receipt plus Alpha activation/readback and "
            "100-case App UAT evidence"
        )


def _binding_file(
    path: Path, *, output_root: Path
) -> tuple[dict[str, Any], str, str]:
    root = output_root.expanduser().resolve()
    if path.expanduser().is_symlink():
        raise ResearchScalePromotionAcceptanceError(
            "M100 Alpha acceptance binding must not be a symlink"
        )
    try:
        resolved = path.expanduser().resolve(strict=True)
        ref = resolved.relative_to(root).as_posix()
    except (FileNotFoundError, ValueError) as exc:
        raise ResearchScalePromotionAcceptanceError(
            "M100 Alpha acceptance binding must be an existing file below "
            "QWQ_OUTPUT_ROOT"
        ) from exc
    return _read_json(resolved), ref, _file_sha256(resolved)


def bind_m1000_alpha_acceptance(
    *,
    target_scale: str,
    predecessor_promotion_path: Path | None,
    predecessor_reference: Mapping[str, Any] | None,
    readiness_receipt_path: Path | None,
    app_uat_receipt_path: Path | None,
    binding_path: Path | None,
    output_root: Path,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if target_scale != "M1000":
        return None, {}
    if predecessor_promotion_path is None or predecessor_reference is None:
        raise ResearchScalePromotionAcceptanceError(
            "DATA.SCALE.PREDECESSOR_IDENTITY_DRIFT: M1000 requires M100 promotion"
        )
    binding_source: dict[str, Any] = {}
    try:
        if binding_path is not None:
            raw_binding, binding_ref, binding_file_sha256 = _binding_file(
                binding_path, output_root=output_root
            )
            binding = validate_m100_alpha_acceptance_binding(
                raw_binding, output_root=output_root
            )
            binding_source = {
                "m100AlphaAcceptanceBindingRef": binding_ref,
                "m100AlphaAcceptanceBindingFileSha256": binding_file_sha256,
            }
        else:
            predecessor = _read_json(predecessor_promotion_path)
            binding = bind_m100_alpha_acceptance(
                readiness_receipt_path,
                app_uat_receipt_path,
                predecessor_promotion={**predecessor, **predecessor_reference},
                output_root=output_root,
            )
            # Re-read all three refs through the same exact-binding validator
            # used by consumers before freezing the result in the promotion.
            binding = validate_m100_alpha_acceptance_binding(
                binding, output_root=output_root
            )
    except (
        M100AlphaAcceptanceError,
        ObjectTransactionError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise ResearchScalePromotionAcceptanceError(str(exc)) from exc
    expected = {
        "promotionId": predecessor_reference.get("promotionId"),
        "promotionReceiptRef": predecessor_reference.get("receiptRef"),
        "promotionReceiptDigest": predecessor_reference.get("receiptDigest"),
        "releaseId": predecessor_reference.get("releaseId"),
        "manifestDigest": predecessor_reference.get("manifestDigest"),
    }
    if any(binding.get(field) != value for field, value in expected.items()):
        raise ResearchScalePromotionAcceptanceError(
            "DATA.SCALE.ALPHA_M100_ACCEPTANCE_DRIFT: binding does not prove the "
            "exact M100 predecessor promotion"
        )
    return binding, binding_source


def acceptance_binding_fields(
    binding: Mapping[str, Any], source_fields: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "m100AlphaAcceptanceBinding": dict(binding),
        "m100AlphaAcceptanceBindingDigest": _document_digest(binding),
        **dict(source_fields),
    }


__all__ = [
    "ResearchScalePromotionAcceptanceError",
    "acceptance_binding_fields",
    "bind_m1000_alpha_acceptance",
    "validate_acceptance_input_mode",
]
