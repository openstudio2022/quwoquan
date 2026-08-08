from __future__ import annotations

import pytest

from content.execution.scale.capacity_plan import throughput_basis_digest
from content.release.canonical.research_scale_capacity import (
    ResearchScaleCapacityEvidenceError,
    project_capacity_throughput,
)


DIGEST = "sha256:" + "a" * 64
CARRIERS = ("homepage", "article", "image", "video")


def _resource() -> dict[str, object]:
    return {
        "evidenceDigest": DIGEST,
        "semanticJobsByLane": [
            {
                "carrier": carrier,
                "semanticJobSucceededCount": 10,
                "perSlotThroughputSamples": [0.01 + index / 1000 for index in range(10)],
            }
            for carrier in CARRIERS
        ],
    }


def _campaign() -> dict[str, str]:
    return {
        "targetScale": "M100",
        "sourceRevision": "sha256:" + "1" * 64,
        "sourceDigest": "sha256:" + "2" * 64,
        "entityCatalogDigest": "sha256:" + "3" * 64,
        "resourceSoakEvidenceRef": "data/local/workspace/evidence/resource-soak.json",
        "resourceSoakEvidenceDigest": DIGEST,
    }


def test_capacity_projection_binds_four_lane_positive_samples() -> None:
    projected = project_capacity_throughput(
        evidence=_campaign(),
        resource_evidence=_resource(),
    )

    assert [row["carrier"] for row in projected] == list(CARRIERS)
    assert all(len(row["perSlotThroughputSamples"]) == 10 for row in projected)
    assert all(row["evidenceDigest"] == DIGEST for row in projected)
    assert all(
        row["throughputBasisDigest"] == throughput_basis_digest(row)
        for row in projected
    )


@pytest.mark.parametrize("mutation", ["digest", "zero", "missing_lane"])
def test_capacity_projection_fails_closed_on_unusable_evidence(
    mutation: str,
) -> None:
    campaign = _campaign()
    resource = _resource()
    if mutation == "digest":
        campaign["resourceSoakEvidenceDigest"] = "sha256:" + "b" * 64
    elif mutation == "zero":
        resource["semanticJobsByLane"][0]["perSlotThroughputSamples"][0] = 0
    else:
        resource["semanticJobsByLane"].pop()

    with pytest.raises(
        ResearchScaleCapacityEvidenceError,
        match="DATA.AGENT.CAPACITY_SHORTFALL",
    ):
        project_capacity_throughput(
            evidence=campaign,
            resource_evidence=resource,
        )
