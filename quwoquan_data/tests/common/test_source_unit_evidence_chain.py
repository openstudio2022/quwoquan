"""来源单元 → 文章资产 证据链契约 (T2)。

证明 docs/pipeline_directory_layout_spec.md §3/§4：
- download 写来源单元（编号 + assets/ + index + manifest），无对象级散 images/。
- produce 选图消费来源单元，asset 携带相对 sourceAssetRef/sourceRef。
- materialize 成品 assets 文件名 = assetId，可由 article.md 的 asset:// 直查；
  manifest.assets[].sourceAssetRef 相对、可回查到来源单元原图；citedSourceRefs 相对。

可直接运行：python3 quwoquan_data/tests/common/test_source_unit_evidence_chain.py
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

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(SCRIPTS_ROOT))

os.environ["QWQ_RUNTIME_ROOT"] = tempfile.mkdtemp()

import numpy as np  # noqa: E402
import cv2  # noqa: E402

from _common.article_package import copy_asset_files  # noqa: E402
from _common.batch_manifest import write_batch_manifest  # noqa: E402
from _common.io import read_json, write_json  # noqa: E402
from _common.paths import (  # noqa: E402
    batch_entity_object_dir,
    batch_root,
    batch_source_unit_dir,
    ensure_batch_layout,
    ensure_task_layout,
    task_shared_dir,
)
from _common.source_unit import iter_source_units, object_image_candidates, write_source_unit  # noqa: E402
from produce.route_workflow import _build_route_assets  # noqa: E402
from verify.verify_directory_evidence_chain import scan_task  # noqa: E402

TASK = "旅行/地域/四川省/景区/景区全覆盖"
BATCH = "evidence_chain"
ENTITIES = ["海螺沟", "稻城亚丁"]


def _img(seed: int) -> bytes:
    canvas = np.zeros((240, 320, 3), np.uint8)
    rng = np.random.default_rng(seed)
    canvas[:] = rng.integers(0, 255, size=3, dtype=np.uint8)
    cv2.rectangle(canvas, (20 + seed * 9, 20), (140 + seed * 9, 130), (int(seed * 41) % 255, 40, 210), -1)
    cv2.circle(canvas, (230, 170), 35 + seed * 6, (10, int(seed * 57) % 255, 90), -1)
    ok, buf = cv2.imencode(".jpg", canvas)
    assert ok
    return buf.tobytes()


def _seed_source_units() -> None:
    ensure_task_layout(TASK)
    ensure_batch_layout(TASK, BATCH, "download")
    write_batch_manifest(TASK, BATCH, command="download")
    for ei, name in enumerate(ENTITIES):
        obj = batch_entity_object_dir(TASK, BATCH, "地点", "景区", name)
        write_source_unit(
            obj,
            ordinal=1,
            source_id="overview_baike",
            source_md=f"# {name}\n\n{name} 的百科概述，含交通/季节/海拔等基础事实。",
            clean_md=f"{name} 概述",
            quality={"sourceId": "overview_baike", "quality": "Good", "score": 4},
            platform="baike",
            source_category="overview_baike",
            url=f"https://zh.wikipedia.org/wiki/{name}",
            title=f"{name}（百科）",
            target_ref=f"/entity/地点/景区/{name}",
            relevance=f"覆盖 {name} 基础事实",
            images=[
                {"bytes": _img(ei * 10 + 1), "url": f"https://img/{name}/a.jpg", "license": "CC", "credit": "WM", "caption": f"{name}实景", "relevance": f"{name}核心体验"},
                {"bytes": _img(ei * 10 + 2), "url": f"https://img/{name}/b.jpg", "license": "CC", "credit": "WM", "caption": f"{name}远景", "relevance": f"{name}节点"},
            ],
            task_id=TASK,
            batch_id=BATCH,
        )


def test_source_unit_layout_no_loose_images():
    _seed_source_units()
    obj = batch_entity_object_dir(TASK, BATCH, "地点", "景区", "海螺沟")
    units = iter_source_units(obj)
    assert len(units) == 1, units
    unit = units[0]
    assert unit.resolve().relative_to(batch_root(TASK, BATCH).resolve()).as_posix().startswith("sources/su_"), unit
    assert (unit / "meta.json").is_file()
    assert (unit / "assets" / "index.json").is_file()
    assert (unit / "assets").is_dir()
    assert (obj / "1.download" / "source_refs.json").is_file()
    # 对象级别不得出现散落 images/
    assert not (obj / "images").exists()
    assert not (obj / "1.download" / "images").exists()
    assert not (obj / "1.download" / "sources").exists()


def test_object_image_candidates_carry_relative_refs():
    _seed_source_units()
    obj = batch_entity_object_dir(TASK, BATCH, "地点", "景区", "海螺沟")
    cands = object_image_candidates(obj, TASK, BATCH)
    assert len(cands) == 2, cands
    for c in cands:
        assert c["sourceRef"].startswith("sources/su_"), c
        assert c["sourceAssetRef"].startswith("sources/su_"), c
        assert not c["sourceAssetRef"].startswith("/")
        assert "/Users/" not in c["sourceAssetRef"]


def test_route_assets_to_post_assets_traceable():
    _seed_source_units()
    # RC4：文章 1:1 同源——证据链取自单一底稿来源（baseSourceRef）的 assets，不跨实体借图。
    obj = batch_entity_object_dir(TASK, BATCH, "地点", "景区", "海螺沟")
    cands = object_image_candidates(obj, TASK, BATCH)
    assert cands, "seeded base source should expose image candidates"
    brief = {
        "carrier": "article",
        "baseSourceRef": cands[0]["sourceRef"],
        "imagePlan": [{"slot": "封面", "imageLayout": "fullWidth"}, {"slot": "节点", "gallery": "masonry"}],
    }
    evidence_bundle = {"routeNodes": [{"entityName": "海螺沟", "entityRef": "地点/景区/海螺沟"}]}
    assets = _build_route_assets(TASK, BATCH, "海螺沟环线", brief, evidence_bundle)
    assert assets, assets
    # 成品资产文件名 = assetId.ext，asset:// 可直查文件
    for a in assets:
        assert a["fileName"] == f"{a['assetId']}{Path(a['fileName']).suffix}", a
        assert a["entityName"] in a["assetId"], a
        assert not a["assetId"].startswith("data_asset_"), a
        assert a["sourceAssetRef"].startswith("sources/su_"), a
        assert not a["sourceAssetRef"].startswith("/"), a
    # copy 到 post assets/，文件名即 assetId
    post_assets = batch_root(TASK, BATCH) / "posts" / "article" / "环线" / "海螺沟环线" / "1" / "assets"
    copied = copy_asset_files(assets, post_assets)
    for a in copied:
        f = post_assets / a["fileName"]
        assert f.is_file(), f
        assert a["assetId"] in f.name, f
        # sourceAssetRef 回查源图存在
        src = batch_root(TASK, BATCH) / a["sourceAssetRef"]
        assert src.is_file(), src


def test_inline_image_placeholders_bind_to_source_asset_ids():
    """RC3：内联图占位就地绑定真实 sourceAssetId；失败图占位整块剥离、图文交错保留。"""
    ensure_task_layout(TASK)
    ensure_batch_layout(TASK, BATCH, "download")
    write_batch_manifest(TASK, BATCH, command="download")
    obj = batch_entity_object_dir(TASK, BATCH, "地点", "景区", "九寨沟")
    source_md = (
        "---\nurl: https://travel.qunar.com/youji/7870084\n---\n\n"
        "# 九寨沟游记\n\n出发前的第一段铺垫正文。\n\n"
        ":::figure\n![五花海](asset://source-inline-001)\n五花海\n:::\n\n"
        "沿栈道走的第二段正文。\n\n"
        ":::figure\n![珍珠滩瀑布](asset://source-inline-002)\n珍珠滩瀑布\n:::\n\n"
        "继续前行的第三段正文。\n\n"
        ":::figure\n![未下载成功的图](asset://source-inline-003)\n未下载成功的图\n:::\n\n"
        "回望全程的结尾段正文。\n"
    )
    manifest = write_source_unit(
        obj,
        ordinal=1,
        source_id="article_qunar_base",
        source_md=source_md,
        clean_md=source_md,
        quality={"sourceId": "article_qunar_base", "quality": "Good", "score": 4},
        platform="qunar",
        source_category="travelogue",
        research_lane="article",
        url="https://travel.qunar.com/youji/7870084",
        title="九寨沟游记",
        target_ref="/entity/地点/景区/九寨沟",
        relevance="九寨沟图文混排游记底稿",
        images=[
            {
                "bytes": _img(31),
                "url": "https://travel.qunar.com/photo/lake.jpg",
                "license": "qunar-ugc",
                "credit": "qunar",
                "caption": "五花海",
                "placeholderId": "source-inline-001",
            },
            {
                "bytes": _img(32),
                "url": "https://travel.qunar.com/photo/falls.jpg",
                "license": "qunar-ugc",
                "credit": "qunar",
                "caption": "珍珠滩瀑布",
                "placeholderId": "source-inline-002",
            },
        ],
        task_id=TASK,
        batch_id=BATCH,
        build_variants=False,
    )
    unit = batch_source_unit_dir(TASK, BATCH, str(manifest["sourceUnitId"]))
    bound = (unit / "source.md").read_text(encoding="utf-8")

    # 成功下载的内联图：占位绑定到真实 sourceAssetId（001_001 / 001_002）。
    assert "asset://source-inline-001" not in bound
    assert "asset://source-inline-002" not in bound
    assert "asset://001_001" in bound
    assert "asset://001_002" in bound
    # 失败图占位整块剥离，不留悬空 source-inline-003。
    assert "source-inline-003" not in bound
    assert "未下载成功的图" not in bound
    # 图文交错保留：正文段落与绑定后的 figure 仍按原序穿插。
    assert (
        bound.index("第一段铺垫正文")
        < bound.index("asset://001_001")
        < bound.index("第二段正文")
        < bound.index("asset://001_002")
        < bound.index("第三段正文")
        < bound.index("结尾段正文")
    )
    # 资产索引记录 inlinePlaceholderId，可回查内联同源出处。
    index_payload = read_json(unit / "assets" / "index.json")
    placeholders = sorted(
        str(a.get("inlinePlaceholderId") or "") for a in index_payload["assets"]
    )
    assert placeholders == ["source-inline-001", "source-inline-002"]


def test_task_shared_allows_baseline_report():
    ensure_task_layout(TASK)
    shared = task_shared_dir(TASK)
    shared.mkdir(parents=True, exist_ok=True)
    write_json(shared / "baseline_report.json", {"status": "passed"})
    issues = scan_task(TASK)
    assert not any("baseline_report.json" in issue for issue in issues), issues


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"source unit evidence chain tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
