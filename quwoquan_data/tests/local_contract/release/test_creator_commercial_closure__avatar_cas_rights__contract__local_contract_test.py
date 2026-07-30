"""Release-selected creators require traceable avatar/CAS/rights closure."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.canonical.creator_commercial_closure import (  # noqa: E402
    creator_commercial_closure_issues,
)


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


def _traceable_creator(tmp_path: Path) -> tuple[Path, dict]:
    creator = tmp_path / "creators/creator-a"
    content = b"avatar-cas"
    digest_hex = hashlib.sha256(content).hexdigest()
    digest = f"sha256:{digest_hex}"
    object_key = (
        f"media/objects/sha256/{digest_hex[:2]}/{digest_hex[2:4]}/"
        f"{digest_hex}.jpg"
    )
    physical = tmp_path / object_key
    physical.parent.mkdir(parents=True, exist_ok=True)
    physical.write_bytes(content)
    _write(creator / "_creator.json", {"creatorId": "creator-a"})
    _write(
        creator / "profile.json",
        {
            "creatorId": "creator-a",
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
                    "sha256": digest,
                    "objectKey": object_key,
                    "bytes": len(content),
                    "mimeType": "image/jpeg",
                }
            ]
        },
    )
    rights = _rights_document(
        asset_id="avatar-a",
        digest=digest,
        byte_count=len(content),
    )
    return creator, rights


def test_creator_commercial_closure__missing_avatar_blocks_release(
    tmp_path: Path,
) -> None:
    creator = tmp_path / "creators/creator-a"
    _write(creator / "_creator.json", {"creatorId": "creator-a"})
    _write(creator / "profile.json", {"creatorId": "creator-a"})
    _write(creator / "assets.refs.json", {"assets": []})

    assert creator_commercial_closure_issues(tmp_path) == [
        {"code": "creator_avatar_missing", "ref": "creator-a"}
    ]


def test_creator_commercial_closure__traceable_avatar_passes(
    tmp_path: Path,
) -> None:
    creator, rights = _traceable_creator(tmp_path)
    _write(creator / "rights_snapshots/avatar-a.json", rights)

    assert creator_commercial_closure_issues(tmp_path) == []


def test_creator_commercial_closure__identifiable_person_requires_obtained_model_release(
    tmp_path: Path,
) -> None:
    creator, rights = _traceable_creator(tmp_path)
    rights["depictsIdentifiablePerson"] = True
    _write(creator / "rights_snapshots/avatar-a.json", rights)

    assert creator_commercial_closure_issues(tmp_path) == [
        {"code": "creator_avatar_model_release_invalid", "ref": "creator-a"}
    ]

    rights["commercialRights"]["modelReleaseStatus"] = "obtained"
    _write(creator / "rights_snapshots/avatar-a.json", rights)
    assert creator_commercial_closure_issues(tmp_path) == []


def test_creator_commercial_closure__subject_identity_is_required(
    tmp_path: Path,
) -> None:
    creator, rights = _traceable_creator(tmp_path)
    rights.pop("depictsIdentifiablePerson")
    _write(creator / "rights_snapshots/avatar-a.json", rights)

    assert creator_commercial_closure_issues(tmp_path) == [
        {"code": "creator_avatar_subject_identity_missing", "ref": "creator-a"}
    ]


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("rightsAuditStatus", "unverified", "creator_avatar_rights_unverified"),
        ("usageScope", "editorial", "creator_avatar_rights_scope_invalid"),
        ("licenseName", "", "creator_avatar_license_invalid"),
        ("attribution", "", "creator_avatar_attribution_missing"),
        (
            "modelReleaseStatus",
            "editorial_only",
            "creator_avatar_model_release_invalid",
        ),
    ],
)
def test_creator_commercial_closure__commercial_rights_fail_closed(
    tmp_path: Path,
    field: str,
    value: object,
    expected_code: str,
) -> None:
    creator, rights = _traceable_creator(tmp_path)
    rights["commercialRights"][field] = value
    _write(creator / "rights_snapshots/avatar-a.json", rights)

    assert creator_commercial_closure_issues(tmp_path) == [
        {"code": expected_code, "ref": "creator-a"}
    ]
