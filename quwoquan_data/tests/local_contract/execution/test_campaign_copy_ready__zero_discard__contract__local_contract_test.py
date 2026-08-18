# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
from __future__ import annotations

from pathlib import Path

from content.execution.campaign.copy_ready import maybe_write_copy_ready_receipt
from content.execution.campaign.receipt import lane_receipt_path
from core.io import write_json

CARRIERS = ("homepage", "article", "image", "video")


def _receipt(
    *,
    root_id: str,
    execution_id: str,
    carrier: str,
    phase: str,
    quota: int = 3,
    selected: int = 6,
) -> dict[str, object]:
    # Zero-discard scale proof: every selected candidate is qualified.
    status = (
        ("qualified" if selected >= quota else "partial")
        if phase == "review"
        else ("finalized" if selected >= quota else "partial")
    )
    receipt = {
        "schema": "quwoquan_data.content_campaign_lane_receipt",
        "rootExecutionId": root_id,
        "executionId": execution_id,
        "carrier": carrier,
        "phase": phase,
        "status": status,
        "approvedQuota": quota,
        "qualifiedCount": selected,
        "finalizedCount": 0 if phase == "review" else selected,
        "selectedCount": selected,
        "discardedCount": 0,
        "shortfallCount": max(0, quota - selected),
        "discards": [],
    }
    if phase == "publish":
        receipt.update(
            {
                "executionPublishRef": (f"data/tasks/{execution_id}/publish_ref.json"),
                "executionPublishSha256": "sha256:" + "e" * 64,
                "campaignRunId": "copy-ready-test-run",
                "campaignGeneration": 1,
                "campaignFencingToken": "sha256:" + "f" * 64,
                "reviewQualifiedCount": selected,
                "publishDiscards": [],
            }
        )
    return receipt


def test_copy_ready_allows_zero_typed_discards(tmp_path: Path) -> None:
    root_id = "20260730--travel-homepage-scale--china--scale-001"
    output = tmp_path / "output"
    campaigns = output / "data/local/workspace/content-campaign-submissions"
    submissions = {}
    lanes = {}
    plan = {
        "planDigest": "sha256:" + ("a" * 64),
        "gitBranch": "dev1.0",
        "gitCommitSha": "b" * 40,
        "sourceDigest": "sha256:" + ("c" * 64),
        "entityCatalogDigest": "sha256:" + ("d" * 64),
        "activeCarriers": list(CARRIERS),
        "workloads": {carrier: 3 for carrier in CARRIERS},
    }
    for carrier in CARRIERS:
        execution_id = (
            root_id
            if carrier == "homepage"
            else f"20260730--travel-{carrier}-scale--china--scale-001"
        )
        submissions[carrier] = {
            "executionId": execution_id,
            "quota": 3,
            "count": 6,
        }
        lanes[carrier] = {
            "status": "finalized",
            "cleanupStatus": "cleaned",
        }
        for phase in ("review", "publish"):
            path = lane_receipt_path(root_id, carrier, phase, root=campaigns)
            path.parent.mkdir(parents=True, exist_ok=True)
            write_json(
                path,
                _receipt(
                    root_id=root_id,
                    execution_id=execution_id,
                    carrier=carrier,
                    phase=phase,
                ),
            )

    unclean = {
        carrier: {**row, "cleanupStatus": "pending"} for carrier, row in lanes.items()
    }
    assert (
        maybe_write_copy_ready_receipt(
            root_execution_id=root_id,
            plan=plan,
            submissions=submissions,
            lanes=unclean,
            campaigns_root=campaigns,
            output_root=output,
            assessed_at="2026-07-30T00:00:00+00:00",
        )
        is None
    ), "COPY_READY must wait until lane cleanupStatus is cleaned"

    path = maybe_write_copy_ready_receipt(
        root_execution_id=root_id,
        plan=plan,
        submissions=submissions,
        lanes=lanes,
        campaigns_root=campaigns,
        output_root=output,
        assessed_at="2026-07-30T00:00:00+00:00",
    )
    assert path is not None
    payload = path.read_text(encoding="utf-8")
    assert '"totalDiscardedCount": 0' in payload
    assert '"qualifiedPerLane": 1' in payload
    assert "typedDiscards" not in payload


