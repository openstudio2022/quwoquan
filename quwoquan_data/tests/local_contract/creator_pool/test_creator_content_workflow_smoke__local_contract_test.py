"""3× creator content bind smoke for commercial batch-100."""
from __future__ import annotations

import json
from pathlib import Path

from _common.creator_assignment import creator_assignment_from_profile
from _common.creator_pool.registry_bridge import load_travel_batch_creators

REPO = Path(__file__).resolve().parents[4]
SEED = REPO / "quwoquan_service/contracts/metadata/_shared/test_fixtures/creator_pool/creator_travel_batch100.seed.json"
BATCH = "travel_batch_100_v1"


def _carrier_pick(users: list[dict], carrier: str) -> dict:
    creators, _ = load_travel_batch_creators(BATCH)
    by_handle = {p.get("userHandle"): p for p in creators.values()}
    best: dict | None = None
    best_score = -1.0
    for user in users:
        handle = str(user.get("userHandle") or "")
        profile = by_handle.get(handle) or {}
        affinity = profile.get("carrierAffinity") or {}
        score = float(affinity.get(carrier) or 0.0)
        if score > best_score:
            best_score = score
            best = {**user, "carrierAffinity": affinity}
    assert best is not None
    return best


def test_batch100_content_bind_smoke_article_image_video() -> None:
    data = json.loads(SEED.read_text(encoding="utf-8"))
    users = data.get("users") or []
    assert len(users) >= 3
    picks = [
        _carrier_pick(users, "article"),
        _carrier_pick(users, "image"),
        _carrier_pick(users, "video"),
    ]
    for user in picks:
        profile = {
            "creatorProfileId": user["creatorProfileId"],
            "authorId": user["authorId"],
            "creatorArchetype": user["creatorArchetype"],
            "profileVersion": "1.0.0",
            "disclosure": {
                "type": "platform_virtual_creator",
                "displayText": "平台虚拟创作者",
                "visible": True,
            },
            "claimPolicy": {
                "experienceClaimMode": "editorial_synthesis",
                "mayUseFirstPerson": False,
                "mustCiteEvidenceForClaims": True,
            },
            "qualityScore": 0.85,
        }
        assignment = creator_assignment_from_profile(profile)
        assert assignment["authorId"] == user["authorId"]
        assert assignment["creatorProfileId"] == user["creatorProfileId"]
        assert user["cohortId"] == BATCH
