# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-041
import hashlib
import json
from pathlib import Path

from core.release_layout import verify_release_holdings


def bundle(root: Path):
    key = "media/image/s/asset/test-asset/v1/source.jpg"
    body = b"independently carried bytes"
    media = root / "payload" / key
    media.parent.mkdir(parents=True)
    media.write_bytes(body)
    manifest = {"assets": [{"assetId": "test-asset", "publicSliceKey": key, "sha256": "sha256:" + hashlib.sha256(body).hexdigest(), "bytes": len(body)}]}
    (root / "payload/media_manifest.json").write_text(json.dumps(manifest))
    return media


def test_release_checks_manifest_bytes_without_library(tmp_path, monkeypatch):
    from core import content_library
    monkeypatch.setattr(content_library, "LIBRARY_ROOT", tmp_path / "no-library")
    bundle(tmp_path / "release")
    assert verify_release_holdings(tmp_path / "release") == ()
    assert not (tmp_path / "no-library").exists()


def test_release_missing_or_corrupt_media_cannot_pass(tmp_path):
    root = tmp_path / "release"
    media = bundle(root)
    media.write_bytes(b"corrupt")
    assert any("DRIFT" in issue for issue in verify_release_holdings(root))
    media.unlink()
    assert any("MISSING" in issue for issue in verify_release_holdings(root))


def test_release_ref_escape_and_symlink_fail_closed(tmp_path):
    root = tmp_path / "release"
    media = bundle(root)
    media.unlink()
    other = tmp_path / "external.jpg"
    other.write_bytes(b"external")
    media.symlink_to(other)
    assert any("SYMLINK" in issue for issue in verify_release_holdings(root))
    (root / "payload/media_manifest.json").write_text(json.dumps({"assets": [{"publicSliceKey": "../external.jpg", "sha256": "sha256:" + "a" * 64, "bytes": 8}]}))
    assert any("REF_INVALID" in issue for issue in verify_release_holdings(root))


def test_materialize_from_carried_owner_without_library(tmp_path):
    from core.media_asset_url import copy_release_media_objects
    root = tmp_path / "release"
    key = "media/image/s/asset/test-asset/v1/source.jpg"
    owner = "posts/image/风光/p0001/作品/1"
    source = root / "payload/objects" / owner / "media/01.jpg"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"published")
    digest = "sha256:" + hashlib.sha256(b"published").hexdigest()
    asset = {"assetId": "test-asset", "path": "media/01.jpg", "sha256": digest, "bytes": 9}
    (source.parent.parent / "manifest.json").write_text(json.dumps({"assets": [asset]}))
    row = {**asset, "publicSliceKey": key, "ownerRefs": [owner]}
    copy_release_media_objects(manifest={"assets": [row]}, release_root=root)
    target = root / "payload" / key
    assert target.read_bytes() == source.read_bytes()
    assert target.stat().st_ino != source.stat().st_ino


def test_media_manifest_uses_local_source_and_body(tmp_path):
    from core.media_asset_url import build_release_media_manifest
    ref = "image/风光/p0001/作品/1"
    obj = tmp_path / "posts" / ref
    (obj / "media").mkdir(parents=True)
    (obj / "media/01.jpg").write_bytes(b"image")
    digest = "sha256:" + hashlib.sha256(b"image").hexdigest()
    evidence = obj / "sources/s001/evidence.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_bytes(b"source")
    source = {"schema": "quwoquan_data.publish_source", "sourceId": "s001", "sourceUrl": "https://example.org/image", "sourceUseMode": "licensed_adaptation", "fetchedAt": "2026-09-09T00:00:00Z", "metadata": {}, "assets": [], "evidence": [{"path": "evidence.json", "sha256": "sha256:" + hashlib.sha256(b"source").hexdigest(), "bytes": 6, "kind": "source_snapshot"}]}
    (evidence.parent / "source.json").write_text(json.dumps(source))
    asset = {"assetId": "test-image", "path": "media/01.jpg", "sha256": digest, "bytes": 5, "kind": "image", "mimeType": "image/jpeg", "sourceRefs": ["sources/s001/source.json"]}
    (obj / "manifest.json").write_text(json.dumps({"objectRef": ref, "version": 1, "assets": [asset]}))
    result = build_release_media_manifest(release_id="test", post_refs=[ref], entity_refs=[], object_root=tmp_path)
    assert result["issues"] == []
    assert result["assets"][0]["rightsSnapshotRefs"] == [f"objects/posts/{ref}/sources/s001/source.json"]
    assert result["assets"][0]["bytes"] == 5
    asset["version"] = 2
    (obj / "manifest.json").write_text(json.dumps({"objectRef": ref, "version": 1, "assets": [asset]}))
    updated = build_release_media_manifest(release_id="next", post_refs=[ref], entity_refs=[], object_root=tmp_path)
    assert "/v2/" in updated["assets"][0]["publicSliceKey"]
    evidence.write_bytes(b"tampered")
    failed = build_release_media_manifest(release_id="test", post_refs=[ref], entity_refs=[], object_root=tmp_path)
    assert failed["assets"] == []
    assert any("evidence bytes drift" in issue for issue in failed["issues"])


def test_corrupt_existing_backup_is_not_silently_reused(tmp_path, monkeypatch):
    import pytest
    from core.content_library import MediaHoldingError, carry_media_reference
    monkeypatch.setenv("QWQ_CARRIED_MEDIA_ROOT", str(tmp_path / "backup"))
    body = tmp_path / "image.jpg"
    body.write_bytes(b"original")
    digest = hashlib.sha256(b"original").hexdigest()
    backed = carry_media_reference(body, sha256=digest)
    backed.write_bytes(b"damaged")
    with pytest.raises(MediaHoldingError, match="drift"):
        carry_media_reference(body, sha256=digest)
    assert backed.read_bytes() == b"damaged"
