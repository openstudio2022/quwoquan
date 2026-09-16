"""Release-selected creators require avatar identity/CAS quality closure only."""

from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.canonical.creator_avatar_quality import (  # noqa: E402
    creator_avatar_quality_issues,
)
from core.schema import assert_valid  # noqa: E402


def _write(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")


def _rights_document(
    *,
    asset_id: str,
    digest: str,
    byte_count: int,
    depicts_identifiable_person: bool = False,
) -> dict:
    return {
        "schema": "quwoquan_data.creator_avatar_rights_snapshot",
        "assetId": asset_id,
        "depictsIdentifiablePerson": depicts_identifiable_person,
        "manifestAsset": {"assetId": asset_id, "sha256": digest},
        "commercialRights": {
            "assetId": asset_id,
            "sourceKind": "licensed_creator_avatar",
            "sourceUseMode": "licensed_adaptation",
            "canonicalFilePage": "https://rights.example/avatar-a",
            "snapshotUrl": "https://rights.example/avatar-a",
            "pageRevision": "sha256:" + "b" * 64,
            "originalAssetUrl": "https://rights.example/avatar-a.jpg",
            "author": "Avatar Author",
            "source": "https://rights.example/avatar-a",
            "licenseName": "CC BY 4.0",
            "licenseShortName": "CC BY 4.0",
            "licenseUrl": "https://creativecommons.org/licenses/by/4.0",
            "usageScope": "app_publish",
            "attribution": "Avatar Author, CC BY 4.0",
            "caption": "Creator avatar",
            "captionSource": "rights owner metadata",
            "modifications": "square crop",
            "fetchedAt": "2026-07-28T00:00:00Z",
            "snapshot": {
                "ref": "evidence/avatar-a.json",
                "sha256": "sha256:" + "c" * 64,
                "bytes": 128,
            },
            "asset": {
                "ref": f"cas/{digest.removeprefix('sha256:')}.jpg",
                "sha256": digest,
                "bytes": byte_count,
                "mimeType": "image/jpeg",
                "width": 64,
                "height": 64,
            },
            "authorizationProof": "https://rights.example/avatar-a/license",
            "modelReleaseStatus": "not_required",
            "rightsAuditStatus": "verified",
            "rightsAuditIssues": [],
        },
    }


def _jpeg_bytes(size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", size, color)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=92)
    return output.getvalue()


def _write_avatar_source(
    creator: Path,
    rights: dict,
    *,
    object_key: str,
    source_asset: dict,
    derivative_binding: dict,
) -> None:
    assert_valid(rights, "release", "creator_avatar_rights_snapshot")
    evidence = json.dumps(rights, ensure_ascii=False).encode("utf-8")
    source = {
        "schema": "quwoquan_data.publish_source",
        "sourceId": "avatar",
        "sourceUrl": rights["commercialRights"]["canonicalFilePage"],
        "sourceUseMode": rights["commercialRights"]["sourceUseMode"],
        "fetchedAt": rights["commercialRights"]["fetchedAt"],
        "metadata": rights,
        "assets": [
            {
                **rights["commercialRights"],
                "assetId": rights["assetId"],
                "sha256": rights["manifestAsset"]["sha256"],
                "bytes": rights["commercialRights"]["asset"]["bytes"],
                "mimeType": rights["commercialRights"]["asset"]["mimeType"],
                "objectKey": object_key,
                "sourceAsset": source_asset,
                "derivativeBinding": derivative_binding,
            }
        ],
        "evidence": [
            {
                "path": "evidence.json",
                "sha256": "sha256:" + hashlib.sha256(evidence).hexdigest(),
                "bytes": len(evidence),
                "kind": "acquisition_receipt",
            }
        ],
    }
    assert_valid(source, "publish", "source")
    evidence_path = creator / "sources/avatar/evidence.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_bytes(evidence)
    _write(creator / "sources/avatar/source.json", source)


def _traceable_creator(tmp_path: Path) -> tuple[Path, dict, dict]:
    creator = tmp_path / "creators/creator-a"
    original = _jpeg_bytes((96, 80), (50, 110, 160))
    content = _jpeg_bytes((64, 64), (50, 110, 160))
    original_digest = "sha256:" + hashlib.sha256(original).hexdigest()
    digest_hex = hashlib.sha256(content).hexdigest()
    digest = f"sha256:{digest_hex}"
    object_key = (
        f"media/objects/sha256/{digest_hex[:2]}/{digest_hex[2:4]}/"
        f"{digest_hex}.jpg"
    )
    media_path = creator / "media/avatar.jpg"
    media_path.parent.mkdir(parents=True, exist_ok=True)
    media_path.write_bytes(content)
    derivative_binding = {
        "originalSha256": original_digest,
        "originalBytes": len(original),
        "originalMimeType": "image/jpeg",
        "policy": "source_unit_asset_budget",
        "profile": "image",
        "derivedSha256": digest,
        "derivedBytes": len(content),
        "derivedMimeType": "image/jpeg",
        "derivedExtension": ".jpg",
    }
    _write(creator / "_creator.json", {"creatorId": "creator-a"})
    _write(
        creator / "profile.json",
        {
            "creatorId": "creator-a",
            "sourceRefs": ["sources/avatar/source.json"],
            "avatarAsset": {
                "assetId": "avatar-a",
                "kind": "avatar",
                "sha256": digest,
            },
        },
    )
    _write(
        creator / "assets.refs.json",
        {
            "assets": [
                {
                    "assetId": "avatar-a",
                    "kind": "avatar",
                    "path": "media/avatar.jpg",
                    "sha256": digest,
                    "bytes": len(content),
                    "mimeType": "image/jpeg",
                    "width": 64,
                    "height": 64,
                    "sourceRefs": ["sources/avatar/source.json"],
                    "derivativeBinding": derivative_binding,
                }
            ]
        },
    )
    rights = _rights_document(
        asset_id="avatar-a",
        digest=digest,
        byte_count=len(content),
    )
    rights["commercialRights"].update(
        modifications="center-square crop and resize from 96x80 to 64x64",
        derivedModifications=["crop", "resize"],
    )
    rights["commercialRights"]["asset"].update(width=64, height=64)
    binding = {
        "object_key": object_key,
        "source_asset": {
            "sha256": original_digest,
            "bytes": len(original),
            "mimeType": "image/jpeg",
            "width": 96,
            "height": 80,
        },
        "derivative_binding": derivative_binding,
    }
    return creator, rights, binding


def test_creator_commercial_closure__missing_avatar_blocks_release(
    tmp_path: Path,
) -> None:
    creator = tmp_path / "creators/creator-a"
    _write(creator / "_creator.json", {"creatorId": "creator-a"})
    _write(creator / "profile.json", {"creatorId": "creator-a"})
    _write(creator / "assets.refs.json", {"assets": []})

    assert creator_avatar_quality_issues(tmp_path) == [
        {"code": "creator_avatar_missing", "ref": "creator-a"}
    ]


def test_creator_commercial_closure__traceable_avatar_passes(
    tmp_path: Path,
) -> None:
    creator, rights, binding = _traceable_creator(tmp_path)
    _write_avatar_source(creator, rights, **binding)

    assert creator_avatar_quality_issues(tmp_path) == []


def test_creator_avatar_quality__rights_and_model_release_do_not_filter_author(
    tmp_path: Path,
) -> None:
    creator, rights, binding = _traceable_creator(tmp_path)
    rights["depictsIdentifiablePerson"] = True

    rights["commercialRights"]["rightsAuditStatus"] = "unverified"
    rights["commercialRights"]["rightsAuditIssues"] = ["commercial proof unavailable"]
    rights["commercialRights"]["usageScope"] = "editorial"
    rights["commercialRights"]["modelReleaseStatus"] = "editorial_only"
    _write_avatar_source(creator, rights, **binding)

    assert creator_avatar_quality_issues(tmp_path) == []


def test_creator_avatar_quality__evidence_identity_is_required(
    tmp_path: Path,
) -> None:
    creator, rights, binding = _traceable_creator(tmp_path)
    rights["manifestAsset"]["sha256"] = "sha256:" + "f" * 64
    _write_avatar_source(creator, rights, **binding)

    assert creator_avatar_quality_issues(tmp_path) == [
        {"code": "creator_avatar_quality_evidence_missing", "ref": "creator-a"}
    ]
