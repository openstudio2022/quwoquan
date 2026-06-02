"""download 下图能力回归：sniff_image_ext / curated_images_for_entity / fetch_image / handler 接线。

不依赖联网：fetch_image 单测 monkeypatch _http_get_bytes；handler 端到端 monkeypatch fetch_image。
可直接运行 python3 quwoquan_data/tests/test_download_images.py
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="dl_images_"))
os.environ["QWQ_DATA_ROOT"] = str(_TMP)
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _common.io import read_json, write_json  # noqa: E402
from _common.paths import batch_command_root, batch_inputs_dir, ensure_batch_layout  # noqa: E402
import download.fetch as fetch_mod  # noqa: E402
import download.handler as handler_mod  # noqa: E402
from download.handler import handle_download  # noqa: E402
from download.source_inputs import curated_images_for_entity  # noqa: E402

_TASK = "旅行/地域/四川省/景区/景区全覆盖"
_EID = "稻城亚丁"

_JPEG = b"\xff\xd8\xff\xe0" + b"\x10" * 4000
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 4000
_GIF = b"GIF89a" + b"\x00" * 4000
_WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 4000


def test_sniff_image_ext():
    assert fetch_mod.sniff_image_ext(_JPEG) == ".jpg"
    assert fetch_mod.sniff_image_ext(_PNG) == ".png"
    assert fetch_mod.sniff_image_ext(_GIF) == ".gif"
    assert fetch_mod.sniff_image_ext(_WEBP) == ".webp"
    # content-type 兜底
    assert fetch_mod.sniff_image_ext(b"????rest", "image/png") == ".png"
    # 非图片
    assert fetch_mod.sniff_image_ext(b"<html>oops</html>", "text/html") is None


def test_curated_images_merges_and_dedups():
    ensure_batch_layout(_TASK, "b_img_curate", "download")
    inputs_dir = batch_inputs_dir(_TASK, "b_img_curate", "download", "source_plan")
    inputs_dir.mkdir(parents=True, exist_ok=True)
    doc = {
        "imageUrls": [
            "https://img.example/a.jpg",
            {"url": "https://img.example/b.jpg", "license": "CC BY-SA 4.0", "credit": "Alice"},
            "https://img.example/a.jpg",  # 重复，应去重
        ],
        "sources": [
            {"source_id": "s1", "url": "https://x.example/g", "imageUrls": ["https://img.example/c.jpg"]},
        ],
    }
    write_json(inputs_dir / f"{_EID}.json", doc)
    specs = curated_images_for_entity(_TASK, "b_img_curate", _EID)
    urls = [s["url"] for s in specs]
    assert urls == [
        "https://img.example/a.jpg",
        "https://img.example/b.jpg",
        "https://img.example/c.jpg",
    ], urls
    assert specs[1]["license"] == "CC BY-SA 4.0"
    assert specs[1]["credit"] == "Alice"


def test_fetch_image_writes_and_rejects_non_image():
    out = Path(tempfile.mkdtemp(prefix="img_"))
    orig = fetch_mod._http_get_bytes
    try:
        fetch_mod._http_get_bytes = lambda url, **kw: (200, _JPEG, "image/jpeg")
        meta = fetch_mod.fetch_image("https://img.example/a.jpg", out, index=1)
        assert meta and meta["fileName"] == "img_01.jpg"
        assert (out / "img_01.jpg").is_file()
        assert meta["bytes"] == len(_JPEG)
        # HTML 错误页伪装 → 拒绝
        fetch_mod._http_get_bytes = lambda url, **kw: (200, b"<html>err</html>" * 500, "text/html")
        assert fetch_mod.fetch_image("https://img.example/x", out, index=2) is None
        # 过小 → 拒绝
        fetch_mod._http_get_bytes = lambda url, **kw: (200, b"\xff\xd8\xff", "image/jpeg")
        assert fetch_mod.fetch_image("https://img.example/s", out, index=3) is None
        # 非 200 → 拒绝
        fetch_mod._http_get_bytes = lambda url, **kw: (404, _JPEG, "image/jpeg")
        assert fetch_mod.fetch_image("https://img.example/n", out, index=4) is None
    finally:
        fetch_mod._http_get_bytes = orig


def test_handle_download_fetches_images_into_index():
    batch = "b_img_handler"
    ensure_batch_layout(_TASK, batch, "download")
    inputs_dir = batch_inputs_dir(_TASK, batch, "download", "source_plan")
    inputs_dir.mkdir(parents=True, exist_ok=True)
    doc = {
        "sources": [{"source_id": "s1", "platform": "web", "url": "https://x.invalid/g", "body": "正文兜底"}],
        "imageUrls": [
            "https://img.invalid/a.jpg",
            {"url": "https://img.invalid/b.jpg", "license": "CC BY-SA 4.0", "credit": "Bob"},
        ],
    }
    write_json(inputs_dir / f"{_EID}.json", doc)

    def _fake_fetch_image(url, images_dir, *, index, min_bytes=3000):
        images_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"img_{index:02d}.jpg"
        (images_dir / file_name).write_bytes(_JPEG)
        return {
            "url": url,
            "fileName": file_name,
            "statusCode": 200,
            "contentType": "image/jpeg",
            "bytes": len(_JPEG),
            "sha256": "deadbeef",
        }

    orig = handler_mod.fetch_image
    try:
        handler_mod.fetch_image = _fake_fetch_image
        handle_download(argparse.Namespace(task=_TASK, batch=batch, entity_ids=_EID))
    finally:
        handler_mod.fetch_image = orig

    images_dir = batch_command_root(_TASK, batch, "download") / "sources" / _EID / "images"
    index_file = images_dir / "index.json"
    assert index_file.is_file(), f"missing {index_file}"
    data = read_json(index_file)
    assert data["imageCount"] == 2, data
    assert (images_dir / "img_01.jpg").is_file()
    assert data["images"][1]["license"] == "CC BY-SA 4.0"
    assert data["images"][1]["credit"] == "Bob"


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"download images tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
