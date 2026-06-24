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
from _common.paths import STAGE_DOWNLOAD, batch_root, ensure_batch_layout  # noqa: E402
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


def _write_lane_plans(batch: str, sources: list[dict], images: list[dict]) -> None:
    obj = resolve_entity_object_dir(_TASK, batch, _EID, etype_hint="景区") / STAGE_DOWNLOAD
    obj.mkdir(parents=True, exist_ok=True)
    write_json(
        obj / "article_source_plan.json",
        {
            "payload": {
                "sources": [
                    {
                        **source,
                        "sourceUseMode": source.get("sourceUseMode") or "factual_reference_only",
                    }
                    for source in sources
                ]
            }
        },
    )
    write_json(
        obj / "image_source_plan.json",
        {
            "payload": {
                "collections": [
                    {
                        "sourceCollectionId": image.get("sourceCollectionId") or f"fixture:{index}",
                        "creator": image.get("credit") or image.get("creator") or f"Fixture {index}",
                        "credit": image.get("credit") or image.get("creator") or f"Fixture {index}",
                        "collectionPageUrl": image.get("collectionPageUrl") or image.get("sourceUrl") or image["url"],
                        "platform": image.get("platform") or "Wikimedia Commons",
                        "license": image.get("license") or "CC-BY-SA 4.0",
                        "termsUrl": image.get("termsUrl") or "https://creativecommons.org/licenses/by-sa/4.0/",
                        "licenseSnapshot": image.get("licenseSnapshot") or "test fixture",
                        "authorizationProof": image.get("authorizationProof") or "test fixture authorization",
                        "usageScope": image.get("usageScope") or "app_publish",
                        "images": [image],
                    }
                    for index, image in enumerate(images, start=1)
                ]
            }
        },
    )


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


def test_fetch_image_payload_respects_max_bytes():
    orig = fetch_mod._http_get_bytes
    seen: list[int] = []
    try:
        def _fake_get(url, **kw):
            seen.append(int(kw.get("max_bytes") or 0))
            return (200, _real_jpeg(44), "image/jpeg")

        fetch_mod._http_get_bytes = _fake_get
        assert fetch_mod.fetch_image_payload("https://img.example/large.jpg", max_bytes=128) is None
    finally:
        fetch_mod._http_get_bytes = orig
    assert seen == [128]


def test_fetch_image_payload_tries_same_source_high_res_candidates():
    compressed = "https://img1.qunarzz.com/travel/d1/1509/f3/foo.jpg_r_720x480x95_abcd1234.jpg"
    original = "https://img1.qunarzz.com/travel/d1/1509/f3/foo.jpg"
    assert original in fetch_mod.candidate_image_urls(compressed)

    calls: list[str] = []
    orig = fetch_mod._http_get_bytes
    try:
        def _fake_get(url, **_kw):
            calls.append(url)
            if url == compressed:
                return (404, b"", "text/html")
            if url == original:
                return (200, _real_jpeg(25), "image/jpeg")
            return (404, b"", "text/html")

        fetch_mod._http_get_bytes = _fake_get
        payload = fetch_mod.fetch_image_payload(compressed)
    finally:
        fetch_mod._http_get_bytes = orig
    assert payload is not None
    assert payload["url"] == original
    assert payload["requestedUrl"] == compressed
    assert payload["normalizedFromUrl"] == compressed
    assert calls[:2] == [compressed, original]


def test_candidate_image_urls_restores_wikimedia_thumb_original():
    thumb = (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/"
        "Example_photo.jpg/640px-Example_photo.jpg"
    )
    original = "https://upload.wikimedia.org/wikipedia/commons/a/ab/Example_photo.jpg"
    assert original in fetch_mod.candidate_image_urls(thumb)


def test_fetch_image_payload_reads_only_data_root_file_urls():
    local = fetch_mod.DATA_ROOT / "generated" / "asset.jpg"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(_real_jpeg(23))
    payload = fetch_mod.fetch_image_payload(local.resolve().as_uri())
    assert payload is not None
    assert payload["contentType"] == "image/jpeg"
    outside = Path(tempfile.mkdtemp(prefix="outside_data_root_")) / "asset.jpg"
    outside.write_bytes(_real_jpeg(24))
    assert fetch_mod.fetch_image_payload(outside.resolve().as_uri()) is None


