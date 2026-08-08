"""选图与版面职责 contract tests：跨实体去重 + cover/node/closing 版面。

可直接运行：python3 quwoquan_data/tests/local_contract/post/test_route_assets_layout__behavior__functional__local_contract_test.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import core.paths as _paths_mod
import cv2
import numpy as np
import pytest
from content.execution.runtime_state import write_execution_runtime_state
from content.post.article import route_assets as RW
from content.post.article.route_assets import _build_route_assets
from content.source.source_unit import (
    resolve_entity_object_dir,
    write_source_unit,
)
from core.paths import (
    ensure_execution_command_layout,
    ensure_execution_layout,
)
from support.execution_manifest_fixture import build_execution_fixture

EXECUTION_ID = "20260711--travel-article-route-assets--test-region-b--pilot-001"
ENTITIES = ["九寨沟", "稻城亚丁", "色达", "新都桥"]
_RUNTIME_ROOT = Path(tempfile.mkdtemp(prefix="route_assets_layout_rt_"))
_SEEDED = False


def _retarget_runtime() -> None:
    os.environ["QWQ_OUTPUT_ROOT"] = str(_RUNTIME_ROOT)
    _paths_mod.RUNTIME_ROOT = _RUNTIME_ROOT
    _paths_mod.DATA_EXECUTIONS_ROOT = _RUNTIME_ROOT / "tasks"


def _distinct_image(seed: int) -> np.ndarray:
    img = np.zeros((240, 320, 3), np.uint8)
    rng = np.random.default_rng(seed)
    img[:] = rng.integers(0, 255, size=3, dtype=np.uint8)
    cv2.rectangle(img, (20 + seed * 7, 20), (120 + seed * 7, 120), (int(seed * 37) % 255, 30, 200), -1)
    cv2.circle(img, (220, 160), 40 + seed * 5, (10, int(seed * 53) % 255, 80), -1)
    return img


def _seed_images() -> None:
    global _SEEDED
    _retarget_runtime()
    if _SEEDED:
        return
    build_execution_fixture(EXECUTION_ID)
    ensure_execution_layout(EXECUTION_ID)
    ensure_execution_command_layout(EXECUTION_ID, "source")
    write_execution_runtime_state(EXECUTION_ID, command="source")
    shared = _distinct_image(99)  # 故意让前两个实体共享同一张图，测试跨实体去重
    for idx, name in enumerate(ENTITIES):
        obj = resolve_entity_object_dir(EXECUTION_ID, name, etype_hint="景区")
        images: list[dict[str, object]] = []
        for k in range(3):
            if idx < 2 and k == 0:
                img = shared
            else:
                img = _distinct_image(idx * 10 + k)
            ok, buf = cv2.imencode(".jpg", img)
            assert ok
            images.append(
                {
                    "bytes": buf.tobytes(),
                    "caption": f"{name} 图{k}",
                    "relevance": f"{name} 图片{k}",
                }
            )
        write_source_unit(
            obj,
            ordinal=1,
            source_id="curated_story",
            source_md=f"{name} 的来源单元正文。",
            platform="curated",
            source_category="internal-curated",
            url=f"https://example.com/{name}",
            title=name,
            target_ref=f"/entity/地点/景区/{name}",
            relevance=f"{name} 的实景图片",
            images=images,
            execution_id=EXECUTION_ID,
        )
    _SEEDED = True


def _build():
    _seed_images()  # 幂等：standalone 与 pytest 两种收集路径都先播种
    # RC4：文章 1:1 同源——cover/node/closing 全部取自该文章底稿单一来源（baseSourceRef）的
    # assets，不再跨实体聚合借图（删除旧多地点 route 跨源拼图）。
    entity = ENTITIES[0]
    candidates = RW._entity_image_candidates(EXECUTION_ID, entity, f"/entity/地点/景区/{entity}")
    assert candidates, "seeded base source should expose image candidates"
    brief = {
        "carrier": "article",
        "baseSourceRef": candidates[0]["sourceRef"],
        "imagePlan": [
            {"slot": "行程概览", "imageLayout": "fullWidth"},
            {"slot": "节点图集", "gallery": "masonry"},
            {"slot": "费用说明", "imageLayout": "wrapRight"},
        ],
    }
    evidence_bundle = {"routeNodes": [{"entityName": entity, "entityRef": f"地点/景区/{entity}"}]}
    return _build_route_assets(EXECUTION_ID, "测试线路", brief, evidence_bundle)


def test_roles_present():
    # 单一底稿来源下，cover/node/closing 三类职责仍各取一张同源图（同源去重保证互异）。
    assets = _build()
    roles = [a.get("role") for a in assets]
    assert "cover" in roles, roles
    assert "node" in roles, roles
    assert "closing" in roles, roles


def test_node_images_bound_to_their_entity():
    assets = _build()
    for asset in assets:
        if asset.get("role") == "node":
            assert asset["entityName"] in asset["alignmentEvidence"], asset


def test_same_source_assets_perceptually_distinct():
    # RC4：同一底稿来源内选出的 cover/node/closing 必须互异（感知去重），不得复用同一张图。
    assets = _build()
    sources = [a["sourcePath"] for a in assets]
    assert len(sources) == len(set(sources)), sources
    from core.image_safety import dedupe_images

    assert len(dedupe_images([Path(s) for s in sources])) == len(sources), "selected assets must be perceptually distinct"


def test_layouts_not_uniformly_degraded():
    assets = _build()
    layouts = {a["imageLayout"] for a in assets}
    assert len(layouts) >= 2, f"layouts should vary by role, got {layouts}"
    cover = next(a for a in assets if a["role"] == "cover")
    assert cover["imageLayout"] == "fullWidth", cover


def test_article_uses_only_semantically_frozen_source_assets():
    """Article compose不得越过content_plan的同源视觉相关性选择重新扩张素材池。"""
    _seed_images()
    entity = ENTITIES[0]
    candidates = RW._entity_image_candidates(EXECUTION_ID, entity, f"/entity/地点/景区/{entity}")
    assert len(candidates) >= 2
    declared = candidates[1]
    brief = {
        "carrier": "article",
        "baseSourceRef": declared["sourceRef"],
        "assetRefs": [declared["sourceAssetRef"]],
        "imagePlan": [{"slot": "封面", "imageLayout": "fullWidth"}],
    }
    evidence_bundle = {
        "routeNodes": [{"entityName": entity, "entityRef": f"/entity/地点/景区/{entity}"}]
    }

    assets = _build_route_assets(EXECUTION_ID, "声明源图文章", brief, evidence_bundle)

    selected = [asset["sourceAssetRef"] for asset in assets]
    assert selected == [declared["sourceAssetRef"]]


def test_article_skips_frozen_image_already_present_in_canonical_publish():
    """A canonical image collision selects the next frozen source asset."""
    _seed_images()
    entity = ENTITIES[0]
    candidates = RW._entity_image_candidates(
        EXECUTION_ID,
        entity,
        f"/entity/地点/景区/{entity}",
    )
    assert len(candidates) >= 2
    duplicate, unique = candidates[:2]
    brief = {
        "carrier": "article",
        "baseSourceRef": duplicate["sourceRef"],
        "assetRefs": [duplicate["sourceAssetRef"], unique["sourceAssetRef"]],
        "imagePlan": [{"slot": "封面", "imageLayout": "fullWidth"}],
    }
    evidence_bundle = {
        "routeNodes": [
            {"entityName": entity, "entityRef": f"/entity/地点/景区/{entity}"}
        ]
    }
    original = RW._canonical_image_conflict
    RW._canonical_image_conflict = lambda candidate: (
        "canonical image identity duplicated by sha256: fixture"
        if candidate["sourceAssetRef"] == duplicate["sourceAssetRef"]
        else ""
    )
    try:
        assets = _build_route_assets(
            EXECUTION_ID,
            "canonical去重文章",
            brief,
            evidence_bundle,
        )
    finally:
        RW._canonical_image_conflict = original

    assert assets[0]["role"] == "cover"
    assert assets[0]["sourceAssetRef"] == unique["sourceAssetRef"]
    assert duplicate["sourceAssetRef"] not in {
        asset["sourceAssetRef"] for asset in assets
    }


def test_article_without_base_source_cannot_fan_in_route_node_sources():
    _seed_images()
    brief = {"carrier": "article", "imagePlan": []}
    evidence_bundle = {
        "routeNodes": [
            {
                "entityName": entity,
                "entityRef": f"/entity/地点/景区/{entity}",
            }
            for entity in ENTITIES[:2]
        ]
    }

    with pytest.raises(RuntimeError, match="requires exactly one baseSourceRef"):
        _build_route_assets(EXECUTION_ID, "禁止跨底稿拼图", brief, evidence_bundle)
    assert not hasattr(RW, "_build_multi_destination_route_assets")


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"route asset layout tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
