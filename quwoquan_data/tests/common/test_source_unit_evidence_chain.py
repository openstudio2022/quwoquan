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
from _common.io import write_json  # noqa: E402
from _common.paths import (  # noqa: E402
    batch_entity_object_dir,
    batch_root,
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
    assert unit.name == "01.overview_baike", unit
    assert (unit / "meta.json").is_file()
    assert (unit / "assets" / "index.json").is_file()
    assert (unit / "assets").is_dir()
    # 对象级别不得出现散落 images/
    assert not (obj / "images").exists()
    assert not (obj / "1.download" / "images").exists()


def test_object_image_candidates_carry_relative_refs():
    _seed_source_units()
    obj = batch_entity_object_dir(TASK, BATCH, "地点", "景区", "海螺沟")
    cands = object_image_candidates(obj, TASK, BATCH)
    assert len(cands) == 2, cands
    for c in cands:
        assert c["sourceAssetRef"].startswith("entities/地点/景区/海螺沟/1.download/sources/01.overview_baike/assets/"), c
        assert not c["sourceAssetRef"].startswith("/")
        assert "/Users/" not in c["sourceAssetRef"]


def test_route_assets_to_post_assets_traceable():
    _seed_source_units()
    brief = {"imagePlan": [{"slot": "封面", "imageLayout": "fullWidth"}, {"slot": "节点", "gallery": "masonry"}]}
    evidence_bundle = {"routeNodes": [{"entityName": n, "entityRef": f"地点/景区/{n}"} for n in ENTITIES]}
    assets = _build_route_assets(TASK, BATCH, "海螺沟环线", brief, evidence_bundle)
    assert assets, assets
    # 成品资产文件名 = assetId.ext，asset:// 可直查文件
    for a in assets:
        assert a["fileName"] == f"{a['assetId']}{Path(a['fileName']).suffix}", a
        assert a["entityName"] in a["assetId"], a
        assert not a["assetId"].startswith("data_asset_"), a
        assert a["sourceAssetRef"].startswith("entities/"), a
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