def test_image_check_temp_file_is_ephemeral():
    batch = "b_img_temp_cleanup"
    ensure_batch_layout(_TASK, batch, "download")
    body = _real_jpeg(31)
    temp_path = handler_mod._write_image_check_temp_file(
        _TASK,
        batch,
        subdir="tmp_image_checks",
        payload={"bytes": body, "ext": ".jpg"},
    )
    assert temp_path.is_file()
    assert temp_path.read_bytes() == body
    handler_mod._cleanup_image_check_temp_file(temp_path)
    assert not temp_path.exists()


def test_repeated_fetch_preserves_better_same_url_source_unit():
    from _common.paths import source_unit_dir

    object_dir = resolve_entity_object_dir(
        _TASK, "b_source_cache", _EID, etype_hint="景区"
    )
    unit = source_unit_dir(object_dir, 1, "stable_source")
    unit.mkdir(parents=True, exist_ok=True)
    write_json(unit / "meta.json", {"url": "https://example.test/source"})
    write_json(
        unit / "source.quality.json",
        {
            "quality": "B-fact",
            "score": 82,
            "statusCode": 200,
        },
    )
    (unit / "source.md").write_text("previous retained source", encoding="utf-8")

    cached = handler_mod._cached_source_quality_if_better(
        object_dir,
        ordinal=1,
        source_id="stable_source",
        url="https://example.test/source",
        candidate_quality={"quality": "Reject", "score": 5},
    )
    assert cached and cached["quality"] == "B-fact"

    assert handler_mod._cached_source_quality_if_better(
        object_dir,
        ordinal=1,
        source_id="stable_source",
        url="https://example.test/replacement",
        candidate_quality={"quality": "Reject", "score": 5},
    ) is None


def test_prune_stale_source_units_removes_dirs_absent_from_current_plan():
    from _common.paths import source_unit_dir

    object_dir = resolve_entity_object_dir(
        _TASK, "b_prune_stale_source_units", _EID, etype_hint="景区"
    )
    keep = source_unit_dir(object_dir, 1, "current_source")
    stale = source_unit_dir(object_dir, 2, "old_image_collection")
    keep.mkdir(parents=True, exist_ok=True)
    stale.mkdir(parents=True, exist_ok=True)
    (keep / "source.md").write_text("current", encoding="utf-8")
    (stale / "source.md").write_text("stale", encoding="utf-8")

    pruned = handler_mod._prune_stale_source_units(object_dir, {keep})

    assert pruned == ["02.old_image_collection"]
    assert keep.is_dir()
    assert not stale.exists()


def test_prune_stale_rejected_units_preserves_homepage_baike_memory():
    from _common.paths import source_unit_dir

    object_dir = resolve_entity_object_dir(
        _TASK, "b_prune_stale_rejected_memory", _EID, etype_hint="景区"
    )
    rejected_root = object_dir / STAGE_DOWNLOAD / "rejected_sources"
    baike = source_unit_dir(object_dir, 1, "home_baidu_baike")
    article = source_unit_dir(object_dir, 2, "article_qunar_base")
    baike = rejected_root / baike.name
    article = rejected_root / article.name
    baike.mkdir(parents=True, exist_ok=True)
    article.mkdir(parents=True, exist_ok=True)
    write_json(
        baike / "meta.json",
        {
            "researchLane": "homepage",
            "platform": "百度百科",
            "sourceKind": "encyclopedia",
            "url": "https://baike.baidu.com/item/foo",
        },
    )
    write_json(
        baike / "source.quality.json",
        {"quality": "Reject", "fetchSucceeded": False, "statusCode": 0},
    )
    write_json(
        article / "meta.json",
        {"researchLane": "article", "platform": "去哪儿攻略", "url": "https://touch.travel.qunar.com/foo"},
    )
    write_json(
        article / "source.quality.json",
        {"quality": "Reject", "fetchSucceeded": False, "statusCode": 0},
    )

    pruned = handler_mod._prune_stale_rejected_source_units(
        object_dir,
        set(),
        selected_lanes={"homepage", "article"},
    )

    assert pruned == ["02.article_qunar_base"]
    assert baike.is_dir()
    assert not article.exists()


