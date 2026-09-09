"""Release 拥有可独立搬运的交付字节；library 缺席不影响完整包校验。"""
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-022
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.release_layout import (
    media_holdings_digest, objects_merkle, payload_file,
    release_holdings, verify_release_holdings,
)


def _release_with_media(root: Path, *, bodies: dict[str, bytes]) -> None:
    objects = payload_file(root, "objects")
    objects.mkdir(parents=True, exist_ok=True)
    (objects / "post.json").write_text('{"ref": "post-1"}', encoding="utf-8")
    assets = []
    for name, body in bodies.items():
        key = f"media/image/s/asset/{Path(name).stem}/v1/source.jpg"
        target = payload_file(root, key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        assets.append({"publicSliceKey": key, "sha256": "sha256:" + hashlib.sha256(body).hexdigest(), "bytes": len(body)})
    payload_file(root, "media_manifest.json").write_text(json.dumps({"assets": assets}))


def test_objects_merkle_ignores_distribution_media(tmp_path):
    first, second = tmp_path / "r1", tmp_path / "r2"
    _release_with_media(first, bodies={"a.jpg": b"cover-a"})
    _release_with_media(second, bodies={"a.jpg": b"cover-a", "b.jpg": b"cover-b"})
    assert objects_merkle(first) == objects_merkle(second)
    assert media_holdings_digest(first) != media_holdings_digest(second)


def test_holdings_describe_actual_independent_media_bytes(tmp_path):
    _release_with_media(tmp_path, bodies={"a.jpg": b"cover-a"})
    path, digest, size = release_holdings(tmp_path)[0]
    assert path == "image/s/asset/a/v1/source.jpg"
    assert size == 7
    assert digest == "sha256:" + hashlib.sha256(b"cover-a").hexdigest()
    assert verify_release_holdings(tmp_path) == ()


def test_substituted_body_fails_manifest_and_changes_media_digest(tmp_path):
    _release_with_media(tmp_path, bodies={"a.jpg": b"cover-a"})
    frozen = media_holdings_digest(tmp_path)
    payload_file(tmp_path, "media/image/s/asset/a/v1/source.jpg").write_bytes(b"tampered")
    assert media_holdings_digest(tmp_path) != frozen
    assert any("DRIFT" in issue for issue in verify_release_holdings(tmp_path))


def test_library_absence_is_irrelevant_but_missing_bundle_file_is_not(tmp_path, monkeypatch):
    from core import content_library
    monkeypatch.setattr(content_library, "LIBRARY_ROOT", tmp_path / "absent-library")
    release = tmp_path / "release"
    _release_with_media(release, bodies={"a.jpg": b"cover-a"})
    assert verify_release_holdings(release) == ()
    payload_file(release, "media/image/s/asset/a/v1/source.jpg").unlink()
    assert any("MISSING" in issue for issue in verify_release_holdings(release))
    assert not (tmp_path / "absent-library").exists()
