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
from core.content_library import resolve_media_holding
from governance.creators import avatar, avatar_materialization
from support.media_fixture import admit_media_body


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
    admit_media_body(source)
    source_asset_id = "source-landscape"
    _write_json(
        source_root / "manifest.json",
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
    source_catalog = source_root / "source_catalog.json"
    _write_json(
        source_catalog,
        {
            "sources": [
                {
                    "sourceUnitId": "test__wikipedia__unit",
                    "fetchedAt": "2026-07-28T01:41:54Z",
                }
            ]
        },
    )
    source_catalog_body = source_catalog.read_bytes()
    file_page = (
        "https://commons.wikimedia.org/wiki/"
        "File:West_Lake,_Hangzhou_2025.jpg"
    )
    original_asset_url = (
        "https://upload.wikimedia.org/wikipedia/commons/1/17/"
        "West_Lake%2C_Hangzhou_2025.jpg"
    )
    source_asset = {
        "authorizationProof": file_page,
        "authorizationRequired": False,
        "bytes": len(source),
        "caption": "West Lake",
        "commercialAuthorizationStatus": "verified" if verified else "unverified",
        "creator": "Test Author",
        "credit": "Test Author",
        "height": 1400,
        "license": "CC BY 4.0",
        "modelReleaseStatus": "not_required",
        "normalizedFromUrl": original_asset_url,
        "pageRevisionId": 93458353,
        "rightsAuditIssues": [] if verified else ["license_unverified"],
        "rightsAuditStatus": "verified" if verified else "unverified",
        "sha256": digest,
        "sourceUrl": file_page,
        "termsUrl": "https://creativecommons.org/licenses/by/4.0",
        "usageScope": "app_publish",
        "watermarkKind": "none",
        "watermarkStatus": "absent",
        "accessPolicy": "open",
        "width": 1600,
    }
    commercial_rights = {
        "assetId": source_asset_id,
        "sourceKind": "licensed_source_image",
        "sourceUseMode": "licensed_adaptation",
        "canonicalFilePage": file_page,
        "snapshotUrl": file_page,
        "pageRevision": str(source_asset["pageRevisionId"]),
        "originalAssetUrl": original_asset_url,
        "author": source_asset["creator"],
        "source": file_page,
        "licenseName": source_asset["license"],
        "licenseShortName": source_asset["license"],
        "licenseUrl": source_asset["termsUrl"],
        "usageScope": source_asset["usageScope"],
        "attribution": f'{source_asset["creator"]} / {source_asset["license"]}',
        "caption": source_asset["caption"],
        "captionSource": "sourceAsset.caption",
        "modifications": "none; source bytes are used before avatar derivation",
        "fetchedAt": "2026-07-28T01:41:54Z",
        "snapshot": {
            "ref": "source_catalog.json",
            "sha256": "sha256:" + hashlib.sha256(source_catalog_body).hexdigest(),
            "bytes": len(source_catalog_body),
        },
        "asset": {
            "ref": object_key,
            "sha256": digest,
            "bytes": len(source),
            "mimeType": "image/jpeg",
            "width": source_asset["width"],
            "height": source_asset["height"],
        },
        "authorizationProof": source_asset["authorizationProof"],
        "modelReleaseStatus": source_asset["modelReleaseStatus"],
        "commercialAuthorizationStatus": source_asset[
            "commercialAuthorizationStatus"
        ],
        "watermarkStatus": source_asset["watermarkStatus"],
        "watermarkKind": source_asset["watermarkKind"],
        "accessPolicy": source_asset["accessPolicy"],
        "rightsAuditStatus": source_asset["rightsAuditStatus"],
        "rightsAuditIssues": source_asset["rightsAuditIssues"],
    }
    _write_json(
        source_root / "rights_snapshots/source-landscape.json",
        {
            "schema": "quwoquan_data.asset_rights_snapshot",
            "assetId": source_asset_id,
            "executionId": "20260728--test-homepage--test--pilot-001",
            "manifestAsset": {"assetId": source_asset_id},
            "commercialRights": commercial_rights,
            "sourceAsset": source_asset,
            "sourceAssetRef": "sources/test__wikipedia__unit/assets/source.jpg",
        },
    )

    persist_avatar = avatar.persist_creator_avatar

    def persist_avatar_with_rights(**kwargs: object) -> dict[str, bool]:
        evidence_document = dict(kwargs["evidence_document"])
        derivative_asset = evidence_document["asset"]
        derivative_rights = {
            **commercial_rights,
            "assetId": evidence_document["assetId"],
            "sourceKind": "creator_avatar_derivative",
            "captionSource": "rights_snapshots/source-landscape.json",
            "modifications": (
                "deterministic center-square crop [100, 0, 1500, 1400] from "
                "1600x1400; RGB; LANCZOS 1280x1280; WebP quality=85 method=4; "
                "derivative_policy_version=1"
            ),
            "asset": dict(derivative_asset),
        }
        evidence_document["commercialRights"] = derivative_rights
        kwargs["evidence_document"] = evidence_document
        return persist_avatar(**kwargs)

    monkeypatch.setattr(avatar, "persist_creator_avatar", persist_avatar_with_rights)

    def allow_current_carried_avatar_projection(target: Path) -> None:
        allowed = {
            Path("_creator.json"),
            Path("profile.json"),
            Path("assets.refs.json"),
            Path("works.refs.ndjson"),
            Path("media/avatar.webp"),
            Path("sources/avatar/evidence.json"),
            Path("sources/avatar/source.json"),
        }
        for path in target.rglob("*"):
            if path.is_symlink():
                raise avatar.CreatorAvatarError(
                    f"creator projection contains symlink: {path}"
                )
            if not path.is_file():
                continue
            relative = path.relative_to(target)
            if relative in allowed:
                continue
            if relative.parts[0] == "rights_snapshots" and path.suffix == ".json":
                continue
            if (
                len(relative.parts) == 3
                and relative.parts[:2] == ("_pool", "versions")
                and path.suffix == ".json"
            ):
                continue
            raise avatar.CreatorAvatarError(
                f"creator projection owns unexpected file: {path}"
            )

    monkeypatch.setattr(
        avatar_materialization,
        "_assert_replaceable_projection",
        allow_current_carried_avatar_projection,
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
    # Materialization gives the derivative body to the library and leaves the
    # versioned tree holding only the profile that cites it.
    assert not (publish / str(first["objectKey"])).exists()
    assert resolve_media_holding(str(first["sha256"])).is_file()
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


def test_materialize_creator_avatar_preserves_append_only_pool_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, publish, source_object_ref, source_asset_id = _fixture(
        tmp_path,
        monkeypatch,
    )
    history = publish / "creators/creator_test/records/1.json"
    history_body = b'{"recordSequence":1}\n'
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_bytes(history_body)

    avatar.materialize_creator_avatar(
        creator_ref="creator_test",
        source_object_ref=source_object_ref,
        source_asset_id=source_asset_id,
        confirm_non_identifiable_person=True,
    )

    assert history.read_bytes() == history_body


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
    assert not list(publish.rglob("*.webp"))
