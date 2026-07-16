from __future__ import annotations

import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from content.release.canonical.gate import _post_contract_issues  # noqa: E402


def _video_leaf(manifest: dict) -> tuple[Path, Path]:
    root = Path(tempfile.mkdtemp(prefix="video_manifest_cover_contract_"))
    leaf = root / "posts" / "video" / "旅行" / "雪山视频" / "1"
    assets = leaf / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "clip.mp4").write_bytes(b"fake-mp4")
    return root, leaf


def test_video_manifest_with_remote_cover_contract_passes():
    manifest = {
        "contentType": "video",
        "assets": [
            {
                "assetId": "clip",
                "fileName": "clip.mp4",
                "kind": "video",
                "objectKey": "media/objects/sha256/aa/clip.mp4",
                "cdnUrl": "https://video.example.com/media/objects/sha256/aa/clip.mp4",
                "thumbnailUrl": "https://video.example.com/media/objects/sha256/aa/clip.mp4?variant=thumb&t=0",
                "coverUrl": "https://video.example.com/media/objects/sha256/aa/clip.mp4?variant=thumb&t=0",
                "coverStrategy": "first_frame",
                "coverFrameTimeMs": 0,
            }
        ],
    }
    root, leaf = _video_leaf(manifest)

    assert _post_contract_issues(leaf, root, manifest) == []


def test_video_manifest_without_cover_is_blocked():
    manifest = {
        "contentType": "video",
        "assets": [
            {
                "assetId": "clip",
                "fileName": "clip.mp4",
                "kind": "video",
                "objectKey": "media/objects/sha256/aa/clip.mp4",
            }
        ],
    }
    root, leaf = _video_leaf(manifest)

    issues = _post_contract_issues(leaf, root, manifest)

    assert any("missing thumbnailUrl or coverUrl" in issue for issue in issues)


def test_video_manifest_without_video_object_ref_is_blocked():
    manifest = {
        "contentType": "video",
        "assets": [
            {
                "assetId": "clip",
                "fileName": "clip.mp4",
                "kind": "video",
                "thumbnailUrl": "https://video.example.com/clip.mp4?variant=thumb&t=0",
            }
        ],
    }
    root, leaf = _video_leaf(manifest)

    issues = _post_contract_issues(leaf, root, manifest)

    assert any("missing videoUrl/objectKey/cdnUrl" in issue for issue in issues)
