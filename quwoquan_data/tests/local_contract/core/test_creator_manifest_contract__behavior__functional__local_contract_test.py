"""Creator projection contract for generated content manifests."""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from core.evidence_contract import post_manifest_contract_issues  # noqa: E402


def _base_manifest() -> dict:
    return {
        "topicId": "topic",
        "contentType": "article",
        "entityRefs": [],
        "tagRefs": [],
        "sourceUrls": [],
        "generator": "agent",
        "createdAt": "2026-06-14T00:00:00Z",
        "updatedAt": "2026-06-14T00:00:00Z",
    }


def test_system_author_manifest_requires_visible_disclosure():
    manifest = {
        **_base_manifest(),
        "authorId": "agent_author_travel_000000001",
        "creatorProfileId": "agent_creator_travel_000000001",
        "creatorArchetype": "travel_blogger",
        "creatorProfileVersion": "1.0.0",
        "experienceClaimMode": "editorial_synthesis",
        "authorQualitySignals": {"qualityScore": 0.86, "fatigueScore": 0.2, "riskTier": "low"},
    }

    issues = post_manifest_contract_issues(manifest)
    assert any("creatorDisclosure" in issue for issue in issues), issues


def test_system_author_manifest_accepts_complete_projection():
    manifest = {
        **_base_manifest(),
        "authorId": "agent_author_travel_000000001",
        "creatorProfileId": "agent_creator_travel_000000001",
        "creatorArchetype": "travel_blogger",
        "creatorProfileVersion": "1.0.0",
        "creatorDisclosure": {
            "type": "platform_virtual_creator",
            "displayText": "平台虚拟创作者",
            "visible": True,
        },
        "experienceClaimMode": "editorial_synthesis",
        "authorQualitySignals": {"qualityScore": 0.86, "fatigueScore": 0.2, "riskTier": "low"},
    }

    assert post_manifest_contract_issues(manifest) == []


if __name__ == "__main__":
    test_system_author_manifest_requires_visible_disclosure()
    test_system_author_manifest_accepts_complete_projection()
    print("creator manifest contract tests passed")
