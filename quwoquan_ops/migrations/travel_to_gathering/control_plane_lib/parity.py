"""parity 八维投影比对与 disposition 汇总（逐字来自原 ``control_plane.py``）。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.codec import (
    canonical_digest,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.constants import (
    DISPOSITIONS,
)


def _dimension_projection(
    documents: Sequence[Mapping[str, Any]],
    dimension: str,
) -> Any:
    by_kind: dict[str, list[Mapping[str, Any]]] = {}
    for wrapper in documents:
        kind = str(wrapper.get("kind") or "")
        document = wrapper.get("document")
        if kind and isinstance(document, dict):
            by_kind.setdefault(kind, []).append(document)
    if dimension == "identity":
        return {
            kind: sorted(
                canonical_digest(
                    {
                        key: document.get(key)
                        for key in (
                            "_id",
                            "gatheringId",
                        )
                        if key in document
                    }
                )
                for document in values
            )
            for kind, values in sorted(by_kind.items())
        }
    if dimension == "count":
        return {kind: len(values) for kind, values in sorted(by_kind.items())}
    if dimension == "state":
        return sorted(
            (
                document.get("_id"),
                document.get("lifecycleStatus"),
                document.get("currentGatheringRevisionId"),
                document.get("currentGatheringRevisionNumber"),
            )
            for document in by_kind.get("circle.gathering", [])
        )
    if dimension == "host":
        return sorted(
            canonical_digest(
                {
                    "gatheringId": document.get("_id"),
                    "hostBinding": document.get("hostBinding"),
                    "organizerAssignments": document.get("organizerAssignments"),
                }
            )
            for document in by_kind.get("circle.gathering", [])
        )
    if dimension == "membership":
        return sorted(
            canonical_digest(
                {
                    "gatheringId": document.get("_id"),
                    "participations": document.get("participations"),
                }
            )
            for document in by_kind.get("circle.gathering", [])
        )
    if dimension == "plan":
        return sorted(
            canonical_digest(document)
            for document in by_kind.get("circle.gathering_plan", [])
        )
    if dimension == "contentRefs":
        refs: list[dict[str, str]] = []
        for plan in by_kind.get("circle.gathering_plan", []):
            for revision in plan.get("revisions", []):
                if not isinstance(revision, dict):
                    continue
                for item in revision.get("items", []):
                    if not isinstance(item, dict):
                        continue
                    for ref in item.get("sourceRefs", []):
                        if (
                            isinstance(ref, dict)
                            and ref.get("objectTypeRef") == "content.Post"
                        ):
                            refs.append(
                                {
                                    "objectTypeRef": "content.Post",
                                    "objectId": str(ref.get("objectId") or ""),
                                }
                            )
        return sorted(canonical_digest(ref) for ref in refs)
    if dimension == "outcome":
        return sorted(
            canonical_digest(
                {
                    "gatheringId": document.get("_id"),
                    "outcome": document.get("outcome"),
                    "completedAt": document.get("completedAt"),
                }
            )
            for document in by_kind.get("circle.gathering", [])
        )
    raise ValueError(f"unsupported parity dimension: {dimension}")


def build_parity(
    expected_documents: Sequence[Mapping[str, Any]],
    observed_documents: Sequence[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    dimensions = (
        "identity",
        "count",
        "state",
        "host",
        "membership",
        "plan",
        "contentRefs",
        "outcome",
    )
    if observed_documents is None:
        return {
            "status": "not_executed",
            "percentage": 0,
            "dimensions": {
                dimension: {
                    "matched": False,
                    "expectedDigest": canonical_digest(
                        _dimension_projection(expected_documents, dimension)
                    ),
                    "observedDigest": "",
                }
                for dimension in dimensions
            },
        }
    result: dict[str, Any] = {}
    matched = 0
    for dimension in dimensions:
        expected = _dimension_projection(expected_documents, dimension)
        observed = _dimension_projection(observed_documents, dimension)
        is_match = expected == observed
        matched += int(is_match)
        result[dimension] = {
            "matched": is_match,
            "expectedDigest": canonical_digest(expected),
            "observedDigest": canonical_digest(observed),
        }
    percentage = (matched * 100) // len(dimensions)
    return {
        "status": "passed" if percentage == 100 else "GATE_BLOCK",
        "percentage": percentage,
        "dimensions": result,
    }


def _disposition_summary(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    total = {disposition: 0 for disposition in DISPOSITIONS}
    by_type: dict[str, dict[str, int]] = {}
    for record in records:
        object_type = str(record["sourceObjectType"])
        disposition = str(record["disposition"])
        total[disposition] += 1
        by_type.setdefault(
            object_type,
            {candidate: 0 for candidate in DISPOSITIONS},
        )[disposition] += 1
    return {
        "counts": total,
        "bySourceObjectType": {key: by_type[key] for key in sorted(by_type)},
    }