def test_handle_download_fetches_images_into_source_unit():
    """新布局：图片落到首个来源单元 assets/，写 assets/index.json，无对象级散 images/。"""
    from _common.source_unit import iter_source_units, resolve_entity_object_dir

    batch = "b_img_handler"
    ensure_batch_layout(_TASK, batch, "download")
    # 两张视觉不同、达到像素门、带真实相关性的图（满足 min count≥2 + relevance + pixels）。
    img_a = _real_jpeg(11)
    img_b = _real_jpeg(97)
    images = [
        {
            "url": "https://img.invalid/a.jpg",
            "platform": "景区官网",
            "license": "CC-BY-SA 4.0",
            "credit": "Ann",
            "sourceUrl": "https://img.invalid/a.jpg",
            "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
            "usageScope": "app_publish",
            "caption": "稻城亚丁仙乃日雪山主峰",
            "relevance": "直接呈现稻城亚丁仙乃日核心徒步段落的雪山实景",
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
            "relevance": "直接呈现稻城亚丁牛奶海与五色海高山湖泊体验段落的实景细节",
        },
    ]
    _write_lane_plans(
        batch,
        [
            {"source_id": "s1", "platform": "baike", "url": "https://x.invalid/g", "body": "正文兜底"},
            {"source_id": "s2", "platform": "mafengwo", "url": "https://x.invalid/h", "body": "游记兜底"},
            {"source_id": "s3", "platform": "官网", "url": "https://x.invalid/i", "body": "官方兜底"},
        ],
        images,
    )

    _by_url = {"https://img.invalid/a.jpg": img_a, "https://img.invalid/b.jpg": img_b}

    def _fake_payload(url, *, min_bytes=3000, max_bytes=0):
        body = _by_url.get(url, img_a)
        import hashlib as _h

        return {
            "url": url,
            "ext": ".jpg",
            "bytes": body,
            "contentType": "image/jpeg",
            "sha256": _h.sha256(body).hexdigest(),
        }

    def _fake_source_fetch(url: str, **_kwargs):
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
    names = [unit.name for unit in units]
    assert names[:3] == ["01.s1", "02.s2", "03.s3"], names
    asset_units = [unit for unit in units if (unit / "assets" / "index.json").is_file()]
    assert len(asset_units) == 2, asset_units
    all_assets = []
    for unit in asset_units:
        data = read_json(unit / "assets" / "index.json")
        for asset in data["assets"]:
            all_assets.append((unit, asset))
    assert len(all_assets) == 2, all_assets
    unit, first = all_assets[0]
    assert (unit / "assets" / first["fileName"]).is_file()
    # download 主链路只闭合原图、尺寸、版权、hash 与相关性；WebP 变体延后到 media/release 阶段。
    assert first["width"] >= 640 and first["height"] >= 426, first
    assert first["contentType"] == "image/jpeg", first
    assert first["relevance"], first
    assert first["variantGeneration"] == "deferred", first
    assert first["variants"] == [], "download 阶段不得物理生成 WebP 变体"
    assert all_assets[1][1]["license"] == "CC-BY-SA 4.0"
    assert all_assets[1][1]["credit"] == "Bob"
    # 不再有对象级散落 images/
    assert not (obj / "images").exists()
    events_path = batch_root(_TASK, batch) / "_shared" / "download_events.jsonl"
    assert events_path.is_file(), "并发下载必须写 append-only events，不能只覆盖 progress snapshot"
    assert "source fetch done" in events_path.read_text(encoding="utf-8")


