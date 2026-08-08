"""Project per-slot throughput samples from canonical soak evidence."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


class ResearchScaleCapacityEvidenceError(RuntimeError):
    pass


_CARRIERS = ("homepage", "article", "image", "video")


def _throughput_basis_digest(row: Mapping[str, Any]) -> str:
    document = {
        "schema": "quwoquan_data.capacity_throughput_basis",
        "carrier": row.get("carrier"),
        "measuredScale": row.get("measuredScale"),
        "sourceRevision": row.get("sourceRevision"),
        "sourceDigest": row.get("sourceDigest"),
        "entityCatalogDigest": row.get("entityCatalogDigest"),
        "throughputUnit": row.get("throughputUnit"),
        "perSlotThroughputSamples": list(
            row.get("perSlotThroughputSamples") or []
        ),
    }
    body = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def project_capacity_throughput(
    *,
    evidence: Mapping[str, Any],
    resource_evidence: Mapping[str, Any],
) -> list[dict[str, Any]]:
    measured_scale = str(evidence.get("targetScale") or "")
    source_revision = str(evidence.get("sourceRevision") or "")
    source_digest = str(evidence.get("sourceDigest") or "")
    entity_catalog_digest = str(evidence.get("entityCatalogDigest") or "")
    if (
        measured_scale not in {"M100", "M1000", "M10000"}
        or any(
            not value.startswith("sha256:") or len(value) != 71
            for value in (
                source_revision,
                source_digest,
                entity_catalog_digest,
            )
        )
    ):
        raise ResearchScaleCapacityEvidenceError(
            "DATA.AGENT.CAPACITY_SHORTFALL: throughput source identity is invalid"
        )
    rows = resource_evidence.get("semanticJobsByLane")
    if not isinstance(rows, list) or len(rows) != len(_CARRIERS):
        raise ResearchScaleCapacityEvidenceError(
            "DATA.AGENT.CAPACITY_SHORTFALL: four-lane throughput evidence is incomplete"
        )
    by_carrier = {
        str(row.get("carrier") or ""): row
        for row in rows
        if isinstance(row, Mapping)
    }
    if set(by_carrier) != set(_CARRIERS):
        raise ResearchScaleCapacityEvidenceError(
            "DATA.AGENT.CAPACITY_SHORTFALL: throughput lane identity drift"
        )
    evidence_ref = str(evidence.get("resourceSoakEvidenceRef") or "")
    evidence_digest = str(evidence.get("resourceSoakEvidenceDigest") or "")
    if (
        not evidence_ref
        or not evidence_digest.startswith("sha256:")
        or len(evidence_digest) != 71
        or resource_evidence.get("evidenceDigest") != evidence_digest
    ):
        raise ResearchScaleCapacityEvidenceError(
            "DATA.AGENT.CAPACITY_SHORTFALL: resource soak evidence binding drift"
        )
    projected: list[dict[str, Any]] = []
    for carrier in _CARRIERS:
        row = by_carrier[carrier]
        samples = row.get("perSlotThroughputSamples")
        succeeded = row.get("semanticJobSucceededCount")
        if (
            isinstance(succeeded, bool)
            or not isinstance(succeeded, int)
            or succeeded < 10
            or not isinstance(samples, list)
            or len(samples) != succeeded
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or value <= 0
                for value in samples
            )
        ):
            raise ResearchScaleCapacityEvidenceError(
                f"DATA.AGENT.CAPACITY_SHORTFALL: {carrier} per-slot throughput samples are invalid"
            )
        projection = {
            "carrier": carrier,
            "measuredScale": measured_scale,
            "sourceRevision": source_revision,
            "sourceDigest": source_digest,
            "entityCatalogDigest": entity_catalog_digest,
            "throughputUnit": "objects_per_second_per_slot",
            "perSlotThroughputSamples": [float(value) for value in samples],
            "evidenceRef": evidence_ref,
            "evidenceDigest": evidence_digest,
        }
        projection["throughputBasisDigest"] = _throughput_basis_digest(
            projection
        )
        projected.append(projection)
    return projected


__all__ = [
    "ResearchScaleCapacityEvidenceError",
    "project_capacity_throughput",
]
