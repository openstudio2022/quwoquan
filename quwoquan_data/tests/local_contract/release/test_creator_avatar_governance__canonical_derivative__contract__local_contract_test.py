"""Creator avatar governance checks canonical CAS, readability and quality only."""

from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.release.canonical import creator_projection
from governance.creators import avatar


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _source_image() -> bytes:
    image = Image.new("RGB", (1600, 1400), (50, 110, 160))
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=92)
    return output.getvalue()


def _fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    verified: bool = True,
) -> tuple[Path, Path, str, str]:
    pool = tmp_path / "creator_pool"
    publish = tmp_path / "publish"
    monkeypatch.setattr(avatar, "CONTROL_PLANE_CREATOR_POOL_ROOT", pool)
    monkeypatch.setattr(avatar, "PUBLISH_ROOT", publish)
    monkeypatch.setattr(creator_projection, "CONTROL_PLANE_CREATOR_POOL_ROOT", pool)
    monkeypatch.setattr(creator_projection, "PUBLISH_ROOT", publish)

    creator_ref = "creator_test"
    profile = pool / "profiles/system_builtin/creator_test.creator.yaml"
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(
        "\n".join(
            [
                f"creatorProfileId: {creator_ref}",
                "version: 1",
                "authorId: author_test",
                "personaId: author_test",
                "displayName: 测试作者",
                "userHandle: creator_test",
                "headline: 测试",
                "bio: 测试",
                "creatorArchetype: editor",
                "status: active",
                "admission:",
                "  processResult: completed",
                "  qualityResult: passed",
                "  evidenceRef: evidence/author-admission.json",
                f"  evidenceDigest: sha256:{'0' * 64}",
                "publicProfileTagRefs: []",
                "disclosure:",
                "  type: platform_virtual_creator",
                "  displayText: 测试",
                "  visible: true",
                "",
            ]
        ),
        encoding="utf-8",
    )

    source_object_ref = "entities/地点/景区/测试景区"
    source_root = publish / source_object_ref
    source = _source_image()
    digest_hex = hashlib.sha256(source).hexdigest()
    digest = f"sha256:{digest_hex}"
    object_key = (
        f"media/objects/sha256/{digest_hex[:2]}/{digest_hex[2:4]}/{digest_hex}.jpg"
    )
    physical = publish / object_key
    physical.parent.mkdir(parents=True, exist_ok=True)
    physical.write_bytes(source)
    source_asset_id = "source-landscape"
    _write_json(
        source_root / "asset.refs.json",
        {
            "assets": [
                {
                    "assetId": source_asset_id,
                    "sha256": digest,
                    "objectKey": object_key,
                    "bytes": len(source),
                }
            ]
        },
    )
    _write_json(
        source_root / "source_catalog.json",
        {
            "sources": [
                {
                    "sourceUnitId": "test__wikipedia__unit",
                    "fetchedAt": "2026-07-28T01:41:54Z",
                }
            ]
        },
    )
    source_asset = {
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:West_Lake,_Hangzhou_2025.jpg",
        "bytes": len(source),
        "caption": "West Lake",
        "creator": "Test Author",
        "credit": "Test Author",
        "height": 1400,
        "license": "CC BY 4.0",
        "modelReleaseStatus": "not_required",
        "normalizedFromUrl": "https://upload.wikimedia.org/wikipedia/commons/1/17/West_Lake%2C_Hangzhou_2025.jpg",
        "pageRevisionId": 93458353,
        "rightsAuditIssues": [] if verified else ["license_unverified"],
        "rightsAuditStatus": "verified" if verified else "unverified",
        "sha256": digest,
        "sourceUrl": "https://commons.wikimedia.org/wiki/File:West_Lake,_Hangzhou_2025.jpg",
        "termsUrl": "https://creativecommons.org/licenses/by/4.0",
        "usageScope": "app_publish",
        "width": 1600,
    }
    _write_json(
        source_root / "rights_snapshots/source-landscape.json",
        {
            "schema": "quwoquan_data.asset_rights_snapshot",
            "assetId": source_asset_id,
            "executionId": "20260728--test-homepage--test--pilot-001",
            "manifestAsset": {"assetId": source_asset_id},
            "sourceAsset": source_asset,
            "sourceAssetRef": "sources/test__wikipedia__unit/assets/source.jpg",
        },
    )
    return pool, publish, source_object_ref, source_asset_id


