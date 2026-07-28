from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.canonical import creator_projection
from content.release.canonical.object_transaction import (
    _project_entity_creator_closure,
)
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.environment.consistency import scan_release_contract


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_entity_creator_profile_id_closes_creator_object(tmp_path: Path) -> None:
    refs, objects = _project_entity_creator_closure(
        entity={"creatorProfileId": "qwq_creator_geo_editor_001"},
        staging=tmp_path,
    )
    assert refs == ["qwq_creator_geo_editor_001"]
    assert objects[0]["creatorRef"] == refs[0]
    assert objects[0]["packageRef"] == ("creator_objects/qwq_creator_geo_editor_001")
    assert (tmp_path / str(objects[0]["packageRef"]) / "profile.json").is_file()


def test_release_preflight_rejects_entity_creator_profile_outside_refs(
    tmp_path: Path,
) -> None:
    entity = tmp_path / "entities/地点/景区/测试实体"
    _write_json(
        entity / "manifest.json",
        {
            "schema": "quwoquan_data.entity_object",
            "finalContentRef": "page.md",
            "sourceCatalogRef": "source.json",
            "rightsRef": "rights.json",
            "creatorRefsRef": "creator.refs.json",
            "tagRefsRef": "tag.refs.json",
            "assetRefsRef": "asset.refs.json",
        },
    )
    _write_json(
        entity / "_entity.json",
        {"creatorProfileId": "qwq_creator_geo_editor_001"},
    )
    _write_json(entity / "creator.refs.json", {"creatorRefs": []})
    _write_json(entity / "tag.refs.json", {"tagRefs": []})
    _write_json(entity / "asset.refs.json", {"assets": []})
    _write_json(entity / "source.json", {"sources": []})
    _write_json(entity / "rights.json", {"assets": []})
    (entity / "page.md").write_text("# 测试实体\n", encoding="utf-8")

    report = scan_release_contract(
        {
            "schema": "quwoquan_data.release_desired_state",
            "releaseId": "release-test",
            "desiredRefs": {
                "entities": ["地点/景区/测试实体"],
                "posts": [],
                "creators": [],
                "tags": [],
            },
        },
        publish_root=tmp_path,
    )

    assert "entity_creator_closure_missing" in {issue["code"] for issue in report["blockingIssues"]}


def test_creator_avatar_projects_only_from_traceable_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = tmp_path / "creator_pool"
    publish = tmp_path / "publish"
    avatar = b"traceable-avatar"
    digest_hex = hashlib.sha256(avatar).hexdigest()
    digest = f"sha256:{digest_hex}"
    object_key = f"media/objects/sha256/{digest_hex[:2]}/{digest_hex[2:4]}/{digest_hex}.jpg"
    physical = publish / object_key
    physical.parent.mkdir(parents=True, exist_ok=True)
    physical.write_bytes(avatar)
    rights_ref = "evidence/avatar-rights.json"
    _write_json(
        pool / rights_ref,
        {
            "assetId": "avatar-test",
            "manifestAsset": {
                "assetId": "avatar-test",
                "sha256": digest,
            },
        },
    )
    profile = {
        "creatorProfileId": "creator_test",
        "authorId": "author_test",
        "subAccountId": "author_test",
        "displayName": "测试作者",
        "userHandle": "creator_test",
        "headline": "测试",
        "bio": "测试",
        "creatorArchetype": "editor",
        "status": "active",
        "publicProfileTagRefs": [],
        "disclosure": {
            "type": "platform_virtual_creator",
            "displayText": "测试",
            "visible": True,
        },
        "avatarAsset": {
            "assetId": "avatar-test",
            "kind": "avatar",
            "sha256": digest,
            "objectKey": object_key,
            "bytes": len(avatar),
            "mimeType": "image/jpeg",
            "rightsSnapshotRef": rights_ref,
        },
    }
    profile_path = pool / "profiles/system/creator_test.creator.yaml"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(yaml.safe_dump(profile, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(creator_projection, "CONTROL_PLANE_CREATOR_POOL_ROOT", pool)
    monkeypatch.setattr(creator_projection, "PUBLISH_ROOT", publish)

    target = tmp_path / "creator"
    creator_projection.project_creator_object("creator_test", target)

    public_profile = json.loads((target / "profile.json").read_text(encoding="utf-8"))
    assert public_profile["avatarAsset"] == {
        "assetId": "avatar-test",
        "kind": "avatar",
        "sha256": digest,
    }
    assert "avatarUrl" not in public_profile
    assets = json.loads((target / "assets.refs.json").read_text(encoding="utf-8"))
    assert assets["assets"][0]["objectKey"] == object_key
    assert (target / "rights_snapshots/avatar-rights.json").is_file()


def test_creator_avatar_rejects_untraceable_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = tmp_path / "creator_pool"
    profile_path = pool / "profiles/system/creator_test.creator.yaml"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        yaml.safe_dump(
            {
                "creatorProfileId": "creator_test",
                "authorId": "author_test",
                "subAccountId": "author_test",
                "displayName": "测试作者",
                "status": "active",
                "avatarAsset": {
                    "assetId": "avatar-test",
                    "kind": "avatar",
                    "sha256": "sha256:" + "a" * 64,
                },
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(creator_projection, "CONTROL_PLANE_CREATOR_POOL_ROOT", pool)

    with pytest.raises(ObjectTransactionError, match="private CAS"):
        creator_projection.project_creator_object("creator_test", tmp_path / "creator")
