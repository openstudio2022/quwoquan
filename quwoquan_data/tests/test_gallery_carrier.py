"""画报载体 contract tests：载体路由 + gallery compose + 载体感知门。

可直接运行：python3 quwoquan_data/tests/test_gallery_carrier.py
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

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common.paths import (  # noqa: E402
    batch_inputs_dir,
    batch_sources_dir,
    ensure_batch_layout,
    ensure_task_layout,
)
from _common.io import read_json, write_json  # noqa: E402
from _common.content_evidence import public_byline_label  # noqa: E402
from _common.draft_io import read_writing_pack, write_agent_draft  # noqa: E402
from produce import route_workflow as RW  # noqa: E402
from produce.route_workflow import (  # noqa: E402
    analyze_route_ref,
    build_route_writing_pack,
    review_route_draft,
)
from agent_draft_kit import gallery_article  # noqa: E402


TASK = "gallery_test"
BATCH = "pilot"
ENTITIES = ["雅拉雪山", "黑石城", "莲花湖", "墨石公园"]


def _distinct_image(seed: int) -> np.ndarray:
    img = np.zeros((240, 320, 3), np.uint8)
    rng = np.random.default_rng(seed)
    img[:] = rng.integers(0, 255, size=3, dtype=np.uint8)
    cv2.circle(img, (160 + seed, 120), 30 + seed * 4, (int(seed * 31) % 255, 60, 180), -1)
    return img


_SOURCE_PATHS: list[str] = []


def _seed():
    ensure_task_layout(TASK)
    ensure_batch_layout(TASK, BATCH, "download")
    ensure_batch_layout(TASK, BATCH, "produce")
    _SOURCE_PATHS.clear()
    for idx, name in enumerate(ENTITIES):
        d = batch_sources_dir(TASK, BATCH, name) / "images"
        d.mkdir(parents=True, exist_ok=True)
        for k in range(2):
            cv2.imwrite(str(d / f"img_{k}.jpg"), _distinct_image(idx * 5 + k + 1))
        src = batch_sources_dir(TASK, BATCH, name) / "curated_story" / "source.md"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text(f"{name} 的光影与现场氛围记录，仅作内部参考。\n", encoding="utf-8")
        _SOURCE_PATHS.append(str(src))


def _gallery_brief() -> dict:
    return {
        "carrier": "gallery",
        "imagePolicy": {"minImages": 4, "captionMaxChars": 20},
        "titleHint": "贡嘎西坡光影图集",
        "templateId": "主题_风光画报",
        "entityRefs": ENTITIES,
        "tagRefs": ["Topic/旅行/主题/风光"],
        "render": {"articleTemplate": "gallery", "fontPreset": "clean"},
        "imagePlan": [
            {"slot": "封面", "imageLayout": "fullWidth"},
            {"slot": "光影图集", "gallery": "masonry"},
        ],
    }


def _low_narrative_quality_payload() -> dict:
    nodes = [{"entityName": n, "entityRef": f"地点/景区/{n}", "mainlineEvidence": [], "emotionEvidence": {}} for n in ENTITIES]
    return {
        "evidenceBundle": {"routeNodes": nodes},
        "storySpine": {},
        "sourceUrls": ["https://example.com/gallery"],
        "sourcePaths": list(_SOURCE_PATHS),
    }


def test_text_heavy_forces_article():
    assets = [{"isTextHeavy": True, "imageStatus": "text_heavy"}] + [{"imageStatus": "safe"} for _ in range(4)]
    assert RW.resolve_carrier({"carrier": "gallery"}, {"routeNodes": []}, assets) == "article"


def test_declared_article_stays_article():
    assets = [{"imageStatus": "safe"} for _ in range(6)]
    assert RW.resolve_carrier({"carrier": "article"}, {"routeNodes": []}, assets) == "article"


def test_image_heavy_low_narrative_routes_gallery():
    assets = [{"imageStatus": "safe"} for _ in range(5)]
    assert RW.resolve_carrier({}, {"routeNodes": []}, assets) == "gallery"


REF = "贡嘎画报"


def test_gallery_compose_brief_then_agent_draft_green():
    _seed()
    brief = _gallery_brief()
    write_json(batch_inputs_dir(TASK, BATCH, "produce", "compose") / f"{REF}.json", brief)
    quality = _low_narrative_quality_payload()

    # prepare：写作契约解析为 gallery 载体 + 占位草稿。
    pack = build_route_writing_pack(TASK, BATCH, REF, brief, quality)
    assert pack["carrier"] == "gallery", pack.get("carrier")
    assert pack["publishLayout"] == "gallery"
    assert read_writing_pack(TASK, BATCH, REF) is not None
    placeholder = review_route_draft(TASK, BATCH, REF, brief, quality)
    assert placeholder["decision"] == "revision_needed"
    assert not placeholder["checks"]["generatorProvenance"]["passed"]

    # 会话模型创作画报（图为主、配小字）→ review 全绿。
    byline = public_byline_label(str(brief.get("templateId")), brief.get("creator") or {})
    md = gallery_article(brief["titleHint"], byline, pack.get("assets") or [])
    assert md.count(":::figure") >= 4, md
    assert "\n\n\n" not in md, "gallery must not have large blank gaps"
    write_agent_draft(
        TASK,
        BATCH,
        REF,
        md,
        model="test-agent/contract",
        cited_source_paths=quality.get("sourcePaths") or [],
        covered_facts=[],
    )
    review = review_route_draft(TASK, BATCH, REF, brief, quality)
    assert review["decision"] == "approved", review["issues"]
    assert review["checks"]["carrierConsistency"]["passed"]
    assert review["checks"]["imageGate"]["passed"]
    assert review["checks"]["galleryCaption"]["passed"], review["checks"]["galleryCaption"]["issues"]
    assert "travelogueDensity" not in review["checks"], "画报载体不应套长文叙事门"
    assert review["generator"] == "agent"


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"gallery carrier tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
