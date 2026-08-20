"""Acquisition and judgment inputs for independent asset review."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.source.independent_asset_review_contract import (
    IndependentAssetReviewError,
    asset_snapshot,
    audited_path,
    file_digest,
)

_ACCEPTED_DECISIONS = {"research_allowed", "commercial_allowed"}
_POPULAR_BINDING_FIELDS = (
    "popularCandidateId", "popularCatalogRef", "popularCatalogDigest",
    "popularCatalogFileSha256",
)


def _asset_snapshot(
    asset: Mapping[str, Any],
    *,
    asset_kind: str,
) -> dict[str, Any]:
    snapshot = asset_snapshot(asset)
    if asset_kind != "video":
        return snapshot
    values = [str(asset.get(field) or "").strip() for field in _POPULAR_BINDING_FIELDS]
    if any(values) and not all(values):
        raise IndependentAssetReviewError(
            "video popular-catalog acquisition binding is incomplete"
        )
    if all(values):
        snapshot.update(zip(_POPULAR_BINDING_FIELDS, values, strict=True))
    return snapshot


def _author_evidence_issues(
    envelope: Mapping[str, Any],
    *,
    workspace_root: Path,
) -> list[str]:
    """Validate the author envelope without importing the execution package."""
    issues: list[str] = []
    agent = envelope.get("agent")
    if not isinstance(agent, Mapping) or any(
        not str(agent.get(field) or "").strip()
        for field in ("provider", "model", "runId", "promptSha256")
    ):
        issues.append("author agent identity is incomplete")
    for row in envelope.get("files") or []:
        if not isinstance(row, Mapping):
            issues.append("author file evidence is invalid")
            continue
        relative = Path(str(row.get("path") or ""))
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            issues.append("author file evidence path is unsafe")
            continue
        path = workspace_root / relative
        if not path.is_file() or file_digest(path) != row.get("sha256"):
            issues.append(f"author file evidence drift: {relative.as_posix()}")
    for gate in envelope.get("gates") or []:
        if not isinstance(gate, Mapping) or gate.get("final") is not True or gate.get(
            "decision"
        ) not in {"passed", "approved"}:
            issues.append("author gate is not final/passing")
    return issues


def _load_acquisition(
    path: Path,
    *,
    asset_kind: str,
    output_root: Path,
) -> tuple[dict[str, Any], str, str]:
    audited, ref = audited_path(
        path,
        output_root=output_root,
        label=f"{asset_kind} acquisition receipt",
    )
    if audited.parent.name != "receipts":
        raise IndependentAssetReviewError(
            f"{asset_kind} acquisition receipt path is not canonical: {audited}"
        )
    acquisition_root = audited.parent.parent
    receipt_ref = audited.relative_to(acquisition_root).as_posix()
    try:
        if asset_kind == "image":
            from content.source.professional_image_acquisition import (
                load_professional_image_acquisition_receipt,
            )
            receipt = load_professional_image_acquisition_receipt(
                receipt_ref,
                root=acquisition_root,
            )
        elif asset_kind == "video":
            from content.source.professional_video_receipt import (
                load_professional_video_acquisition_receipt,
            )

            receipt = load_professional_video_acquisition_receipt(
                receipt_ref,
                root=acquisition_root,
            )
        else:
            raise IndependentAssetReviewError(f"assetKind is unsupported: {asset_kind}")
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        if isinstance(exc, IndependentAssetReviewError):
            raise
        raise IndependentAssetReviewError(str(exc)) from exc
    return receipt, ref, file_digest(audited)


def _one_asset(receipt: Mapping[str, Any], *, asset_id: str) -> dict[str, Any]:
    matches = [
        dict(row)
        for row in receipt.get("assets") or []
        if isinstance(row, Mapping) and str(row.get("assetId") or "") == asset_id
    ]
    if len(matches) != 1:
        raise IndependentAssetReviewError(
            f"acquisition asset binding is missing or ambiguous: {asset_id}"
        )
    asset = matches[0]
    if asset.get("acquisitionStatus") != "acquired":
        raise IndependentAssetReviewError(f"asset was not acquired: {asset_id}")
    return asset


def _review_decision(
    judgment: Mapping[str, Any],
    *,
    snapshot: Mapping[str, Any],
    acquisition_safety: Mapping[str, Any],
) -> str:
    if judgment.get("rightsStatus") != snapshot.get("rightsStatus"):
        raise IndependentAssetReviewError("review rightsStatus cannot upgrade acquisition truth")
    if judgment.get("authorizationRequired") is not snapshot.get("authorizationRequired"):
        raise IndependentAssetReviewError(
            "review authorizationRequired cannot drift from acquisition truth"
        )
    accepted = (
        snapshot.get("distributionDecision") in _ACCEPTED_DECISIONS
        and judgment.get("distributionDecision") == snapshot.get("distributionDecision")
        and judgment.get("rightsStatus") in {"verified", "unverified", "unknown"}
        and judgment.get("safetyStatus") == "passed"
        and judgment.get("entityMatch") == "matched"
        and judgment.get("qualityStatus") == "passed"
        and judgment.get("privacyRisk") == "none"
        and judgment.get("minorRisk") == "none"
        and judgment.get("maliciousMediaRisk") == "none"
        and judgment.get("watermarkStatus") == "absent"
        and acquisition_safety.get("status") == "passed"
        and acquisition_safety.get("entityMatch") == "matched"
        and acquisition_safety.get("privacyRisk") == "none"
        and acquisition_safety.get("minorRisk") == "none"
        and acquisition_safety.get("maliciousMediaRisk") == "none"
        and acquisition_safety.get("watermarkStatus") == "absent"
    )
    if accepted:
        return "accepted"
    if judgment.get("distributionDecision") != "blocked":
        raise IndependentAssetReviewError(
            "a non-passing independent judgment must remain distributionDecision=blocked"
        )
    findings = [str(item).strip() for item in judgment.get("findings") or [] if str(item).strip()]
    if not findings:
        raise IndependentAssetReviewError("blocked independent judgment requires findings")
    return "blocked"