def test_repeated_image_lane_fetch_reuses_cached_assets_when_network_fails():
    """同一批次重复修复时，已审计图片字节应先走本地 source-unit 缓存。"""
    from _common.source_unit import iter_source_units, resolve_entity_object_dir

    batch = "b_img_lane_cache_reuse"
    ensure_batch_layout(_TASK, batch, "download")
    img_a = _real_jpeg(41)
    img_b = _real_jpeg(42)
    sources = [
        {"source_id": "s1", "platform": "baike", "url": "https://x.invalid/g", "body": "正文兜底"},
        {"source_id": "s2", "platform": "mafengwo", "url": "https://x.invalid/h", "body": "游记兜底"},
        {"source_id": "s3", "platform": "官网", "url": "https://x.invalid/i", "body": "官方兜底"},
    ]
    images = [
        {
            "url": "https://img.invalid/cache-a.jpg",
            "platform": "Wikimedia Commons",
            "license": "CC-BY-SA 4.0",
            "credit": "Ann",
            "sourceUrl": "https://img.invalid/cache-a.jpg",
            "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
            "authorizationProof": "https://img.invalid/cache-a.jpg#rights",
            "usageScope": "app_publish",
            "caption": "稻城亚丁仙乃日雪山",
            "relevance": "直接呈现稻城亚丁仙乃日雪山实景",
        },
        {
            "url": "https://img.invalid/cache-b.jpg",
            "platform": "Wikimedia Commons",
            "license": "CC-BY-SA 4.0",
            "credit": "Bob",
            "sourceUrl": "https://img.invalid/cache-b.jpg",
            "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
            "authorizationProof": "https://img.invalid/cache-b.jpg#rights",
            "usageScope": "app_publish",
            "caption": "稻城亚丁牛奶海",
            "relevance": "直接呈现稻城亚丁牛奶海高山湖泊",
        },
    ]
    _write_lane_plans(batch, sources, images)

    _by_url = {"https://img.invalid/cache-a.jpg": img_a, "https://img.invalid/cache-b.jpg": img_b}

    def _fake_payload(url, *, min_bytes=3000, max_bytes=0):
        body = _by_url[url]
        import hashlib as _h

        return {
            "url": url,
            "ext": ".jpg",
            "bytes": body,
            "contentType": "image/jpeg",
            "sha256": _h.sha256(body).hexdigest(),
        }

    def _fake_source_fetch(url: str, **_kwargs):
        return {
            "url": url,
            "statusCode": 200,
            "htmlBytes": b"<html></html>",
            "text": (
                f"{_EID} 景区预约、观光车、徒步动线、天气和返程时间都需要提前确认。"
                f"核心景观集中在雪山、草甸和海子段落，上午进入更利于避开拥堵。"
                f"高海拔区域温差明显，雨具、防晒和补给都要按长线徒步准备。"
            ),
            "sha256": "sha-source",
        }

    orig_fetch = handler_mod.fetch_image_payload
    orig_source = handler_mod.fetch_source_payload
    try:
        handler_mod.fetch_image_payload = _fake_payload
        handler_mod.fetch_source_payload = _fake_source_fetch
        handle_download(argparse.Namespace(task=_TASK, batch=batch, entity_ids=_EID, entity_type="景区"))

        network_calls: list[str] = []

        def _network_down(url, *, min_bytes=3000):
            network_calls.append(url)
            return None

        handler_mod.fetch_image_payload = _network_down
        handle_download(argparse.Namespace(task=_TASK, batch=batch, entity_ids=_EID, entity_type="景区"))
    finally:
        handler_mod.fetch_image_payload = orig_fetch
        handler_mod.fetch_source_payload = orig_source

    assert network_calls == []
    obj = resolve_entity_object_dir(_TASK, batch, _EID, etype_hint="景区")
    asset_units = [unit for unit in iter_source_units(obj) if (unit / "assets" / "index.json").is_file()]
    assert len(asset_units) == 2


