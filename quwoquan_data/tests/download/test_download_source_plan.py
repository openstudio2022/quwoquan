"""download 原文诚实评价回归：source_plan.body 不再冒充真实原文正文。

裸 GET 对 .invalid 域必失败；source.md 只保留 fetch 元信息 + manual_source_plan_note，
不得把 task/source_plan.body 当成真实抓取正文。
覆盖两种 source_plan 形态：顶层 sources / envelope payload.sources。
可直接运行 python3 quwoquan_data/tests/download/test_download_source_plan.py
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
import io
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

_TMP = Path(tempfile.mkdtemp(prefix="dl_srcplan_"))
os.environ["QWQ_DATA_ROOT"] = str(_TMP)
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")

sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.io import read_json, write_json  # noqa: E402
from _common.paths import (  # noqa: E402
    STAGE_DOWNLOAD,
    batch_entity_object_dir,
    batch_inputs_dir,
    ensure_batch_layout,
)
from _common.source_unit import iter_source_units, resolve_entity_object_dir  # noqa: E402
import download.handler as handler_mod  # noqa: E402
from download.handler import handle_download  # noqa: E402
from download.gate import download_requirements  # noqa: E402
from download.source_inputs import curated_sources_for_entity  # noqa: E402
from task import store  # noqa: E402

_TASK = "旅行/地域/四川省/景区/景区全覆盖"
_BATCH = "test_batch"
_EID = "稻城亚丁"
_BODY_MARK = "离线兜底正文：亚丁三神山与牛奶海"


def _real_jpeg(seed: int, *, size=(800, 600)) -> bytes:
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, size=(size[1], size[0], 3), dtype="uint8")
    buf = io.BytesIO()
    Image.fromarray(arr, "RGB").save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _doc(top_level: bool, source_count: int = 1) -> dict:
    entries = [
        {
            "source_id": "s1",
            "platform": "baike",
            "url": "https://daocheng.invalid/guide",
            "body": _BODY_MARK,
        },
        {
            "source_id": "s2",
            "platform": "mafengwo",
            "url": "https://daocheng.invalid/travelogue",
            "body": "离线兜底正文：亚丁徒步与避坑。",
        },
        {
            "source_id": "s3",
            "platform": "官网",
            "url": "https://daocheng.invalid/official",
            "body": "离线兜底正文：亚丁官方开放与预约信息。",
        },
    ][:source_count]
    payload = {
        "sources": entries,
        "imageUrls": [
            {
                "url": "https://img.invalid/a.jpg",
                "platform": "景区官网",
                "license": "CC-BY-SA 4.0",
                "credit": "景区官方",
                "sourceUrl": "https://img.invalid/a.jpg",
                "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                "usageScope": "app_publish",
                "caption": "稻城亚丁主峰",
                "relevance": "支撑稻城亚丁主峰段落",
            },
            {
                "url": "https://img.invalid/b.jpg",
                "platform": "景区官网",
                "license": "CC-BY-SA 4.0",
                "credit": "景区官方",
                "sourceUrl": "https://img.invalid/b.jpg",
                "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                "usageScope": "app_publish",
                "caption": "牛奶海",
                "relevance": "支撑牛奶海段落",
            },
        ],
    }
    return payload if top_level else {
        "schemaVersion": "quwoquan_data.stage_envelope", "ref": _EID,
        "payload": {"entityId": _EID, **payload},
    }


def test_source_screen_report_ref_is_entity_scoped():
    a = handler_mod._source_screen_report_ref("景区甲", "article_qunar_base_1")
    b = handler_mod._source_screen_report_ref("景区乙", "article_qunar_base_1")
    assert a != b
    assert "/" not in a and "/" not in b
    assert "景区甲" in a
    assert "article_qunar_base_1" in a


def _seed_object_plan(top_level: bool, source_count: int = 1) -> None:
    """对象优先：source_plan 落实体对象 1.download/source_plan.json。"""
    ensure_batch_layout(_TASK, _BATCH, "download")
    obj = resolve_entity_object_dir(_TASK, _BATCH, _EID, etype_hint="景区")
    write_json(obj / STAGE_DOWNLOAD / "source_plan.json", _doc(top_level, source_count))


def test_curated_reads_object_plan_top_level_and_envelope():
    _seed_object_plan(top_level=True)
    assert len(curated_sources_for_entity(_TASK, _BATCH, _EID, "景区")) == 1
    _seed_object_plan(top_level=False)
    got = curated_sources_for_entity(_TASK, _BATCH, _EID, "景区")
    assert len(got) == 1 and got[0]["url"].endswith("/guide")


def test_curated_ignores_legacy_layout_only():
    # 旧 stage-first source_plan 不再作为读取真相源。
    legacy_batch = "legacy_only_batch"
    ensure_batch_layout(_TASK, legacy_batch, "download")
    inputs_dir = batch_inputs_dir(_TASK, legacy_batch, "download", "source_plan")
    inputs_dir.mkdir(parents=True, exist_ok=True)
    write_json(inputs_dir / f"{_EID}.json", _doc(top_level=True))
    got = curated_sources_for_entity(_TASK, legacy_batch, _EID, "景区")
    assert got == []


def test_download_requirements_follow_separated_image_and_homepage_quota():
    one_work = store.scaffold_spec(
        vertical="travel",
        organize_by="地域",
        key="四川省",
        name="一图一主页",
        category="景区",
        scope={"region": "四川省", "entityTypes": ["地点/景区"], "coverageTargets": []},
        content={
            "modalityContract": "separated_research",
            "quotas": {
                "entityArticlesPerTarget": 4,
                "imageWorksPerTarget": 1,
                "entityHomepagesPerTarget": 1,
            },
        },
        created_by="test",
    )
    two_works = store.scaffold_spec(
        vertical="travel",
        organize_by="地域",
        key="四川省",
        name="两图一主页",
        category="景区",
        scope={"region": "四川省", "entityTypes": ["地点/景区"], "coverageTargets": []},
        content={
            "modalityContract": "separated_research",
            "quotas": {
                "entityArticlesPerTarget": 2,
                "imageWorksPerTarget": 2,
                "entityHomepagesPerTarget": 1,
            },
        },
        created_by="test",
    )
    store.save_spec(one_work)
    store.save_spec(two_works)

    assert download_requirements(one_work["taskId"])["minImages"] == 2
    assert download_requirements(two_works["taskId"])["minImages"] == 3
    assert download_requirements(one_work["taskId"])["minArticleBaseSources"] == 4
    assert download_requirements(two_works["taskId"])["minArticleBaseSources"] == 2


def test_article_scoped_source_plan_gate_does_not_require_homepage_core_category():
    task = store.scaffold_spec(
        vertical="travel",
        organize_by="地域",
        key="四川省",
        name="文章lane门",
        category="景区",
        scope={"region": "四川省", "entityTypes": ["地点/景区"], "coverageTargets": []},
        content={
            "modalityContract": "separated_research",
            "quotas": {
                "entityArticlesPerTarget": 2,
                "imageWorksPerTarget": 1,
                "entityHomepagesPerTarget": 1,
            },
        },
        created_by="test",
    )
    store.save_spec(task)
    article_sources = [
        {
            "source_id": "article_a",
            "platform": "携程攻略",
            "category": "travelogue",
            "sourceRole": "base",
            "url": "https://you.ctrip.com/travels/example/1.html",
        },
        {
            "source_id": "article_b",
            "platform": "去哪儿攻略",
            "category": "travelogue",
            "sourceRole": "base",
            "url": "https://touch.travel.qunar.com/youji/1",
        },
    ]

    article_issues = handler_mod._source_plan_gate_issues(
        task_id=task["taskId"],
        batch_id="article_lane_gate",
        entity_id=_EID,
        entity_type="景区",
        planned_sources=article_sources,
        selected_lanes={"article"},
        vertical="travel",
    )
    assert not any("missing core source categories" in issue for issue in article_issues)
    assert not any("encyclopedia" in issue or "official" in issue for issue in article_issues)

    homepage_issues = handler_mod._source_plan_gate_issues(
        task_id=task["taskId"],
        batch_id="homepage_lane_gate",
        entity_id=_EID,
        entity_type="景区",
        planned_sources=article_sources,
        selected_lanes={"homepage"},
        vertical="travel",
    )
    assert any("homepage research needs encyclopedia or official evidence" in issue for issue in homepage_issues)

    official_homepage_issues = handler_mod._source_plan_gate_issues(
        task_id=task["taskId"],
        batch_id="homepage_lane_single_official_gate",
        entity_id=_EID,
        entity_type="景区",
        planned_sources=[
            {
                "source_id": "home_official",
                "platform": "景区官网",
                "category": "official",
                "sourceRole": "primary",
                "url": "https://example.com/scenic/about",
            }
        ],
        selected_lanes={"homepage"},
        vertical="travel",
    )
    assert not any("fewer than 2" in issue for issue in official_homepage_issues)
    assert official_homepage_issues == []

    official_site_issues = handler_mod._source_plan_gate_issues(
        task_id=task["taskId"],
        batch_id="homepage_lane_single_official_site_gate",
        entity_id=_EID,
        entity_type="景区",
        planned_sources=[
            {
                "source_id": "home_tourism_site",
                "platform": "旅游官网",
                "category": "official_site",
                "sourceRole": "primary",
                "url": "https://example.com/scenic",
            }
        ],
        selected_lanes={"homepage"},
        vertical="travel",
    )
    assert official_site_issues == []


def test_handle_download_produces_source_unit_from_preset_plan():
    # 对象同构新布局：来源写成 entities/{domain}/{type}/{name}/1.download/sources/01.s1/。
    _seed_object_plan(top_level=True, source_count=3)
    args = argparse.Namespace(task=_TASK, batch=_BATCH, entity_ids=_EID, entity_type="景区")
    original_fetch = handler_mod.fetch_source_payload
    original_image_fetch = handler_mod.fetch_image_payload
    try:
        img_a = _real_jpeg(31)
        img_b = _real_jpeg(32)

        def _fake_fetch(url: str, **_kwargs):
            return {
                "url": url,
                "statusCode": 200,
                "htmlBytes": b"<html></html>",
                "text": (
                    f"{_EID} 景区当天开放时间会随天气调整，进山前最好先确认门票、观光车和预约规则。"
                    f"从游客中心到核心步道之间转场时间不短，如果上午抵达，通常更适合先看主景点再安排长距离徒步。"
                    f"雨后栈道湿滑、午后风大，带老人或孩子同行时要优先考虑体力分配、补给点位置和返程排队。"
                ),
                "sha256": "sha",
            }

        def _fake_image_fetch(url, *, min_bytes=3000):
            body = img_a if url.endswith("a.jpg") else img_b
            import hashlib as _h

            return {
                "url": url,
                "ext": ".jpg",
                "bytes": body,
                "contentType": "image/jpeg",
                "sha256": _h.sha256(body).hexdigest(),
            }

        handler_mod.fetch_source_payload = _fake_fetch
        handler_mod.fetch_image_payload = _fake_image_fetch
        handle_download(args)
    finally:
        handler_mod.fetch_source_payload = original_fetch
        handler_mod.fetch_image_payload = original_image_fetch
    obj = resolve_entity_object_dir(_TASK, _BATCH, _EID, etype_hint="景区")
    units = iter_source_units(obj)
    assert units, f"no source unit under {obj}"
    assert [unit.name for unit in units[:3]] == ["01.s1", "02.s2", "03.s3"], units
    assert len(units) == 4 and units[3].name.startswith("04.image_"), units
    assert (units[3] / "assets" / "index.json").is_file()
    src_md = units[0] / "source.md"
    clean_md = units[0] / "source.clean.md"
    assert src_md.is_file(), f"missing {src_md}"
    assert clean_md.is_file(), f"missing {clean_md}"
    assert (units[0] / "meta.json").is_file()
    source_text = src_md.read_text(encoding="utf-8")
    clean_text = clean_md.read_text(encoding="utf-8")
    assert _BODY_MARK in source_text
    assert "manual_source_plan_note:" in source_text
    assert "开放时间" in source_text and "门票" in source_text and "返程排队" in source_text
    assert _BODY_MARK not in clean_text
    assert "manual_source_plan_note:" not in clean_text
    assert "开放时间" in clean_text and "门票" in clean_text and "返程排队" in clean_text
    # 不再产生对象级散落 images/
    assert not (obj / "images").exists()


def _write_separated_lane_plans(
    batch: str,
    *,
    homepage_sources: list[dict],
    article_sources: list[dict],
    images: list[dict],
) -> None:
    obj = resolve_entity_object_dir(_TASK, batch, _EID, etype_hint="景区") / STAGE_DOWNLOAD
    obj.mkdir(parents=True, exist_ok=True)
    write_json(obj / "homepage_source_plan.json", {"payload": {"sources": homepage_sources}})
    write_json(obj / "article_source_plan.json", {"payload": {"sources": article_sources}})
    write_json(
        obj / "image_source_plan.json",
        {
            "payload": {
                "collections": [
                    {
                        "sourceCollectionId": image.get("sourceCollectionId") or f"fixture:{index}",
                        "creator": image.get("credit") or f"Fixture {index}",
                        "credit": image.get("credit") or f"Fixture {index}",
                        "collectionPageUrl": image.get("sourceUrl") or image["url"],
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


def test_lane_scoped_homepage_download_preserves_other_lanes():
    batch = "lane_scoped_homepage_preserve"
    images = [
        {
            "url": "https://img.invalid/lane-a.jpg",
            "platform": "Wikimedia Commons",
            "license": "CC-BY-SA 4.0",
            "credit": "Ann",
            "sourceUrl": "https://img.invalid/lane-a.jpg",
            "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
            "authorizationProof": "https://img.invalid/lane-a.jpg#rights",
            "usageScope": "app_publish",
            "caption": "稻城亚丁雪山",
            "relevance": "直接呈现稻城亚丁雪山景观",
        },
        {
            "url": "https://img.invalid/lane-b.jpg",
            "platform": "Wikimedia Commons",
            "license": "CC-BY-SA 4.0",
            "credit": "Bob",
            "sourceUrl": "https://img.invalid/lane-b.jpg",
            "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
            "authorizationProof": "https://img.invalid/lane-b.jpg#rights",
            "usageScope": "app_publish",
            "caption": "稻城亚丁牛奶海",
            "relevance": "直接呈现稻城亚丁牛奶海湖泊",
        },
    ]
    article_sources = [
        {
            "source_id": "article_guide",
            "platform": "马蜂窝",
            "category": "travelogue",
            "url": "https://daocheng.invalid/article-guide",
            "sourceUseMode": "factual_reference_only",
        },
        {
            "source_id": "article_official",
            "platform": "景区官网",
            "category": "official_article",
            "url": "https://daocheng.invalid/article-official",
            "sourceUseMode": "factual_reference_only",
        },
    ]
    _write_separated_lane_plans(
        batch,
        homepage_sources=[
            {
                "source_id": "home_old",
                "platform": "维基百科",
                "category": "encyclopedia",
                "url": "https://daocheng.invalid/home-old",
                "sourceUseMode": "factual_reference_only",
            }
        ],
        article_sources=article_sources,
        images=images,
    )

    img_a = _real_jpeg(41)
    img_b = _real_jpeg(42)
    image_calls: list[str] = []

    def _fake_fetch(url: str, **_kwargs):
        return {
            "url": url,
            "statusCode": 200,
            "htmlBytes": b"<html></html>",
            "text": (
                f"{_EID} 景区由雪山、海子、草甸和游客中心组成，游览前需要确认门票预约。"
                f"核心线路通常围绕冲古寺、洛绒牛场、牛奶海和五色海展开。"
                f"景区海拔变化明显，徒步时要注意补给、保暖、防晒和返程时间。"
            ),
            "sha256": "sha-source",
        }

    def _fake_image_fetch(url, *, min_bytes=3000):
        image_calls.append(url)
        import hashlib as _h

        body = img_a if url.endswith("lane-a.jpg") else img_b
        return {
            "url": url,
            "ext": ".jpg",
            "bytes": body,
            "contentType": "image/jpeg",
            "sha256": _h.sha256(body).hexdigest(),
        }

    original_fetch = handler_mod.fetch_source_payload
    original_image_fetch = handler_mod.fetch_image_payload
    try:
        handler_mod.fetch_source_payload = _fake_fetch
        handler_mod.fetch_image_payload = _fake_image_fetch
        handle_download(
            argparse.Namespace(
                task=_TASK,
                batch=batch,
                entity_ids=_EID,
                entity_type="景区",
                lane="all",
                max_workers=1,
            )
        )

        obj = resolve_entity_object_dir(_TASK, batch, _EID, etype_hint="景区")
        previous_other_lane_units = {
            unit.name
            for unit in iter_source_units(obj)
            if read_json(unit / "meta.json").get("researchLane") in {"article", "image"}
        }
        assert previous_other_lane_units

        _write_separated_lane_plans(
            batch,
            homepage_sources=[
                {
                    "source_id": "home_new",
                    "platform": "景区官网",
                    "category": "official",
                    "url": "https://daocheng.invalid/home-new",
                    "sourceUseMode": "factual_reference_only",
                },
                {
                    "source_id": "home_new_support",
                    "platform": "百度百科",
                    "category": "encyclopedia",
                    "url": "https://daocheng.invalid/home-new-support",
                    "sourceUseMode": "factual_reference_only",
                }
            ],
            article_sources=article_sources,
            images=images,
        )
        image_calls.clear()
        handle_download(
            argparse.Namespace(
                task=_TASK,
                batch=batch,
                entity_ids=_EID,
                entity_type="景区",
                lane="homepage",
                max_workers=1,
            )
        )
    finally:
        handler_mod.fetch_source_payload = original_fetch
        handler_mod.fetch_image_payload = original_image_fetch

    obj = resolve_entity_object_dir(_TASK, batch, _EID, etype_hint="景区")
    current_units = {unit.name for unit in iter_source_units(obj)}
    current_other_lane_units = {
        unit.name
        for unit in iter_source_units(obj)
        if read_json(unit / "meta.json").get("researchLane") in {"article", "image"}
    }
    assert previous_other_lane_units.issubset(current_other_lane_units)
    assert any(name.endswith(".home_new") for name in current_units)
    assert not any(name.endswith(".home_old") for name in current_units)
    assert image_calls == []


def test_curated_blocks_dual_scenic_location_tree_conflict():
    conflict_batch = "dual_tree_download"
    ensure_batch_layout(_TASK, conflict_batch, "download")
    scenic = resolve_entity_object_dir(_TASK, conflict_batch, _EID, etype_hint="地点/景区")
    write_json(scenic / STAGE_DOWNLOAD / "source_plan.json", _doc(top_level=True))
    spot = batch_entity_object_dir(_TASK, conflict_batch, "地点", "打卡地", _EID)
    (spot / STAGE_DOWNLOAD).mkdir(parents=True, exist_ok=True)
    write_json(spot / STAGE_DOWNLOAD / "source_plan.json", _doc(top_level=True))
    try:
        curated_sources_for_entity(_TASK, conflict_batch, _EID, "景区")
    except ValueError as exc:
        assert "dual scenic-location trees coexist" in str(exc) or "entity type drift" in str(exc)
    else:
        raise AssertionError("expected dual-tree conflict")


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"download source_plan tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
