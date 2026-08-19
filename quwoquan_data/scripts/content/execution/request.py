"""Strongly typed runtime request for one content execution."""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.codec import JsonObject, JsonObjectDecodeError
from core.control_types import TargetSelector


def resolve_candidate_pool(
    *,
    quota: object,
    count: object,
) -> tuple[int, int]:
    """Return the approved quota and the first pursuit round's candidate pool.

    ``--quota`` is the delivery promise.  ``--count`` only widens the first
    round beyond the policy oversample factor; omitting it derives the round
    from that single policy truth source.  Later rounds are sized by
    ``QuotaPursuitProgress.next_round_pool`` against the open deficit, so a
    below-forecast pass rate is recovered by replenishment rather than by an
    inflated one-shot draw.
    """
    from content.execution.planning.quota_pursuit import initial_candidate_pool
    from core.runtime_policy import active_runtime_policy

    if isinstance(quota, bool) or not isinstance(quota, int) or quota < 1:
        raise SystemExit("[task execute] GATE_BLOCK --quota must be a positive integer")
    derived = initial_candidate_pool(
        quota,
        oversample_factor=active_runtime_policy().oversample_factor,
    )
    if count is None:
        return quota, derived
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise SystemExit("[task execute] GATE_BLOCK --count must be a positive integer")
    return quota, count


def derive_capacity_from_execution(
    *,
    execution_id: str,
    work_unit_count: int,
) -> dict[str, Any]:
    """Derive the governed capacity triple for one single-execution request.

    The campaign envelope already derives this topology from its frozen
    work-unit count. A single execution carries the same decision, so it must
    read the same truth source instead of asking the caller to hand-author a
    digest that no document would back.
    """
    from content.execution.identity import parse_execution_id
    from content.execution.planning.capacity_policy import (
        derive_workload_capacity_fields,
    )

    try:
        identity = parse_execution_id(execution_id)
    except ValueError as exc:
        raise SystemExit(f"[task execute] GATE_BLOCK {exc}") from exc
    return derive_workload_capacity_fields(
        target_scale=identity.phase.value,
        carrier=identity.content_type.value,
        work_unit_count=work_unit_count,
    )


