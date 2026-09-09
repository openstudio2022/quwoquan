# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-041
import json

import pytest

from core.release_media_binding import bind_release_object_media_assets


def test_release_projection_does_not_rewrite_source_review_or_records(tmp_path):
    obj = tmp_path / "entities/地点/中国/四川省/成都市/公园/p0001/人民公园/1"
    obj.mkdir(parents=True)
    asset = {"assetId": "image-1", "kind": "image", "sha256": "sha256:" + "a" * 64, "objectKey": "media/objects/private", "path": "media/01.jpg"}
    (obj / "manifest.json").write_text(json.dumps({"assets": [asset]}))
    evidence = b'{ "assetId": "original-id-not-in-delivery", "objectKey": "source/original" }\n'
    paths = [obj / "sources/s001/evidence.json", obj / "sources/s001/source.json", obj / "content_review.json", obj / "records/1.json"]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(evidence)
    bind_release_object_media_assets(objects_root=tmp_path, manifest={"assets": [{"assetId": "image-1", "kind": "image", "sha256": "sha256:" + "a" * 64, "ownerRefs": [obj.relative_to(tmp_path).as_posix()]}]})
    for path in paths:
        assert path.read_bytes() == evidence
    result = json.loads((obj / "manifest.json").read_bytes())
    assert "objectKey" not in result["assets"][0]
    assert result["assets"][0]["path"] == "media/01.jpg"


def test_release_projection_rejects_asset_owned_by_another_object(tmp_path):
    obj = tmp_path / "posts/image/风光/p0001/标题/1"
    obj.mkdir(parents=True)
    (obj / "manifest.json").write_text(json.dumps({"assets": [{"assetId": "image-1", "kind": "image", "sha256": "sha256:" + "a" * 64}]}))
    with pytest.raises(ValueError, match="owner"):
        bind_release_object_media_assets(objects_root=tmp_path, manifest={"assets": [{"assetId": "image-1", "kind": "image", "sha256": "sha256:" + "a" * 64, "ownerRefs": ["posts/image/other/1"]}]})