def test_copy_ready_treats_quota_shortfall_as_statistics(tmp_path: Path) -> None:
    root_id = "20260730--travel-homepage-m100--china--scale-002"
    output = tmp_path / "output"
    campaigns = output / "data/local/workspace/content-campaign-submissions"
    plan = {
        "planDigest": "sha256:" + ("1" * 64),
        "gitBranch": "dev1.0",
        "gitCommitSha": "2" * 40,
        "sourceDigest": "sha256:" + ("3" * 64),
        "entityCatalogDigest": "sha256:" + ("4" * 64),
        "activeCarriers": list(CARRIERS),
        "workloads": {
            "homepage": 100,
            "article": 100,
            "image": 100,
            "video": 10,
        },
    }
    submissions = {}
    lanes = {}
    for carrier in CARRIERS:
        execution_id = (
            root_id
            if carrier == "homepage"
            else f"20260730--travel-{carrier}-m100--china--scale-002"
        )
        submissions[carrier] = {
            "executionId": execution_id,
            "quota": 100 if carrier != "video" else 10,
            "count": 100 if carrier != "video" else 10,
        }
        lanes[carrier] = {"status": "partial", "cleanupStatus": "cleaned"}
        for phase in ("review", "publish"):
            write_json(
                lane_receipt_path(root_id, carrier, phase, root=campaigns),
                _receipt(
                    root_id=root_id,
                    execution_id=execution_id,
                    carrier=carrier,
                    phase=phase,
                    quota=int(submissions[carrier]["quota"]),
                    selected=1,
                ),
            )

    path = maybe_write_copy_ready_receipt(
        root_execution_id=root_id,
        plan=plan,
        submissions=submissions,
        lanes=lanes,
        campaigns_root=campaigns,
        output_root=output,
        assessed_at="2026-07-30T00:00:00+00:00",
    )

    assert path is not None
    payload = path.read_text(encoding="utf-8")
    assert '"qualifiedCount": 1' in payload
    assert '"shortfallCount": 99' in payload


def test_copy_ready_accepts_positive_partial_publish_with_typed_object_discard(
    tmp_path: Path,
) -> None:
    root_id = "20260730--travel-video-partial--china--scale-003"
    output = tmp_path / "output"
    campaigns = output / "data/local/workspace/content-campaign-submissions"
    plan = {
        "planDigest": "sha256:" + "5" * 64,
        "gitBranch": "dev1.0",
        "gitCommitSha": "6" * 40,
        "sourceDigest": "sha256:" + "7" * 64,
        "entityCatalogDigest": "sha256:" + "8" * 64,
        "activeCarriers": ["video"],
        "workloads": {"video": 3},
    }
    review = _receipt(
        root_id=root_id,
        execution_id=root_id,
        carrier="video",
        phase="review",
        quota=3,
        selected=3,
    )
    publish = _receipt(
        root_id=root_id,
        execution_id=root_id,
        carrier="video",
        phase="publish",
        quota=3,
        selected=3,
    )
    publish.update(
        {
            "status": "partial",
            "finalizedCount": 2,
            "shortfallCount": 1,
            "publishDiscards": [
                {
                    "objectRef": "video/测试/video-003/001",
                    "issues": ["DATA.PUBLISH.OBJECT_APPLY_FAILED"],
                }
            ],
        }
    )
    write_json(
        lane_receipt_path(root_id, "video", "review", root=campaigns), review
    )
    write_json(
        lane_receipt_path(root_id, "video", "publish", root=campaigns), publish
    )

    path = maybe_write_copy_ready_receipt(
        root_execution_id=root_id,
        plan=plan,
        submissions={
            "video": {"executionId": root_id, "quota": 3, "count": 3}
        },
        lanes={
            "video": {"status": "partial", "cleanupStatus": "cleaned"}
        },
        campaigns_root=campaigns,
        output_root=output,
        assessed_at="2026-07-30T00:00:00+00:00",
    )

    assert path is not None
    payload = path.read_text(encoding="utf-8")
    assert '"finalizedCount": 2' in payload
    assert '"totalDiscardedCount": 1' in payload
