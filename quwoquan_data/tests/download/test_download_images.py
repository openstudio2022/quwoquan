"""download 下图能力回归：sniff_image_ext / curated_images_for_entity / fetch_image / handler 接线。

不依赖联网：fetch_image 单测 monkeypatch _http_get_bytes；handler 端到端 monkeypatch fetch_image。
可直接运行 python3 quwoquan_data/tests/download/test_download_images.py
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import argparse
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="dl_images_"))
os.environ["QWQ_DATA_ROOT"] = str(_TMP)
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")

sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.io import read_json, write_json  # noqa: E402
from _common.paths import STAGE_DOWNLOAD, ensure_batch_layout  # noqa: E402
from _common.source_unit import resolve_entity_object_dir  # noqa: E402
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


def _real_jpeg(seed: int, *, size=(800, 600)) -> bytes:
    """生成可被 PIL 解析、达到像素门、且彼此视觉不同（避开感知去重）的真实 JPEG。"""
    import io as _io

    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, size=(size[1], size[0], 3), dtype="uint8")
    buf = _io.BytesIO()
    Image.fromarray(arr, "RGB").save(buf, format="JPEG", quality=85)
    return buf.getvalue()


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
    inputs_dir = resolve_entity_object_dir(_TASK, "b_img_curate", _EID, etype_hint="景区") / STAGE_DOWNLOAD
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
    write_json(inputs_dir / "source_plan.json", doc)
    specs = curated_images_for_entity(_TASK, "b_img_curate", _EID, "景区")
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


def test_handle_download_fetches_images_into_source_unit():
    """新布局：图片落到首个来源单元 assets/，写 assets/index.json，无对象级散 images/。"""
    from _common.source_unit import iter_source_units, resolve_entity_object_dir

    batch = "b_img_handler"
    ensure_batch_layout(_TASK, batch, "download")
    # 两张视觉不同、达到像素门、带真实相关性的图（满足 min count≥2 + relevance + pixels）。
    img_a = _real_jpeg(11)
    img_b = _real_jpeg(97)
    doc = {
        "sources": [
            {"source_id": "s1", "platform": "baike", "url": "https://x.invalid/g", "body": "正文兜底"},
            {"source_id": "s2", "platform": "mafengwo", "url": "https://x.invalid/h", "body": "游记兜底"},
            {"source_id": "s3", "platform": "官网", "url": "https://x.invalid/i", "body": "官方兜底"},
        ],
        "imageUrls": [
            {
                "url": "https://img.invalid/a.jpg",
                "platform": "景区官网",
                "license": "CC-BY-SA 4.0",
                "credit": "Ann",
                "sourceUrl": "https://img.invalid/a.jpg",
                "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                "usageScope": "app_publish",
                "caption": "稻城亚丁仙乃日雪山主峰",
                "relevance": "支撑仙乃日核心徒步段落的雪山实景",
            },
            {
                "url": "https://img.invalid/b.jpg",
                "platform": "景区官网",
                "license": "CC-BY-SA 4.0",
                "credit": "Bob",
                "sourceUrl": "https://img.invalid/b.jpg",
                "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                "usageScope": "app_publish",
                "caption": "牛奶海与五色海高山湖泊",
                "relevance": "对应高山湖泊体验段落的实景细节",
            },
        ],
    }
    # 对象优先：source_plan 落实体对象 1.download/source_plan.json（prepare 见已存在则不覆盖）。
    obj_plan = resolve_entity_object_dir(_TASK, batch, _EID, etype_hint="景区") / "1.download" / "source_plan.json"
    write_json(obj_plan, doc)

    _by_url = {"https://img.invalid/a.jpg": img_a, "https://img.invalid/b.jpg": img_b}

    def _fake_payload(url, *, min_bytes=3000):
        body = _by_url.get(url, img_a)
        import hashlib as _h

        return {
            "url": url,
            "ext": ".jpg",
            "bytes": body,
            "contentType": "image/jpeg",
            "sha256": _h.sha256(body).hexdigest(),
        }

    def _fake_source_fetch(url: str):
        return {
            "url": url,
            "statusCode": 200,
            "htmlBytes": b"<html></html>",
            "text": (
                f"{_EID} 景区当天开放时间会随天气变化，门票和观光车最好提前确认。"
                f"上午进山更适合先走主景段，再看体力决定是否加长徒步，午后排队和返程压力都会更大。"
                f"雨后栈道湿滑、风口偏冷，补给点和返程时间都要在出发前预留。"
            ),
            "sha256": "sha-source",
        }

    orig = handler_mod.fetch_image_payload
    orig_source = handler_mod.fetch_source_payload
    try:
        handler_mod.fetch_image_payload = _fake_payload
        handler_mod.fetch_source_payload = _fake_source_fetch
        handle_download(argparse.Namespace(task=_TASK, batch=batch, entity_ids=_EID, entity_type="景区"))
    finally:
        handler_mod.fetch_image_payload = orig
        handler_mod.fetch_source_payload = orig_source

    obj = resolve_entity_object_dir(_TASK, batch, _EID, etype_hint="景区")
    units = iter_source_units(obj)
    assert units, f"no source unit under {obj}"
    assert [unit.name for unit in units] == ["01.s1", "02.s2", "03.s3"], units
    unit = units[0]
    index_file = unit / "assets" / "index.json"
    assert index_file.is_file(), f"missing {index_file}"
    data = read_json(index_file)
    assert len(data["assets"]) == 2, data
    first = data["assets"][0]
    assert (unit / "assets" / first["fileName"]).is_file()
    # 新增持久化字段：尺寸 + contentType + 完整版权 + 相关性 + 多变体。
    assert first["width"] >= 640 and first["height"] >= 426, first
    assert first["contentType"] == "image/jpeg", first
    assert first["relevance"], first
    assert first["variants"], "应有物理多变体(webp)"
    variant_profiles = {v["profile"] for v in first["variants"]}
    assert {"thumbnail", "display"}.issubset(variant_profiles), variant_profiles
    for v in first["variants"]:
        assert (unit / "assets" / v["fileName"]).is_file(), v
    assert data["assets"][1]["license"] == "CC-BY-SA 4.0"
    assert data["assets"][1]["credit"] == "Bob"
    # 不再有对象级散落 images/
    assert not (obj / "images").exists()


def test_handle_download_blocks_unsafe_images_before_persist():
    from _common.source_unit import iter_source_units, resolve_entity_object_dir

    batch = "b_img_handler_unsafe"
    ensure_batch_layout(_TASK, batch, "download")
    doc = {
        "sources": [
            {"source_id": "s1", "platform": "baike", "url": "https://x.invalid/g", "body": "正文兜底"},
            {"source_id": "s2", "platform": "官网", "url": "https://x.invalid/h", "body": "官方兜底"},
        ],
        "imageUrls": [
            {
                "url": "https://img.invalid/a.jpg",
                "platform": "景区官网",
                "license": "scenic_official_authorized",
                "credit": "景区官方",
                "sourceUrl": "https://img.invalid/a.jpg",
                "termsUrl": "https://img.invalid/terms",
                "usageScope": "app_publish",
                "caption": "稻城亚丁主峰",
                "relevance": "支撑稻城亚丁主峰段落",
            },
            {
                "url": "https://img.invalid/b.jpg",
                "platform": "景区官网",
                "license": "scenic_official_authorized",
                "credit": "景区官方",
                "sourceUrl": "https://img.invalid/b.jpg",
                "termsUrl": "https://img.invalid/terms",
                "usageScope": "app_publish",
                "caption": "牛奶海",
                "relevance": "支撑牛奶海段落",
            },
        ],
    }
    obj_plan = resolve_entity_object_dir(_TASK, batch, _EID, etype_hint="景区") / "1.download" / "source_plan.json"
    write_json(obj_plan, doc)

    img_a = _real_jpeg(21)
    img_b = _real_jpeg(22)

    def _fake_payload(url, *, min_bytes=3000):
        body = img_a if url.endswith("a.jpg") else img_b
        import hashlib as _h

        return {
            "url": url,
            "ext": ".jpg",
            "bytes": body,
            "contentType": "image/jpeg",
            "sha256": _h.sha256(body).hexdigest(),
        }

    class _Verdict:
        def __init__(self, status: str):
            self.status = status
            self.reasons = ("watermark_or_platform_text",)

        @property
        def blocks_image_publish(self):
            return True

    def _fake_source_fetch(url: str):
        return {
            "url": url,
            "statusCode": 200,
            "htmlBytes": b"<html></html>",
            "text": (
                f"{_EID} 景区当天开放时间会随天气变化，门票和观光车最好提前确认。"
                f"上午进山更适合先走主景段，再看体力决定是否加长徒步，午后排队和返程压力都会更大。"
                f"雨后栈道湿滑、风口偏冷，补给点和返程时间都要在出发前预留。"
            ),
            "sha256": "sha-source",
        }

    orig_fetch = handler_mod.fetch_image_payload
    orig_assess = handler_mod.assess_image
    orig_source = handler_mod.fetch_source_payload
    try:
        handler_mod.fetch_image_payload = _fake_payload
        handler_mod.assess_image = lambda path: _Verdict("unsafe")
        handler_mod.fetch_source_payload = _fake_source_fetch
        try:
            handle_download(argparse.Namespace(task=_TASK, batch=batch, entity_ids=_EID, entity_type="景区"))
        except SystemExit as exc:
            assert exc.code == 1
        else:
            raise AssertionError("expected download gate to fail for unsafe images")
    finally:
        handler_mod.fetch_image_payload = orig_fetch
        handler_mod.assess_image = orig_assess
        handler_mod.fetch_source_payload = orig_source

    obj = resolve_entity_object_dir(_TASK, batch, _EID, etype_hint="景区")
    units = iter_source_units(obj)
    assert units, f"no source unit under {obj}"
    assets_dir = units[0] / "assets"
    assert not assets_dir.exists(), f"unsafe images should not persist into assets: {assets_dir}"


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"download images tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
