"""来源单元 → 文章资产 证据链契约 (T2)。

证明 docs/pipeline_directory_layout_spec.md §3/§4：
- download 写来源单元（编号 + assets/ + index + manifest），无对象级散 images/。
- produce 选图消费来源单元，asset 携带相对 sourceAssetRef/sourceRef。
- materialize 成品 assets 文件名 = assetId，可由 article.md 的 asset:// 直查；
  manifest.assets[].sourceAssetRef 相对、可回查到来源单元原图；citedSourceRefs 相对。

可直接运行：python3 quwoquan_data/tests/local_contract/core/test_source_unit_evidence_chain__behavior__functional__local_contract_test.py
"""
from __future__ import annotations

import re
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


import numpy as np  # noqa: E402
import cv2  # noqa: E402

from core.article_package import copy_asset_files  # noqa: E402
from content.execution.runtime_state import write_execution_runtime_state  # noqa: E402
from core.io import read_json, write_json  # noqa: E402
from core.paths import (  # noqa: E402
    execution_entity_object_dir,
    execution_root,
    execution_source_unit_dir,
    ensure_execution_command_layout,
    ensure_execution_layout,
    execution_shared_dir,
)
from core.qunar_template import source_author_ref  # noqa: E402
from content.source.source_assets import object_image_candidates  # noqa: E402
from content.source.source_unit import iter_source_units, write_source_unit  # noqa: E402
from content.post.route_assets import _build_route_assets  # noqa: E402
from verify.verify_directory_evidence_chain import scan_execution  # noqa: E402
from support.execution_manifest_fixture import build_execution_fixture  # noqa: E402

TASK = "20260711--travel-article-evidence--cn-sichuan--canary-001"
BATCH = TASK
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
    build_execution_fixture(TASK)
    ensure_execution_layout(TASK)
    ensure_execution_command_layout(TASK, "source")
    write_execution_runtime_state(TASK, command="source")
    for ei, name in enumerate(ENTITIES):
        obj = execution_entity_object_dir(TASK, "地点", "景区", name)
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
            execution_id=TASK,
        )


def test_source_unit_layout_no_loose_images():
    _seed_source_units()
    obj = execution_entity_object_dir(TASK, "地点", "景区", "海螺沟")
    units = iter_source_units(obj)
    assert len(units) == 1, units
    unit = units[0]
    assert re.match(r"^sources/海螺沟__[A-Za-z0-9_\-]+__[0-9a-f]{8}$", unit.resolve().relative_to(execution_root(TASK).resolve()).as_posix()), unit
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
    obj = execution_entity_object_dir(TASK, "地点", "景区", "海螺沟")
    cands = object_image_candidates(obj, TASK)
    assert len(cands) == 2, cands
    for c in cands:
        assert re.match(r"^sources/海螺沟__[A-Za-z0-9_\-]+__[0-9a-f]{8}/", c["sourceRef"]), c
        assert re.match(r"^sources/海螺沟__[A-Za-z0-9_\-]+__[0-9a-f]{8}/", c["sourceAssetRef"]), c
        assert not c["sourceAssetRef"].startswith("/")
        assert "/Users/" not in c["sourceAssetRef"]


