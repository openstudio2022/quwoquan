# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/spec.md#gwt-001
"""The checked-in golden publish set must close one replayable media release."""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
PUBLISH = ROOT / "quwoquan_data" / "publish"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.canonical.aggregate_release import (  # noqa: E402
    build_aggregate_release,
)
from content.release.environment.consistency import (  # noqa: E402
    scan_release_contract,
)
from core.release_layout import payload_file  # noqa: E402


def _object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), path
    return value


def _strings(value: object) -> Iterable[str]:
    if isinstance(value, Mapping):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)
    elif isinstance(value, str):
        yield value


def _values_for_keys(value: object, keys: set[str]) -> Iterable[object]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in keys:
                yield child
            yield from _values_for_keys(child, keys)
    elif isinstance(value, list):
        for child in value:
            yield from _values_for_keys(child, keys)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _manifest_paths(kind: str) -> list[Path]:
    return sorted((PUBLISH / kind).rglob("manifest.json"))


def test_geo_content_trinity_golden_publish_closes_one_media_authority(
    tmp_path: Path,
) -> None:
    entity_manifests = _manifest_paths("entities")
    post_manifests = _manifest_paths("posts")
    assert entity_manifests, "golden publish must contain a homepage object"
    assert post_manifests, "golden publish must contain content objects"

    published_manifests = [_object(path) for path in entity_manifests + post_manifests]
    execution_ids = sorted(
        {
            str(manifest.get("executionId") or "")
            for manifest in published_manifests
            if str(manifest.get("executionId") or "")
        }
    )
    assert execution_ids
    assert {
        str(manifest.get("contentType") or "")
        for manifest in published_manifests
        if manifest.get("contentType")
    } == {"article", "image", "video"}

    result = build_aggregate_release(
        publish_root=PUBLISH,
        release_root=tmp_path / "releases",
        release_id="geo-content-trinity-golden-release",
        execution_ids=execution_ids,
    )
    release = Path(str(result["releaseRoot"]))
    desired = _object(payload_file(release, "desired_state.json"))
    desired_refs = desired["desiredRefs"]
    assert isinstance(desired_refs, dict)
    assert desired_refs["entities"]
    assert desired_refs["posts"]
    assert desired_refs["creators"]

    media = _object(payload_file(release, "media_manifest.json"))
    assert media["sourceOwner"] == "qwq_data"
    assert media["issues"] == []
    rows = media["assets"]
    assert isinstance(rows, list) and rows
    authority = {
        str(row["assetId"]): row
        for row in rows
        if isinstance(row, dict)
    }
    assert len(authority) == len(rows)

    owner_refs = {
        str(owner)
        for row in authority.values()
        for owner in row["ownerRefs"]
    }
    assert any(ref.startswith("creators/") for ref in owner_refs)
    assert any(ref.startswith("entities/") for ref in owner_refs)
    assert any(ref.startswith("posts/image/") for ref in owner_refs)
    assert any(ref.startswith("posts/video/") for ref in owner_refs)
    assert {
        str(row["kind"])
        for row in authority.values()
        if any(
            str(owner).startswith("creators/")
            for owner in row["ownerRefs"]
        )
    } == {"avatar"}
    assert {
        str(row["kind"])
        for row in authority.values()
        if any(
            str(owner).startswith("entities/")
            for owner in row["ownerRefs"]
        )
    } == {"image"}
    assert {
        str(row["kind"])
        for row in authority.values()
        if any(
            str(owner).startswith("posts/image/")
            for owner in row["ownerRefs"]
        )
    } == {"image"}
    assert {
        str(row["kind"])
        for row in authority.values()
        if any(
            str(owner).startswith("posts/video/")
            for owner in row["ownerRefs"]
        )
    } == {"image", "video"}

    for asset_id, row in authority.items():
        assert "objectKey" not in row
        public_slice = str(row["publicSliceKey"])
        assert public_slice.startswith(
            f"media/{row['kind']}/s/asset/"
        )
        public_bytes = payload_file(release, public_slice)
        assert public_bytes.is_file()
        assert public_bytes.stat().st_size == row["bytes"]
        assert _sha256(public_bytes) == row["sha256"]

        rights_by_owner: dict[str, int] = {}
        for rights_ref in row["rightsSnapshotRefs"]:
            rights_ref = str(rights_ref)
            rights_path = payload_file(release, rights_ref)
            assert rights_path.is_file()
            rights = _object(rights_path)
            manifest_asset = rights.get("manifestAsset")
            assert isinstance(manifest_asset, dict)
            assert rights["assetId"] == asset_id
            assert manifest_asset["assetId"] == asset_id
            assert manifest_asset["sha256"] == row["sha256"]
            assert any(
                key in rights
                for key in ("sourceAsset", "sourceAssets", "commercialRights")
            )
            assert any(
                str(value).strip()
                for value in _values_for_keys(
                    rights,
                    {"license", "licenseName", "authorizationProof"},
                )
            )
            owner = rights_ref.removeprefix("objects/").split(
                "/rights_snapshots/",
                1,
            )[0]
            assert owner in row["ownerRefs"]
            rights_by_owner[owner] = rights_by_owner.get(owner, 0) + 1
        assert set(rights_by_owner) == set(row["ownerRefs"])

    for kind in ("entities", "posts"):
        for ref in desired_refs[kind]:
            object_root = payload_file(release, f"objects/{kind}/{ref}")
            manifest = _object(object_root / "manifest.json")
            source_catalog_ref = str(manifest.get("sourceCatalogRef") or "")
            assert source_catalog_ref
            assert (object_root / source_catalog_ref).is_file()

            attestation = _object(object_root / "attestation.json")
            reviewer = attestation.get("independentReviewer")
            assert attestation["decision"] == "approved"
            assert attestation["executionBinding"] == "frozen"
            assert isinstance(reviewer, dict)
            assert reviewer["status"] == "passed"
            assert reviewer["runId"]
            assert reviewer["resultHash"]

            source_units = {
                value.split("/", 2)[1]
                for value in _strings(manifest)
                if value.startswith("sources/")
                and len(value.split("/", 2)) == 3
            }
            assert len(source_units) == 1, (
                f"{kind}/{ref} must remain inside one source unit, "
                f"got {source_units}"
            )

    article_refs = [
        ref
        for ref in desired_refs["posts"]
        if str(ref).startswith("article/")
    ]
    assert article_refs
    for ref in article_refs:
        article = _object(
            payload_file(release, f"objects/posts/{ref}/manifest.json")
        )
        assert article["generator"] == "agent"
        assert article["reviewDecision"] == "approved"
        article_assets = [
            asset
            for asset in article["assets"]
            if isinstance(asset, dict)
        ]
        if not article_assets:
            assert article["publishMediaMode"] == "text_only"
        for asset in article_assets:
            asset_id = str(asset["assetId"])
            assert asset_id in authority
            assert f"posts/{ref}" in authority[asset_id]["ownerRefs"]

    video_refs = [
        ref
        for ref in desired_refs["posts"]
        if str(ref).startswith("video/")
    ]
    assert video_refs
    for ref in video_refs:
        video = _object(
            payload_file(release, f"objects/posts/{ref}/manifest.json")
        )
        assets = {
            str(asset["assetId"]): asset
            for asset in video["assets"]
            if isinstance(asset, dict)
        }
        primary = next(
            asset
            for asset in assets.values()
            if asset.get("kind") == "video"
        )
        poster = assets[str(primary["posterAssetId"])]
        assert poster["kind"] == "image"
        assert poster["role"] == "cover"
        assert authority[str(primary["assetId"])]["kind"] == "video"
        assert authority[str(poster["assetId"])]["kind"] == "image"

    release_object_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(payload_file(release, "objects").rglob("*.json"))
    )
    assert '"objectKey"' not in release_object_text
    assert "media/objects/sha256/" not in release_object_text

    first = rows[0]
    assert isinstance(first, dict)
    first["ownerRefs"] = ["posts/article/not-the-owner/1"]
    first["rightsSnapshotRefs"] = [
        "objects/posts/article/not-the-owner/1/rights_snapshots/../forged.json"
    ]
    payload_file(release, "media_manifest.json").write_text(
        json.dumps(media, ensure_ascii=False),
        encoding="utf-8",
    )
    report = scan_release_contract(desired, release_root=release)
    codes = {
        str(issue["code"])
        for issue in report["blockingIssues"]
    }
    assert "release_media_owner_closure_mismatch" in codes
    assert "release_media_rights_refs_invalid" in codes
