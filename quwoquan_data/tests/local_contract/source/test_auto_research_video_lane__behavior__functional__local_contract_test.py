from __future__ import annotations

from core.io import read_json
from content.source.research.auto_plan_video import write_video_lane
from governance.content_supply_policy import load_content_supply_policy


def _frame(entity: str, ordinal: int) -> dict[str, object]:
    proof = f"https://commons.wikimedia.org/wiki/File:{entity}_{ordinal}.jpg"
    return {
        "url": f"https://upload.wikimedia.org/{entity}_{ordinal}.jpg",
        "platform": "Wikimedia Commons",
        "license": "CC BY-SA 4.0",
        "credit": f"Creator {ordinal}",
        "creator": f"Creator {ordinal}",
        "sourceUrl": proof,
        "collectionPageUrl": proof,
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "licenseSnapshot": "CC BY-SA 4.0 recorded on the Commons file page",
        "authorizationProof": proof,
        "usageScope": "app_publish",
        "modelReleaseStatus": "not_required",
        "width": 1600,
        "height": 1000,
        "caption": f"{entity} 景观画面 {ordinal}",
        "relevance": f"{entity} 景观画面 {ordinal}",
    }


def test_video_lane_writes_minimum_rights_cleared_frame_plan(tmp_path):
    entity = "测试实体甲"
    required = (
        load_content_supply_policy("travel").video_delivery.minimum_source_frames
    )
    report: dict[str, object] = {"sourceUnavailable": [], "videoFrames": []}
    updated: list[dict[str, object]] = []

    write_video_lane(
        entity_id=entity,
        entity_aliases=[entity],
        vertical="travel",
        plan_dir=tmp_path,
        force=True,
        report=report,
        updated=updated,
        open_license_image_pool=[
            _frame(entity, ordinal) for ordinal in range(1, required + 2)
        ],
    )

    payload = read_json(tmp_path / "video_source_plan.json")["payload"]
    assert len(payload["assets"]) == required
    assert payload["sourceUnavailable"] == []
    assert {asset["researchLane"] for asset in payload["assets"]} == {"video"}
    assert all(asset["authorizationProof"] for asset in payload["assets"])
    assert updated == [{"entityId": entity, "lane": "video", "assets": required}]
