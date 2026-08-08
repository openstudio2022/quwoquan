"""Project and revalidate cumulative source-pool lineage for scale evidence."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.execution.campaign.source_pool_binding import (
    validate_capsule_scale_source_pool,
    validate_lane_source_pool_selection,
)
from content.release.canonical.campaign_scale_contract import (
    CARRIERS,
    CampaignScaleEvidenceError,
)
from content.release.canonical.object_transaction_contract import _read_json
from core.schema import assert_valid

_PREDECESSOR_SCALE = {"M1000": "M100", "M10000": "M1000"}


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(raw_ref: object, *, output_root: Path, label: str) -> Path:
    ref = Path(str(raw_ref or ""))
    if ref.is_absolute() or not ref.parts or ".." in ref.parts:
        raise CampaignScaleEvidenceError(f"{label} must be one safe output ref")
    path = (output_root / ref).resolve()
    try:
        path.relative_to(output_root.resolve())
    except ValueError as exc:
        raise CampaignScaleEvidenceError(
            f"{label} must remain below QWQ_OUTPUT_ROOT"
        ) from exc
    return path


def _validated(path: Path, area: str, schema: str, *, label: str) -> dict[str, Any]:
    value = _read_json(path)
    assert_valid(value, area, schema, label=label)
    return value


def _stable_capsule(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in manifest.items()
        if key not in {"capsuleDigest", "treeDigest"}
    }


def project_campaign_source_pool(
    *,
    plan: Mapping[str, Any],
    campaign_plan_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Project the exact plan/capsule source-pool selection into release evidence."""

    binding = plan.get("scaleSourcePool")
    selections = plan.get("laneSourcePoolSelections")
    if not isinstance(binding, Mapping) or not isinstance(selections, Mapping):
        raise CampaignScaleEvidenceError(
            "DATA.SOURCE.POOL_SHORTFALL: scale campaign lacks frozen source pool"
        )
    if any(
        binding.get(key) != plan.get(key)
        for key in ("sourceRevision", "sourceDigest", "entityCatalogDigest")
    ):
        raise CampaignScaleEvidenceError("campaign source-pool identity drift")
    report = _validated(
        campaign_plan_path.parent / "campaign_report.json",
        "execution",
        "content_campaign_report",
        label="scale campaign report",
    )
    report_lanes = report.get("lanes")
    if not isinstance(report_lanes, Mapping):
        raise CampaignScaleEvidenceError("scale campaign report lanes are missing")
    capsule_refs = {str(report_lanes[carrier].get("sourceCapsuleRef") or "") for carrier in CARRIERS}
    capsule_digests = {str(report_lanes[carrier].get("sourceCapsuleDigest") or "") for carrier in CARRIERS}
    if (
        len(capsule_refs) != 1
        or "" in capsule_refs
        or len(capsule_digests) != 1
        or "" in capsule_digests
        or report.get("rootExecutionId") != plan.get("rootExecutionId")
        or report.get("planDigest") != plan.get("planDigest")
        or report.get("sourceDigest") != plan.get("sourceDigest")
        or report.get("entityCatalogDigest") != plan.get("entityCatalogDigest")
        or any(report_lanes[carrier].get("sourceCapsuleReadOnly") is not True for carrier in CARRIERS)
    ):
        raise CampaignScaleEvidenceError("campaign source capsule binding drift")
    capsule_ref = capsule_refs.pop()
    capsule_digest = capsule_digests.pop()
    capsule_root = _resolve(capsule_ref, output_root=output_root, label="source capsule ref")
    manifest = _validated(
        capsule_root / ".qwq_campaign_capsule.json",
        "execution",
        "content_source_capsule",
        label="scale source capsule",
    )
    if (
        manifest.get("capsuleDigest") != capsule_digest
        or _digest(_stable_capsule(manifest)) != capsule_digest
        or manifest.get("scaleSourcePool") != binding
        or manifest.get("laneSourcePoolSelections") != selections
        or manifest.get("sourceRevision") != plan.get("sourceRevision")
        or manifest.get("sourceDigest") != plan.get("sourceDigest")
        or manifest.get("entityCatalogDigest") != plan.get("entityCatalogDigest")
    ):
        raise CampaignScaleEvidenceError("campaign source capsule manifest drift")
    snapshot_root = capsule_root / str(manifest.get("sourcePoolSnapshotRootRef"))
    try:
        validate_capsule_scale_source_pool(
            binding,
            snapshot_root=snapshot_root,
            lane_selections={
                carrier: dict(selections[carrier]) for carrier in CARRIERS
            },
            expected_snapshot_digest=str(manifest.get("sourcePoolSnapshotDigest")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CampaignScaleEvidenceError(
            f"campaign selected source-pool snapshot drift: {exc}"
        ) from exc
    plan_path = _resolve(binding.get("planRef"), output_root=output_root, label="source-pool plan ref")
    snapshot_plan = snapshot_root / "plan.json"
    physical_plan = _read_json(plan_path)
    if (
        _file_sha256(plan_path) != binding.get("planFileSha256")
        or _file_sha256(snapshot_plan) != binding.get("planFileSha256")
        or physical_plan != _read_json(snapshot_plan)
        or any(
            physical_plan.get(key) != binding.get(key)
            for key in (
                "poolId", "targetScale", "sourceRevision", "sourceDigest",
                "entityCatalogDigest", "planDigest",
            )
        )
    ):
        raise CampaignScaleEvidenceError("source-pool plan bytes drift")
    projected_selections: list[dict[str, Any]] = []
    for carrier in CARRIERS:
        selection = selections.get(carrier)
        if not isinstance(selection, Mapping):
            raise CampaignScaleEvidenceError(f"{carrier} source-pool selection is missing")
        try:
            validated = validate_lane_source_pool_selection(
                selection,
                carrier=carrier,
                count=int(selection.get("candidateCount") or 0),
            )
        except (TypeError, ValueError) as exc:
            raise CampaignScaleEvidenceError(str(exc)) from exc
        projected_selections.append(validated)
    source_pool = {
        "poolId": str(binding["poolId"]),
        "targetScale": str(binding["targetScale"]),
        "sourceRevision": str(binding["sourceRevision"]),
        "sourceDigest": str(binding["sourceDigest"]),
        "entityCatalogDigest": str(binding["entityCatalogDigest"]),
        "planDigest": str(binding["planDigest"]),
        "planFileSha256": str(binding["planFileSha256"]),
        "sourceCapsuleRef": capsule_ref,
        "sourceCapsuleDigest": capsule_digest,
        "laneSelections": projected_selections,
    }
    return {"sourcePool": source_pool, "sourcePoolDigest": _digest(source_pool)}


def _promotion_source_pool_chain(
    path: Path,
    *,
    output_root: Path,
    seen: set[Path],
) -> list[dict[str, Any]]:
    resolved = path.resolve()
    if resolved in seen:
        raise CampaignScaleEvidenceError("source-pool predecessor lineage is cyclic")
    seen.add(resolved)
    promotion = _validated(
        resolved, "release", "research_scale_promotion", label="predecessor promotion"
    )
    evidence_path = _resolve(
        promotion.get("campaignEvidenceRef"),
        output_root=output_root,
        label="predecessor campaign evidence ref",
    )
    evidence = _validated(
        evidence_path,
        "release",
        "campaign_scale_evidence",
        label="predecessor campaign scale evidence",
    )
    if (
        promotion.get("campaignEvidenceDigest") != evidence.get("evidenceDigest")
        or promotion.get("sourcePoolDigest") != evidence.get("sourcePoolDigest")
    ):
        raise CampaignScaleEvidenceError("predecessor source-pool evidence binding drift")
    chain: list[dict[str, Any]] = []
    predecessor = evidence.get("predecessorPromotion")
    if isinstance(predecessor, Mapping):
        chain.extend(
            _promotion_source_pool_chain(
                _resolve(
                    predecessor.get("receiptRef"),
                    output_root=output_root,
                    label="source-pool predecessor promotion ref",
                ),
                output_root=output_root,
                seen=seen,
            )
        )
    chain.append({"promotion": promotion, "evidence": evidence})
    return chain


def source_pool_lineage_fields(
    *,
    source_pool_fields: Mapping[str, Any],
    target_scale: str,
    predecessor_promotion_path: Path | None,
    output_root: Path,
) -> dict[str, Any]:
    """Bind the immediate predecessor and reject reuse across the full lineage."""

    expected = _PREDECESSOR_SCALE.get(target_scale)
    if expected is None:
        if predecessor_promotion_path is not None:
            raise CampaignScaleEvidenceError("M100 source pool forbids a predecessor")
        return {**dict(source_pool_fields), "predecessorSourcePoolDigests": []}
    if predecessor_promotion_path is None:
        raise CampaignScaleEvidenceError(f"{target_scale} source pool requires {expected} predecessor")
    chain = _promotion_source_pool_chain(
        predecessor_promotion_path, output_root=output_root, seen=set()
    )
    immediate = chain[-1]["promotion"]
    if immediate.get("targetScale") != expected:
        raise CampaignScaleEvidenceError("source-pool predecessor scale drift")
    source_pool = source_pool_fields.get("sourcePool")
    if not isinstance(source_pool, Mapping):
        raise CampaignScaleEvidenceError("current source-pool evidence is missing")
    identities = ("sourceRevision", "sourceDigest", "entityCatalogDigest")
    current_ids = {
        str(row["carrier"]): set(row["candidateIds"])
        for row in source_pool["laneSelections"]
    }
    predecessor_digests: list[str] = []
    for row in chain:
        evidence = row["evidence"]
        predecessor_pool = evidence.get("sourcePool")
        if (
            not isinstance(predecessor_pool, Mapping)
            or any(predecessor_pool.get(key) != source_pool.get(key) for key in identities)
        ):
            raise CampaignScaleEvidenceError("source-pool predecessor identity drift")
        predecessor_digests.append(str(evidence["sourcePoolDigest"]))
        for lane in predecessor_pool.get("laneSelections") or []:
            carrier = str(lane.get("carrier") or "")
            if carrier in current_ids and current_ids[carrier] & set(lane.get("candidateIds") or []):
                raise CampaignScaleEvidenceError(
                    f"DATA.SOURCE.POOL_SHORTFALL: {carrier} candidate reused from predecessor"
                )
    return {
        **dict(source_pool_fields),
        "predecessorSourcePoolDigests": predecessor_digests,
    }


def campaign_source_pool_fields(
    *,
    plan: Mapping[str, Any],
    campaign_plan_path: Path,
    target_scale: str,
    predecessor_promotion_path: Path | None,
    output_root: Path,
) -> dict[str, Any]:
    return source_pool_lineage_fields(
        source_pool_fields=project_campaign_source_pool(
            plan=plan,
            campaign_plan_path=campaign_plan_path,
            output_root=output_root,
        ),
        target_scale=target_scale,
        predecessor_promotion_path=predecessor_promotion_path,
        output_root=output_root,
    )


def validate_recorded_source_pool_fields(
    *,
    campaign: Mapping[str, Any],
    plan: Mapping[str, Any],
    campaign_plan_path: Path,
    predecessor_promotion_path: Path | None,
    output_root: Path,
) -> None:
    projected = project_campaign_source_pool(
        plan=plan, campaign_plan_path=campaign_plan_path, output_root=output_root
    )
    expected = source_pool_lineage_fields(
        source_pool_fields=projected,
        target_scale=str(campaign.get("targetScale") or ""),
        predecessor_promotion_path=predecessor_promotion_path,
        output_root=output_root,
    )
    if any(campaign.get(key) != value for key, value in expected.items()):
        raise CampaignScaleEvidenceError("campaign source-pool projection drift")


__all__ = [
    "campaign_source_pool_fields",
    "project_campaign_source_pool",
    "source_pool_lineage_fields",
    "validate_recorded_source_pool_fields",
]