@dataclass(frozen=True, slots=True)
class RuntimeExecutionRequest:
    family_ref: str
    region_ref: str
    selector: TargetSelector
    count: int
    quota: int
    capacity_calibration: Mapping[str, Any]
    topic: str | None
    source_providers: tuple[str, ...]
    target_names: tuple[str, ...]
    worker_host_set_binding: Mapping[str, Any] | None = None
    scale_source_pool: Mapping[str, Any] | None = None
    source_pool_evidence_root_ref: str | None = None
    source_pool_selection: Mapping[str, Any] | None = None
    rewrite: Mapping[str, Any] | None = None
    retry_review_feedback: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.family_ref or not self.region_ref:
            raise ValueError("familyRef and regionRef must be non-empty")
        if not isinstance(self.selector, TargetSelector):
            raise ValueError("selector must be TargetSelector")
        if isinstance(self.count, bool) or self.count < 1:
            raise ValueError("count must be a positive integer")
        if isinstance(self.quota, bool) or self.quota < 1:
            raise ValueError("quota must be a positive integer")
        from content.execution.planning.capacity_calibration import (
            assert_capacity_source_binding,
        )

        assert_capacity_source_binding(self.capacity_calibration)
        if self.worker_host_set_binding is not None:
            from core.schema import assert_valid

            assert_valid(
                dict(self.worker_host_set_binding),
                "execution",
                "governed_worker_host_binding",
                label="runtime worker host-set binding",
            )
        if any(not provider.strip() for provider in self.source_providers):
            raise ValueError("sourceProviders must contain non-empty provider IDs")
        if tuple(sorted(set(self.source_providers))) != self.source_providers:
            raise ValueError("sourceProviders must be deduplicated and sorted")
        if len(set(self.target_names)) != len(self.target_names):
            raise ValueError("targetNames must be deduplicated")
        if any(not name.strip() for name in self.target_names):
            raise ValueError("targetNames must contain non-empty values")
        # quota is a content-object target. count/targetNames describe the
        # unique-entity candidate scope and therefore may be smaller than quota.
        if self.rewrite is not None:
            from content.execution.planning.rewrite import RewriteBinding

            rewrite = RewriteBinding.from_document(self.rewrite)
            if self.count != 1 or self.quota != 1:
                raise ValueError("targeted rewrite count and quota must both equal 1")
            if self.target_names != (rewrite.target_name,):
                raise ValueError("targeted rewrite must freeze exactly its source target")
        if self.retry_review_feedback is not None:
            from content.execution.planning.retry_review_feedback import (
                validate_retry_review_feedback,
            )

            feedback = validate_retry_review_feedback(self.retry_review_feedback)
            if tuple(feedback["failedObjectRefs"]) == ():
                raise ValueError("retry review feedback must contain failed objects")
        pool_parts = (
            self.scale_source_pool,
            self.source_pool_evidence_root_ref,
            self.source_pool_selection,
        )
        if any(part is not None for part in pool_parts):
            if not all(part is not None for part in pool_parts):
                raise ValueError("scale source pool runtime binding is incomplete")
            from core.schema import assert_valid

            from content.execution.campaign.source_pool_binding import (
                validate_lane_source_pool_selection,
            )

            assert_valid(
                dict(self.scale_source_pool or {}),
                "execution",
                "scale_source_pool_binding",
            )
            selection = dict(self.source_pool_selection or {})
            validate_lane_source_pool_selection(
                selection,
                carrier=str(selection.get("carrier") or ""),
                count=self.count,
            )

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "RuntimeExecutionRequest":
        quota, count = resolve_candidate_pool(
            quota=getattr(args, "quota", None),
            count=getattr(args, "count", None),
        )
        family_ref = str(getattr(args, "family", "") or "").strip()
        region_ref = str(getattr(args, "region_ref", "") or "").strip().strip("/")
        selector_raw = str(getattr(args, "selector", "") or "").strip()
        if not family_ref or not region_ref:
            raise SystemExit("[task execute] GATE_BLOCK --family and --region-ref are required")
        try:
            selector = TargetSelector(selector_raw)
        except ValueError as exc:
            choices = ", ".join(item.value for item in TargetSelector)
            raise SystemExit(
                f"[task execute] GATE_BLOCK --selector must be one of: {choices}"
            ) from exc
        topic = str(getattr(args, "topic", "") or "").strip() or None
        providers = tuple(
            sorted(
                {
                    str(value).strip()
                    for value in (getattr(args, "source_providers", ()) or ())
                    if str(value).strip()
                }
            )
        )
        target_names = tuple(
            str(value).strip()
            for value in (getattr(args, "target_names", ()) or ())
            if str(value).strip()
        )
        raw_capacity_receipt = str(
            getattr(args, "capacity_calibration_receipt", "") or ""
        ).strip()
        if not raw_capacity_receipt:
            raise SystemExit(
                "[task execute] GATE_BLOCK --capacity-calibration-receipt is required"
            )
        from content.execution.planning.capacity_calibration import (
            CapacityCalibrationError,
            bind_capacity_calibration_source,
            current_host_class,
            resolve_capacity_calibration_ref,
        )

        receipt_ref = raw_capacity_receipt
        try:
            receipt_path = resolve_capacity_calibration_ref(receipt_ref)
        except CapacityCalibrationError as exc:
            raise SystemExit(
                f"[task execute] GATE_BLOCK capacity calibration: {exc}"
            ) from exc

        provider_tier = str(
            getattr(args, "semantic_selection_id", "") or "default"
        ).strip()
        try:
            capacity_calibration = bind_capacity_calibration_source(
                receipt_path=receipt_path,
                receipt_ref=receipt_ref,
                host_class=current_host_class(),
                provider_tier=provider_tier,
            )
        except CapacityCalibrationError as exc:
            raise SystemExit(
                f"[task execute] GATE_BLOCK capacity calibration: {exc}"
            ) from exc
        raw_host_binding = str(
            getattr(args, "worker_host_set_binding_json", "") or ""
        ).strip()
        worker_host_set_binding = None
        if raw_host_binding:
            import json

            decoded = json.loads(raw_host_binding)
            if not isinstance(decoded, Mapping):
                raise SystemExit(
                    "[task execute] GATE_BLOCK --worker-host-set-binding-json must be an object"
                )
            worker_host_set_binding = dict(decoded)
        pool_id = str(getattr(args, "scale_source_pool_id", "") or "").strip()
        pool_fields = {
            "poolId": pool_id,
            "targetScale": str(
                getattr(args, "scale_source_pool_target_scale", "") or ""
            ).strip(),
            "sourceRevision": str(
                getattr(args, "source_pool_source_revision", "") or ""
            ).strip(),
            "sourceDigest": str(
                getattr(args, "source_pool_source_digest", "") or ""
            ).strip(),
            "entityCatalogDigest": str(
                getattr(args, "source_pool_entity_catalog_digest", "") or ""
            ).strip(),
            "planRef": str(
                getattr(args, "scale_source_pool_plan_ref", "") or ""
            ).strip(),
            "planDigest": str(
                getattr(args, "scale_source_pool_plan_digest", "") or ""
            ).strip(),
            "planFileSha256": str(
                getattr(args, "scale_source_pool_plan_file_sha256", "") or ""
            ).strip(),
        }
        evidence_ref = str(
            getattr(args, "source_pool_evidence_root_ref", "") or ""
        ).strip()
        candidate_ids = tuple(
            str(value).strip()
            for value in (getattr(args, "source_pool_candidate_ids", ()) or ())
            if str(value).strip()
        )
        selection_digest = str(
            getattr(args, "source_pool_selection_digest", "") or ""
        ).strip()
        pool_values_present = any(pool_fields.values()) or bool(
            evidence_ref or candidate_ids or selection_digest
        )
        scale_source_pool = None
        source_pool_selection = None
        if pool_values_present:
            if not all(pool_fields.values()) or not evidence_ref or not candidate_ids or not selection_digest:
                raise SystemExit(
                    "[task execute] GATE_BLOCK DATA.SOURCE.POOL_SHORTFALL: "
                    "scale source pool runtime binding is incomplete"
                )
            scale_source_pool = pool_fields
            source_pool_selection = {
                "carrier": str(getattr(args, "source_pool_carrier", "") or ""),
                "candidateIds": list(candidate_ids),
                "candidateCount": len(candidate_ids),
                "selectionDigest": selection_digest,
            }
        raw_rewrite = getattr(args, "rewrite_binding", None)
        rewrite = None
        if raw_rewrite is not None:
            if not isinstance(raw_rewrite, Mapping):
                raise SystemExit(
                    "[task execute] GATE_BLOCK frozen rewrite binding must be an object"
                )
            from content.execution.planning.rewrite import RewriteBinding

            rewrite = RewriteBinding.from_document(raw_rewrite).to_document()
        raw_retry_review_feedback = getattr(args, "retry_review_feedback", None)
        retry_review_feedback = None
        if raw_retry_review_feedback is not None:
            if not isinstance(raw_retry_review_feedback, Mapping):
                raise SystemExit(
                    "[task execute] GATE_BLOCK retry review feedback must be an object"
                )
            from content.execution.planning.retry_review_feedback import (
                validate_retry_review_feedback,
            )

            retry_review_feedback = validate_retry_review_feedback(
                raw_retry_review_feedback
            )
            execution_id = str(getattr(args, "execution_id", "") or "").strip()
            if retry_review_feedback.get("executionId") != execution_id:
                raise SystemExit(
                    "[task execute] GATE_BLOCK retry review feedback executionId drift"
                )
        return cls(
            family_ref=family_ref,
            region_ref=region_ref,
            selector=selector,
            count=count,
            quota=quota,
            capacity_calibration=capacity_calibration,
            worker_host_set_binding=worker_host_set_binding,
            topic=topic,
            source_providers=providers,
            target_names=target_names,
            scale_source_pool=scale_source_pool,
            source_pool_evidence_root_ref=evidence_ref or None,
            source_pool_selection=source_pool_selection,
            rewrite=rewrite,
            retry_review_feedback=retry_review_feedback,
        )

    @classmethod
    def from_document(cls, value: object) -> "RuntimeExecutionRequest":
        try:
            document = JsonObject.from_value(value, label="execution request")
            base = {
                "familyRef",
                "regionRef",
                "selector",
                "count",
                "quota",
                "capacityCalibration",
                "workerHostSetBinding",
                "topic",
                "sourceProviders",
                "targetNames",
            }
            pool_keys = {
                "scaleSourcePool", "sourcePoolEvidenceRootRef", "sourcePoolSelection"
            }
            rewrite_keys = {"rewrite"}
            retry_feedback_keys = {"retryReviewFeedback"}
            keys = set(document.to_document())
            allowed_keys = base | pool_keys | rewrite_keys | retry_feedback_keys
            if (
                not base.issubset(keys)
                or not keys.issubset(allowed_keys)
                or bool(keys & pool_keys) != pool_keys.issubset(keys)
            ):
                raise JsonObjectDecodeError(
                    "execution request keys must be exactly "
                    + ", ".join(sorted(base))
                )
            raw = document.to_document()
            return cls(
                family_ref=document.string("familyRef"),
                region_ref=document.string("regionRef").strip().strip("/"),
                selector=TargetSelector(document.string("selector")),
                count=document.integer("count"),
                quota=document.integer("quota"),
                capacity_calibration=document.object(
                    "capacityCalibration"
                ).to_document(),
                worker_host_set_binding=(
                    dict(raw["workerHostSetBinding"])
                    if isinstance(raw.get("workerHostSetBinding"), Mapping)
                    else None
                ),
                topic=document.optional_string("topic"),
                source_providers=document.string_list("sourceProviders"),
                target_names=document.string_list("targetNames"),
                scale_source_pool=(
                    dict(raw["scaleSourcePool"])
                    if isinstance(raw.get("scaleSourcePool"), Mapping)
                    else None
                ),
                source_pool_evidence_root_ref=(
                    document.string("sourcePoolEvidenceRootRef")
                    if "sourcePoolEvidenceRootRef" in raw
                    else None
                ),
                source_pool_selection=(
                    dict(raw["sourcePoolSelection"])
                    if isinstance(raw.get("sourcePoolSelection"), Mapping)
                    else None
                ),
                rewrite=(
                    dict(raw["rewrite"])
                    if isinstance(raw.get("rewrite"), Mapping)
                    else None
                ),
                retry_review_feedback=(
                    dict(raw["retryReviewFeedback"])
                    if isinstance(raw.get("retryReviewFeedback"), Mapping)
                    else None
                ),
            )
        except (JsonObjectDecodeError, ValueError) as exc:
            raise SystemExit(f"[task execute] GATE_BLOCK invalid frozen request: {exc}") from exc

    def to_document(self) -> dict[str, object]:
        document: dict[str, object] = {
            "familyRef": self.family_ref,
            "regionRef": self.region_ref,
            "selector": self.selector.value,
            "count": self.count,
            "quota": self.quota,
            "capacityCalibration": dict(self.capacity_calibration),
            "workerHostSetBinding": (
                dict(self.worker_host_set_binding)
                if self.worker_host_set_binding is not None
                else None
            ),
            "topic": self.topic,
            "sourceProviders": list(self.source_providers),
            "targetNames": list(self.target_names),
        }
        if self.scale_source_pool is not None:
            document["scaleSourcePool"] = dict(self.scale_source_pool)
            document["sourcePoolEvidenceRootRef"] = self.source_pool_evidence_root_ref
            document["sourcePoolSelection"] = dict(self.source_pool_selection or {})
        if self.rewrite is not None:
            document["rewrite"] = dict(self.rewrite)
        if self.retry_review_feedback is not None:
            document["retryReviewFeedback"] = dict(self.retry_review_feedback)
        return document


__all__ = ["RuntimeExecutionRequest", "resolve_candidate_pool"]
