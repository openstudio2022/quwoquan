"""Strongly typed runtime request for one content execution."""
from __future__ import annotations

import argparse
import math
import re
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
    """Return the approved quota and the oversampled candidate pool.

    ``--quota`` is the delivery promise.  ``--count`` only widens the candidate
    pool beyond the policy oversample factor; omitting it derives the pool from
    that single policy truth source.
    """
    from core.runtime_policy import active_runtime_policy

    if isinstance(quota, bool) or not isinstance(quota, int) or quota < 1:
        raise SystemExit("[task execute] GATE_BLOCK --quota must be a positive integer")
    factor = active_runtime_policy().oversample_factor
    derived = int(math.ceil(quota * factor))
    if count is None:
        return quota, derived
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise SystemExit("[task execute] GATE_BLOCK --count must be a positive integer")
    if count < quota:
        raise SystemExit(
            f"[task execute] GATE_BLOCK --count {count} must not be smaller than --quota {quota}"
        )
    return quota, count


@dataclass(frozen=True, slots=True)
class RuntimeExecutionRequest:
    family_ref: str
    region_ref: str
    selector: TargetSelector
    count: int
    quota: int
    required_workers: int
    partition_count: int
    capacity_plan_digest: str
    topic: str | None
    source_providers: tuple[str, ...]
    target_names: tuple[str, ...]
    scale_source_pool: Mapping[str, Any] | None = None
    source_pool_evidence_root_ref: str | None = None
    source_pool_selection: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.family_ref or not self.region_ref:
            raise ValueError("familyRef and regionRef must be non-empty")
        if not isinstance(self.selector, TargetSelector):
            raise ValueError("selector must be TargetSelector")
        if isinstance(self.count, bool) or self.count < 1:
            raise ValueError("count must be a positive integer")
        if isinstance(self.quota, bool) or self.quota < 1:
            raise ValueError("quota must be a positive integer")
        if self.quota > self.count:
            raise ValueError("quota must not exceed the candidate pool count")
        if isinstance(self.required_workers, bool) or self.required_workers < 1:
            raise ValueError("requiredWorkers must be a positive integer")
        if self.partition_count not in {16, 32, 64, 128, 256}:
            raise ValueError("partitionCount must be a governed partition count")
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", self.capacity_plan_digest):
            raise ValueError("capacityPlanDigest must be a canonical sha256 digest")
        if any(not provider.strip() for provider in self.source_providers):
            raise ValueError("sourceProviders must contain non-empty provider IDs")
        if tuple(sorted(set(self.source_providers))) != self.source_providers:
            raise ValueError("sourceProviders must be deduplicated and sorted")
        if len(set(self.target_names)) != len(self.target_names):
            raise ValueError("targetNames must be deduplicated")
        if any(not name.strip() for name in self.target_names):
            raise ValueError("targetNames must contain non-empty values")
        if self.target_names and not (
            self.quota <= len(self.target_names) <= self.count
        ):
            raise ValueError(
                "targetNames size must fall inside the [quota, count] candidate pool range"
            )
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
        required_workers = getattr(args, "required_workers", None)
        partition_count = getattr(args, "partition_count", None)
        capacity_plan_digest = str(
            getattr(args, "capacity_plan_digest", "") or ""
        ).strip()
        if (
            isinstance(required_workers, bool)
            or not isinstance(required_workers, int)
            or required_workers < 1
            or isinstance(partition_count, bool)
            or not isinstance(partition_count, int)
            or partition_count not in {16, 32, 64, 128, 256}
            or not re.fullmatch(r"sha256:[a-f0-9]{64}", capacity_plan_digest)
        ):
            raise SystemExit(
                "[task execute] GATE_BLOCK --required-workers, --partition-count "
                "and --capacity-plan-digest are required governed capacity inputs"
            )
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
        return cls(
            family_ref=family_ref,
            region_ref=region_ref,
            selector=selector,
            count=count,
            quota=quota,
            required_workers=required_workers,
            partition_count=partition_count,
            capacity_plan_digest=capacity_plan_digest,
            topic=topic,
            source_providers=providers,
            target_names=target_names,
            scale_source_pool=scale_source_pool,
            source_pool_evidence_root_ref=evidence_ref or None,
            source_pool_selection=source_pool_selection,
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
                "requiredWorkers",
                "partitionCount",
                "capacityPlanDigest",
                "topic",
                "sourceProviders",
                "targetNames",
            }
            pool_keys = {
                "scaleSourcePool", "sourcePoolEvidenceRootRef", "sourcePoolSelection"
            }
            keys = set(document.to_document())
            if keys not in {frozenset(base), frozenset(base | pool_keys)}:
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
                required_workers=document.integer("requiredWorkers"),
                partition_count=document.integer("partitionCount"),
                capacity_plan_digest=document.string("capacityPlanDigest"),
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
            "requiredWorkers": self.required_workers,
            "partitionCount": self.partition_count,
            "capacityPlanDigest": self.capacity_plan_digest,
            "topic": self.topic,
            "sourceProviders": list(self.source_providers),
            "targetNames": list(self.target_names),
        }
        if self.scale_source_pool is not None:
            document["scaleSourcePool"] = dict(self.scale_source_pool)
            document["sourcePoolEvidenceRootRef"] = self.source_pool_evidence_root_ref
            document["sourcePoolSelection"] = dict(self.source_pool_selection or {})
        return document


__all__ = ["RuntimeExecutionRequest", "resolve_candidate_pool"]