def test_materialize_creator_avatar_is_traceable_and_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool, publish, source_object_ref, source_asset_id = _fixture(
        tmp_path,
        monkeypatch,
    )

    first = avatar.materialize_creator_avatar(
        creator_ref="creator_test",
        source_object_ref=source_object_ref,
        source_asset_id=source_asset_id,
        confirm_non_identifiable_person=True,
    )
    second = avatar.materialize_creator_avatar(
        creator_ref="creator_test",
        source_object_ref=source_object_ref,
        source_asset_id=source_asset_id,
        confirm_non_identifiable_person=True,
    )

    assert first["idempotent"] is False
    assert second["idempotent"] is True
    assert first["cropBox"] == [100, 0, 1500, 1400]
    assert first["dimensions"] == [1280, 1280]
    assert (publish / str(first["objectKey"])).is_file()
    evidence = json.loads(
        (pool / str(first["evidenceRef"])).read_text(encoding="utf-8")
    )
    assert evidence["processResult"] == "completed"
    assert evidence["qualityResult"] == "passed"
    assert evidence["checks"] == {
        "format": "passed",
        "readable": "passed",
        "clarity": "passed",
        "safety": "passed",
    }
    assert evidence["sourceEvidence"]["ref"].endswith(
        "rights_snapshots/source-landscape.json"
    )
    profile = json.loads(
        (publish / "creators/creator_test/profile.json").read_text(encoding="utf-8")
    )
    assert profile["avatarAsset"]["sha256"] == first["sha256"]


def test_materialize_creator_avatar_requires_subject_attestation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool, _, source_object_ref, source_asset_id = _fixture(tmp_path, monkeypatch)

    with pytest.raises(avatar.CreatorAvatarError, match="confirm-non-identifiable"):
        avatar.materialize_creator_avatar(
            creator_ref="creator_test",
            source_object_ref=source_object_ref,
            source_asset_id=source_asset_id,
            confirm_non_identifiable_person=False,
        )

    profile = next((pool / "profiles").rglob("*.creator.yaml"))
    assert "avatarAsset" not in profile.read_text(encoding="utf-8")


def test_materialize_creator_avatar_accepts_unverified_source_rights_for_all_environments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool, publish, source_object_ref, source_asset_id = _fixture(
        tmp_path,
        monkeypatch,
        verified=False,
    )

    result = avatar.materialize_creator_avatar(
        creator_ref="creator_test",
        source_object_ref=source_object_ref,
        source_asset_id=source_asset_id,
        confirm_non_identifiable_person=True,
    )

    profile = next((pool / "profiles").rglob("*.creator.yaml"))
    assert "avatarAsset" in profile.read_text(encoding="utf-8")
    projected = json.loads(
        (publish / "creators/creator_test/profile.json").read_text(encoding="utf-8")
    )
    assert projected["avatarAsset"]["sha256"] == result["sha256"]


def test_materialize_creator_avatar_rolls_back_new_artifacts_on_projection_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool, publish, source_object_ref, source_asset_id = _fixture(
        tmp_path,
        monkeypatch,
    )
    unexpected = publish / "creators/creator_test/unexpected.txt"
    unexpected.parent.mkdir(parents=True, exist_ok=True)
    unexpected.write_text("user-owned", encoding="utf-8")

    with pytest.raises(avatar.CreatorAvatarError, match="unexpected file"):
        avatar.materialize_creator_avatar(
            creator_ref="creator_test",
            source_object_ref=source_object_ref,
            source_asset_id=source_asset_id,
            confirm_non_identifiable_person=True,
        )

    profile = next((pool / "profiles").rglob("*.creator.yaml"))
    assert "avatarAsset" not in profile.read_text(encoding="utf-8")
    assert unexpected.read_text(encoding="utf-8") == "user-owned"
    assert not list((pool / "evidence/avatar_rights").rglob("*.json"))
    assert not list((publish / "media/objects/sha256").rglob("*.webp"))
