"""选图与版面职责 contract tests：跨实体去重 + cover/node/closing 版面。

可直接运行：python3 quwoquan_data/tests/test_route_assets_layout.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

os.environ["QWQ_RUNTIME_ROOT"] = tempfile.mkdtemp()

import numpy as np  # noqa: E402
import cv2  # noqa: E402

from _common.paths import batch_sources_dir, ensure_batch_layout, ensure_task_layout  # noqa: E402
from produce.route_workflow import _build_route_assets  # noqa: E402


TASK = "asset_layout_test"
BATCH = "pilot"
ENTITIES = ["九寨沟", "稻城亚丁", "色达", "新都桥"]


def _distinct_image(seed: int) -> np.ndarray:
    img = np.zeros((240, 320, 3), np.uint8)
    rng = np.random.default_rng(seed)
    img[:] = rng.integers(0, 255, size=3, dtype=np.uint8)
    cv2.rectangle(img, (20 + seed * 7, 20), (120 + seed * 7, 120), (int(seed * 37) % 255, 30, 200), -1)
    cv2.circle(img, (220, 160), 40 + seed * 5, (10, int(seed * 53) % 255, 80), -1)
    return img


def _seed_images() -> None:
    ensure_task_layout(TASK)
    ensure_batch_layout(TASK, BATCH, "download")
    shared = _distinct_image(99)  # 故意让前两个实体共享同一张图，测试跨实体去重
    for idx, name in enumerate(ENTITIES):
        images_dir = batch_sources_dir(TASK, BATCH, name) / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        for k in range(3):
            if idx < 2 and k == 0:
                img = shared
            else:
                img = _distinct_image(idx * 10 + k)
            cv2.imwrite(str(images_dir / f"img_{k:02d}.jpg"), img)


def _build():
    _seed_images()  # 幂等：standalone 与 pytest 两种收集路径都先播种
    brief = {
        "imagePlan": [
            {"slot": "行程概览", "imageLayout": "fullWidth"},
            {"slot": "节点图集", "gallery": "masonry"},
            {"slot": "费用说明", "imageLayout": "wrapRight"},
        ]
    }
    evidence_bundle = {"routeNodes": [{"entityName": n, "entityRef": f"地点/景区/{n}"} for n in ENTITIES]}
    return _build_route_assets(TASK, BATCH, "测试线路", brief, evidence_bundle)


def test_roles_present():
    assets = _build()
    roles = [a.get("role") for a in assets]
    assert "cover" in roles, roles
    assert roles.count("node") >= 3, roles
    assert "closing" in roles, roles


def test_node_images_bound_to_their_entity():
    assets = _build()
    for asset in assets:
        if asset.get("role") == "node":
            assert asset["entityName"] in asset["sourcePath"], asset


def test_cross_entity_dedup_no_duplicate_source():
    assets = _build()
    sources = [a["sourcePath"] for a in assets]
    assert len(sources) == len(set(sources)), sources
    # 共享图只应被选用一次（跨实体感知去重）
    from _common.image_safety import dedupe_images

    assert len(dedupe_images([Path(s) for s in sources])) == len(sources), "selected assets must be perceptually distinct"


def test_layouts_not_uniformly_degraded():
    assets = _build()
    layouts = {a["imageLayout"] for a in assets}
    assert len(layouts) >= 2, f"layouts should vary by role, got {layouts}"
    cover = next(a for a in assets if a["role"] == "cover")
    assert cover["imageLayout"] == "fullWidth", cover


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"route asset layout tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