def test_failed_image_lane_repair_preserves_previous_image_source_units():
    """新图片源全失败时，失败修复不能剪掉上一轮已存在的图片证据。"""
    from _common.source_unit import iter_source_units, resolve_entity_object_dir

    batch = "b_img_lane_failed_repair_preserves_cache"
    ensure_batch_layout(_TASK, batch, "download")
    img_a = _real_jpeg(51)
    img_b = _real_jpeg(52)
    sources = [
        {"source_id": "s1", "platform": "baike", "url": "https://x.invalid/g", "body": "正文兜底"},
        {"source_id": "s2", "platform": "mafengwo", "url": "https://x.invalid/h", "body": "游记兜底"},
        {"source_id": "s3", "platform": "官网", "url": "https://x.invalid/i", "body": "官方兜底"},
    ]
    old_images = [
        {
            "url": "https://img.invalid/old-a.jpg",
            "platform": "Wikimedia Commons",
            "license": "CC-BY-SA 4.0",
            "credit": "Ann",
            "sourceUrl": "https://img.invalid/old-a.jpg",
            "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
            "authorizationProof": "https://img.invalid/old-a.jpg#rights",
            "usageScope": "app_publish",
            "caption": "稻城亚丁仙乃日雪山",
            "relevance": "直接呈现稻城亚丁仙乃日雪山实景",
        },
        {
            "url": "https://img.invalid/old-b.jpg",
            "platform": "Wikimedia Commons",
            "license": "CC-BY-SA 4.0",
            "credit": "Bob",
            "sourceUrl": "https://img.invalid/old-b.jpg",
            "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
            "authorizationProof": "https://img.invalid/old-b.jpg#rights",
            "usageScope": "app_publish",
            "caption": "稻城亚丁牛奶海",
            "relevance": "直接呈现稻城亚丁牛奶海高山湖泊",
        },
    ]
    _write_lane_plans(batch, sources, old_images)

    def _fake_payload(url, *, min_bytes=3000, max_bytes=0):
        body = img_a if url.endswith("old-a.jpg") else img_b
        import hashlib as _h

        return {
            "url": url,
            "ext": ".jpg",
            "bytes": body,
            "contentType": "image/jpeg",
            "sha256": _h.sha256(body).hexdigest(),
        }

    def _fake_source_fetch(url: str, **_kwargs):
        return {
            "url": url,
            "statusCode": 200,
            "htmlBytes": b"<html></html>",
            "text": (
                f"{_EID} 景区预约、观光车、徒步动线、天气和返程时间都需要提前确认。"
                f"核心景观集中在雪山、草甸和海子段落，上午进入更利于避开拥堵。"
                f"高海拔区域温差明显，雨具、防晒和补给都要按长线徒步准备。"
            ),
            "sha256": "sha-source",
        }

    orig_fetch = handler_mod.fetch_image_payload
    orig_source = handler_mod.fetch_source_payload
    try:
        handler_mod.fetch_image_payload = _fake_payload
        handler_mod.fetch_source_payload = _fake_source_fetch
        handle_download(argparse.Namespace(task=_TASK, batch=batch, entity_ids=_EID, entity_type="景区"))

        obj = resolve_entity_object_dir(_TASK, batch, _EID, etype_hint="景区")
        previous_image_units = {
            unit.name
            for unit in iter_source_units(obj)
            if read_json(unit / "meta.json").get("researchLane") == "image"
        }
        assert previous_image_units

        new_images = [
            {
                **old_images[0],
                "url": "https://img.invalid/new-a.jpg",
                "sourceUrl": "https://img.invalid/new-a.jpg",
                "authorizationProof": "https://img.invalid/new-a.jpg#rights",
            },
            {
                **old_images[1],
                "url": "https://img.invalid/new-b.jpg",
                "sourceUrl": "https://img.invalid/new-b.jpg",
                "authorizationProof": "https://img.invalid/new-b.jpg#rights",
            },
        ]
        _write_lane_plans(batch, sources, new_images)
        handler_mod.fetch_image_payload = lambda url, *, min_bytes=3000, max_bytes=0: None
        try:
            handle_download(argparse.Namespace(task=_TASK, batch=batch, entity_ids=_EID, entity_type="景区"))
        except SystemExit as exc:
            assert exc.code == 1
        else:
            raise AssertionError("expected failed image repair to fail the download gate")
    finally:
        handler_mod.fetch_image_payload = orig_fetch
        handler_mod.fetch_source_payload = orig_source

    obj = resolve_entity_object_dir(_TASK, batch, _EID, etype_hint="景区")
    current_image_units = {
        unit.name
        for unit in iter_source_units(obj)
        if read_json(unit / "meta.json").get("researchLane") == "image"
    }
    assert previous_image_units.issubset(current_image_units)