def test_route_assets_to_post_assets_traceable():
    _seed_source_units()
    # RC4：文章 1:1 同源——证据链取自单一底稿来源（baseSourceRef）的 assets，不跨实体借图。
    obj = execution_entity_object_dir(TASK, "地点", "景区", "海螺沟")
    cands = object_image_candidates(obj, TASK)
    assert cands, "seeded base source should expose image candidates"
    brief = {
        "carrier": "article",
        "baseSourceRef": cands[0]["sourceRef"],
        "imagePlan": [{"slot": "封面", "imageLayout": "fullWidth"}, {"slot": "节点", "gallery": "masonry"}],
    }
    evidence_bundle = {"routeNodes": [{"entityName": "海螺沟", "entityRef": "地点/景区/海螺沟"}]}
    assets = _build_route_assets(TASK, "海螺沟环线", brief, evidence_bundle)
    assert assets, assets
    # 成品资产文件名 = assetId.ext，asset:// 可直查文件
    for a in assets:
        assert a["fileName"] == f"{a['assetId']}{Path(a['fileName']).suffix}", a
        assert a["entityName"] in a["assetId"], a
        assert not a["assetId"].startswith("data_asset_"), a
        assert re.match(r"^sources/海螺沟__[A-Za-z0-9_\-]+__[0-9a-f]{8}/", a["sourceAssetRef"]), a
        assert not a["sourceAssetRef"].startswith("/"), a
    # copy 到 post assets/，文件名即 assetId
    post_assets = execution_root(TASK) / "posts" / "article" / "环线" / "海螺沟环线" / "1" / "assets"
    copied = copy_asset_files(assets, post_assets)
    for a in copied:
        f = post_assets / a["fileName"]
        assert f.is_file(), f
        assert a["assetId"] in f.name, f
        # sourceAssetRef 回查源图存在
        src = execution_root(TASK) / a["sourceAssetRef"]
        assert src.is_file(), src


def test_inline_image_placeholders_bind_to_source_asset_ids():
    """RC3：内联图占位就地绑定真实 sourceAssetId；失败图占位整块剥离、图文交错保留。"""
    ensure_execution_layout(TASK)
    ensure_execution_command_layout(TASK, "source")
    write_execution_runtime_state(TASK, command="source")
    obj = execution_entity_object_dir(TASK, "地点", "景区", "九寨沟")
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
        execution_id=TASK,
        build_variants=False,
    )
    unit = execution_source_unit_dir(TASK, str(manifest["sourceUnitId"]))
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


def test_qunar_source_unit_records_author_identity_from_source_row():
    ensure_execution_layout(TASK)
    ensure_execution_command_layout(TASK, "source")
    write_execution_runtime_state(TASK, command="source")
    obj = execution_entity_object_dir(TASK, "地点", "景区", "剑门关")
    manifest = write_source_unit(
        obj,
        ordinal=1,
        source_id="article_qunar_author_base",
        source_md=(
            "---\nurl: https://touch.travel.qunar.com/youji/7869929\n---\n\n"
            "2025/09/29出发\n剑门关栈道、交通、门票和观光车信息都写清楚。"
        ),
        quality={"sourceId": "article_qunar_author_base", "quality": "Good", "score": 4},
        platform="qunar",
        source_category="travelogue",
        research_lane="article",
        url="https://touch.travel.qunar.com/youji/7869929",
        title="剑门关一日游",
        target_ref="/entity/地点/景区/剑门关",
        relevance="剑门关图文游记底稿",
        source={
            "userName": "灵光旅行",
            "userId": "3367372@qunar",
            "userBooksUrl": "https://touch.travel.qunar.com/3367372@qunar/books",
        },
        execution_id=TASK,
        build_variants=False,
    )

    assert manifest["sourceAuthorRef"] == source_author_ref("3367372@qunar")
    assert manifest["siteTemplate"]["authorName"] == "灵光旅行"
    assert manifest["siteTemplate"]["authorId"] == "3367372@qunar"
    assert manifest["siteTemplate"]["authorBooksUrl"] == "https://touch.travel.qunar.com/3367372@qunar/books"
    unit = execution_source_unit_dir(TASK, str(manifest["sourceUnitId"]))
    persisted = read_json(unit / "meta.json")
    assert persisted["sourceAuthorRef"] == manifest["sourceAuthorRef"]


def test_execution_shared_rejects_unregistered_baseline_report():
    ensure_execution_layout(TASK)
    shared = execution_shared_dir(TASK)
    shared.mkdir(parents=True, exist_ok=True)
    write_json(shared / "baseline_report.json", {"status": "passed"})
    issues = scan_execution(TASK)
    assert any("baseline_report.json" in issue and "未登记" in issue for issue in issues), issues


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"source unit evidence chain tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
