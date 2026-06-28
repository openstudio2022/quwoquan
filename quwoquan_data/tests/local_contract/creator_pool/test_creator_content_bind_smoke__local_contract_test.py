from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SCRIPTS = REPO / "quwoquan_data/scripts"
sys.path.insert(0, str(SCRIPTS))

from _common.creator_assignment import creator_assignment_from_profile

REPO = Path(__file__).resolve().parents[4]
SEED = REPO / "quwoquan_service/contracts/metadata/_shared/test_fixtures/creator_pool/creator_travel_scale10.seed.json"


def test_creator_assignment_matches_seed_users() -> None:
    data = json.loads(SEED.read_text(encoding="utf-8"))
    users = data.get("users") or []
    assert len(users) >= 3
    for user in users[:3]:
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