def test_handle_download_isolates_rejected_sources_when_retained_bundle_is_sufficient():
    from _common.source_unit import iter_source_units, resolve_entity_object_dir

    batch = "b_reject_isolation"
    ensure_batch_layout(_TASK, batch, "download")
    img_a = _real_jpeg(31)
    img_b = _real_jpeg(32)
    _write_lane_plans(
        batch,
        [
            {"source_id": "s1", "platform": "baike", "url": "https://x.invalid/good1", "body": "正文兜底"},
            {"source_id": "s2", "platform": "mafengwo", "url": "https://x.invalid/good2", "body": "游记兜底"},
            {"source_id": "s3", "platform": "官网", "url": "https://x.invalid/good3", "body": "官方兜底"},
            {"source_id": "s_bad", "platform": "sogou", "url": "https://x.invalid/bad", "body": ""},
        ],
        [
            {
                "url": "https://img.invalid/a.jpg",
                "platform": "Wikimedia Commons",
                "license": "CC-BY-SA 4.0",
                "credit": "Ann",
                "sourceUrl": "https://img.invalid/a.jpg",
                "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                "usageScope": "app_publish",
                "caption": "稻城亚丁仙乃日雪山",
                "relevance": "直接呈现稻城亚丁仙乃日雪山实景",
            },
            {
                "url": "https://img.invalid/b.jpg",
                "platform": "Wikimedia Commons",
                "license": "CC-BY-SA 4.0",
                "credit": "Bob",
                "sourceUrl": "https://img.invalid/b.jpg",
                "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                "usageScope": "app_publish",
                "caption": "稻城亚丁牛奶海",
                "relevance": "直接呈现稻城亚丁牛奶海高山湖泊",
            },
        ],
    )

    def _fake_payload(url, *, min_bytes=3000, max_bytes=0):
        body = img_a if url.endswith("a.jpg") else img_b
        import hashlib as _h

        return {
            "url": url,
            "ext": ".jpg",
            "bytes": body,
            "contentType": "image/jpeg",
            "sha256": _h.sha256(body).hexdigest(),
        }

    def _fake_source_fetch(url: str, **_kwargs):
        if url.endswith("/bad"):
            return {
                "url": url,
                "statusCode": 200,
                "htmlBytes": b"<html></html>",
                "text": "验证码",
                "sha256": "sha-bad",
            }
        return {
            "url": url,
            "statusCode": 200,
            "htmlBytes": b"<html></html>",
            "text": (
                f"{_EID} 景区开放时间、门票预约、观光车和徒步路线都需要提前确认。"
                f"上午进入景区适合先看雪山和湖泊，下午留出返程时间。"
                f"高海拔区域风大，补给、雨具和保暖衣物都要提前准备。"
            ),
            "sha256": "sha-good",
        }

    orig_fetch = handler_mod.fetch_image_payload
    orig_source = handler_mod.fetch_source_payload
    try:
        handler_mod.fetch_image_payload = _fake_payload
        handler_mod.fetch_source_payload = _fake_source_fetch
        handle_download(argparse.Namespace(task=_TASK, batch=batch, entity_ids=_EID, entity_type="景区"))
    finally:
        handler_mod.fetch_image_payload = orig_fetch
        handler_mod.fetch_source_payload = orig_source

    obj = resolve_entity_object_dir(_TASK, batch, _EID, etype_hint="景区")
    source_names = [unit.name for unit in iter_source_units(obj)]
    assert "04.s_bad" not in source_names
    rejected = obj / "1.download" / "rejected_sources" / "04.s_bad"
    assert rejected.is_dir()
    assert (rejected / "source.quality.json").is_file()


def test_handle_download_blocks_unsafe_images_before_persist():
    from _common.source_unit import iter_source_units, resolve_entity_object_dir

    batch = "b_img_handler_unsafe"
    ensure_batch_layout(_TASK, batch, "download")
    _write_lane_plans(
        batch,
        [
            {"source_id": "s1", "platform": "baike", "url": "https://x.invalid/g", "body": "正文兜底"},
            {"source_id": "s2", "platform": "官网", "url": "https://x.invalid/h", "body": "官方兜底"},
        ],
        [
            {
                "url": "https://img.invalid/a.jpg",
                "platform": "景区官网",
                "license": "scenic_official_authorized",
                "credit": "景区官方",
                "sourceUrl": "https://img.invalid/a.jpg",
                "termsUrl": "https://img.invalid/terms",
                "usageScope": "app_publish",
                "caption": "稻城亚丁主峰",
                "relevance": "直接呈现稻城亚丁主峰",
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
                "relevance": "直接呈现稻城亚丁牛奶海",
            },
        ],
    )

    img_a = _real_jpeg(21)
    img_b = _real_jpeg(22)

    def _fake_payload(url, *, min_bytes=3000, max_bytes=0):
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

    def _fake_source_fetch(url: str, **_kwargs):
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
