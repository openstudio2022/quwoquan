"""Adopt one independently reviewed professional asset into immutable closure."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
)
from content.source.independent_asset_review import (
    IndependentAssetReviewError,
    assert_asset_review_accepted,
    load_independent_asset_review_receipt,
)
from content.source.independent_asset_review_contract import (
    canonical_digest,
    file_digest,
)
from core.io import read_json
from core.source_digest import content_source_revision


def _output_root(execution_root: Path) -> Path:
    resolved = execution_root.resolve()
    if resolved.parent.name != "tasks" or resolved.parent.parent.name != "data":
        raise ObjectTransactionError(
            "professional asset execution root must be QWQ_OUTPUT_ROOT/data/tasks/<executionId>"
        )
    return resolved.parent.parent.parent


def _execution_source_identity(
    source_identity: Mapping[str, Any],
) -> tuple[str, str, str]:
    required = ("sourceRevision", "sourceDigest", "entityCatalogDigest")
    values = tuple(str(source_identity.get(field) or "").strip() for field in required)
    try:
        expected_revision = content_source_revision(
            source_digest=values[1],
            entity_catalog_digest=values[2],
        )
    except ValueError as exc:
        raise ObjectTransactionError(str(exc)) from exc
    if expected_revision != values[0]:
        raise ObjectTransactionError(
            "professional asset execution source identity drift"
        )
    return values


def _one_value(values: Sequence[object], *, label: str) -> str:
    normalized = {
        str(value or "").strip() for value in values if str(value or "").strip()
    }
    if len(normalized) != 1:
        raise ObjectTransactionError(
            f"professional asset {label} is missing or ambiguous"
        )
    return next(iter(normalized))


def _professional_identity(
    raw: Mapping[str, Any],
    related_sources: Sequence[Mapping[str, Any]],
    *,
    asset_kind: str,
) -> tuple[str, str, str] | None:
    rows = (raw, *related_sources)
    receipt_field = (
        "acquisitionReceiptRef"
        if asset_kind == "image"
        else "professionalAcquisitionReceiptRef"
    )
    professional_rows = tuple(
        row for row in rows if str(row.get(receipt_field) or "").strip()
    )
    if not professional_rows:
        return None
    receipt_values = [row.get(receipt_field) for row in professional_rows]
    asset_values = [row.get("professionalAssetId") for row in professional_rows]
    digest_values = [row.get("professionalContentSha256") for row in professional_rows]
    receipt_ref = _one_value(receipt_values, label="acquisitionReceiptRef")
    asset_id = _one_value(asset_values, label="professionalAssetId")
    content_sha256 = _one_value(digest_values, label="professionalContentSha256")
    relative = Path(receipt_ref)
    if (
        relative.is_absolute()
        or len(relative.parts) < 2
        or relative.parts[-2] != "receipts"
        or relative.suffix != ".json"
        or ".." in relative.parts
        or (asset_kind == "video" and len(relative.parts) != 2)
    ):
        raise ObjectTransactionError(
            "professional asset acquisitionReceiptRef is non-canonical"
        )
    if not content_sha256.startswith("sha256:") or len(content_sha256) != 71:
        raise ObjectTransactionError("professional asset contentSha256 is invalid")
    return receipt_ref, asset_id, content_sha256


def build_independent_asset_review_binding(
    receipt: Mapping[str, Any],
    *,
    receipt_ref: str,
    receipt_file_sha256: str,
) -> dict[str, Any]:
    snapshot = receipt["assetSnapshot"]
    reviewer = receipt["reviewerExecution"]
    binding = {
        "reviewId": str(receipt["reviewId"]),
        "assetKind": str(receipt["assetKind"]),
        "objectRef": str(receipt["objectRef"]),
        "receiptRef": receipt_ref,
        "receiptDigest": str(receipt["receiptDigest"]),
        "receiptFileSha256": receipt_file_sha256,
        "sourceRevision": str(receipt["sourceRevision"]),
        "sourceDigest": str(receipt["sourceDigest"]),
        "entityCatalogDigest": str(receipt["entityCatalogDigest"]),
        "acquisitionReceiptRef": str(receipt["acquisitionReceiptRef"]),
        "acquisitionReceiptDigest": str(receipt["acquisitionReceiptDigest"]),
        "acquisitionReceiptSha256": str(receipt["acquisitionReceiptSha256"]),
        "acquisitionAssetId": str(snapshot["assetId"]),
        "contentSha256": str(snapshot["contentSha256"]),
        "casRef": str(snapshot["casRef"]),
        "reviewDecision": str(receipt["reviewDecision"]),
        "reviewer": {
            "provider": str(reviewer["provider"]),
            "model": str(reviewer["model"]),
            "runId": str(reviewer["runId"]),
        },
    }
    if receipt["assetKind"] == "video":
        binding.update(
            mediaProbeDigest=canonical_digest(snapshot["mediaProbe"]),
            popularitySignalsDigest=canonical_digest(snapshot["popularitySignals"]),
        )
    return binding


def adopt_independent_asset_review(
    *,
    raw_asset: Mapping[str, Any],
    related_sources: Sequence[Mapping[str, Any]],
    asset_kind: str,
    asset_id: str,
    content_sha256: str,
    object_ref: str,
    execution_root: Path,
    source_identity: Mapping[str, Any],
    object_root: Path,
) -> dict[str, Any] | None:
    """Bind one exact execution receipt without copying it into publish content."""

    identity = _professional_identity(raw_asset, related_sources, asset_kind=asset_kind)
    if identity is None:
        return None
    receipt_ref, acquisition_asset_id, acquired_sha256 = identity
    if asset_kind == "image" and acquired_sha256 != content_sha256:
        # 发布字节允许是执行内派生变体（如 WebP 压缩），但 asset 行必须显式声明
        # 派生自这份采集 CAS 内容；否则按字节漂移拒绝。video 的 transcode 同理豁免。
        declared = str(raw_asset.get("professionalContentSha256") or "").strip()
        if declared != acquired_sha256:
            raise ObjectTransactionError(
                "professional asset bytes drift from acquisition CAS"
            )
    output_root = _output_root(execution_root)
    acquisition_root_ref = "data/local/workspace/source-acquisition"
    expected_acquisition_ref = (
        f"{acquisition_root_ref}/video/{receipt_ref}"
        if asset_kind == "video"
        else f"{acquisition_root_ref}/{receipt_ref}"
    )
    expected_source_identity = _execution_source_identity(source_identity)
    source_digest = expected_source_identity[1]
    review_root = execution_root / "evidence/asset_reviews/receipts"
    candidates: list[Path] = []
    for path in sorted(review_root.glob("*.json")) if review_root.is_dir() else ():
        payload = read_json(path)
        snapshot = (
            payload.get("assetSnapshot") if isinstance(payload, Mapping) else None
        )
        if (
            isinstance(snapshot, Mapping)
            and payload.get("assetKind") == asset_kind
            and payload.get("objectRef") == object_ref
            and payload.get("acquisitionReceiptRef") == expected_acquisition_ref
            and snapshot.get("assetId") == acquisition_asset_id
            and snapshot.get("contentSha256") == acquired_sha256
        ):
            candidates.append(path)
    if len(candidates) != 1:
        raise ObjectTransactionError(
            "professional asset requires exactly one execution-local independent review: "
            f"asset={asset_id} matches={len(candidates)}"
        )
    source_path = candidates[0]
    try:
        receipt = load_independent_asset_review_receipt(
            source_path.relative_to(output_root).as_posix(),
            output_root=output_root,
        )
        assert_asset_review_accepted(
            receipt,
            content_sha256=acquired_sha256,
            source_digest=source_digest,
            asset_id=acquisition_asset_id,
        )
    except (IndependentAssetReviewError, OSError, ValueError) as exc:
        raise ObjectTransactionError(str(exc)) from exc
    actual_source_identity = (
        str(receipt["sourceRevision"]),
        str(receipt["sourceDigest"]),
        str(receipt["entityCatalogDigest"]),
    )
    if actual_source_identity != expected_source_identity:
        raise ObjectTransactionError(
            "professional asset independent review source identity drift"
        )
    if asset_kind == "video":
        professional_sources = [
            row
            for row in related_sources
            if str(row.get("professionalAcquisitionReceiptRef") or "").strip()
        ]
        snapshot = receipt["assetSnapshot"]
        if (
            len(professional_sources) != 1
            or professional_sources[0].get("professionalMediaProbe")
            != snapshot.get("mediaProbe")
            or professional_sources[0].get("popularitySignals")
            != snapshot.get("popularitySignals")
            or professional_sources[0].get("premiumPlayableEligible") is not True
        ):
            raise ObjectTransactionError(
                "professional video source-unit evidence drifts from independent review"
            )
    if (object_root / "asset_reviews").exists():
        raise ObjectTransactionError(
            "professional asset review evidence must not enter canonical object"
        )
    receipt_ref = source_path.relative_to(output_root).as_posix()
    return build_independent_asset_review_binding(
        receipt,
        receipt_ref=receipt_ref,
        receipt_file_sha256=file_digest(source_path),
    )


def validate_frozen_asset_review_binding(
    *,
    output_root: Path,
    object_ref: str,
    rights_asset: Mapping[str, Any],
    source_digest: str,
) -> dict[str, Any] | None:
    """Recheck the digest-bound execution receipt at release time."""

    acquisition_ref = str(rights_asset.get("acquisitionReceiptRef") or "").strip()
    raw_binding = rights_asset.get("independentAssetReview")
    if not acquisition_ref and raw_binding is None:
        return None
    if not acquisition_ref or not isinstance(raw_binding, Mapping):
        raise ObjectTransactionError(
            f"{object_ref}: professional asset review binding is incomplete"
        )
    receipt_ref = Path(str(raw_binding.get("receiptRef") or ""))
    if (
        receipt_ref.is_absolute()
        or ".." in receipt_ref.parts
        or len(receipt_ref.parts) != 7
        or receipt_ref.parts[:2] != ("data", "tasks")
        or receipt_ref.parts[3:6] != ("evidence", "asset_reviews", "receipts")
        or receipt_ref.suffix != ".json"
    ):
        raise ObjectTransactionError(
            f"{object_ref}: asset review receiptRef must name execution evidence"
        )
    receipt_path = output_root.resolve() / receipt_ref
    if not receipt_path.is_file() or receipt_path.is_symlink():
        raise ObjectTransactionError(
            f"{object_ref}: execution asset review receipt is missing"
        )
    if file_digest(receipt_path) != raw_binding.get("receiptFileSha256"):
        raise ObjectTransactionError(
            f"{object_ref}: execution asset review receipt bytes drift"
        )
    receipt = read_json(receipt_path)
    if not isinstance(receipt, dict):
        raise ObjectTransactionError(
            f"{object_ref}: execution asset review receipt is invalid"
        )
    # 复检对象是 receipt 冻结的采集内容（binding 与 receipt 的逐字段一致性在下方
    # build_independent_asset_review_binding 比对里另行校验）。发布物理字节允许是
    # 执行内派生（video transcode / image 变体），其完整性由 rights asset 的
    # sha256 与 CAS 键约束，不在此处比对。
    reviewed_content_sha256 = str(raw_binding.get("contentSha256") or "")
    try:
        assert_asset_review_accepted(
            receipt,
            content_sha256=reviewed_content_sha256,
            source_digest=source_digest,
            asset_id=str(raw_binding.get("acquisitionAssetId") or ""),
        )
    except (IndependentAssetReviewError, ValueError) as exc:
        raise ObjectTransactionError(str(exc)) from exc
    expected = build_independent_asset_review_binding(
        receipt,
        receipt_ref=receipt_ref.as_posix(),
        receipt_file_sha256=file_digest(receipt_path),
    )
    if dict(raw_binding) != expected:
        raise ObjectTransactionError(
            f"{object_ref}: independent asset review binding drift"
        )
    if (
        acquisition_ref != expected["acquisitionReceiptRef"]
        or expected["objectRef"] != object_ref
        or expected["sourceDigest"] != source_digest
        or expected["sourceRevision"]
        != content_source_revision(
            source_digest=expected["sourceDigest"],
            entity_catalog_digest=expected["entityCatalogDigest"],
        )
    ):
        raise ObjectTransactionError(
            f"{object_ref}: independent asset review identity drift"
        )
    return expected


__all__ = [
    "adopt_independent_asset_review",
    "build_independent_asset_review_binding",
    "validate_frozen_asset_review_binding",
]
