"""build 实体主页真实链路契约测试。

prepare 下发产出契约（含 SOP 模板路径 + region/season 菜单 + 字数下限）；
validate 采纳门拦截：主页缺失 / 字数不足 / conditionProfile 取值越界。
catalog 按脚本相对路径定位，故临时 QWQ_DATA_ROOT 不影响 region/season 校验。
可直接运行 python3 quwoquan_data/tests/build/test_build_homepage.py
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
import shutil
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="build_homepage_"))
os.environ["QWQ_DATA_ROOT"] = str(_TMP)
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")

sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.io import read_json, write_json  # noqa: E402
from _common.batch_asset_registry import allocate_post_asset_id, load_batch_asset_registry  # noqa: E402
from _common.batch_manifest import load_batch_manifest, write_batch_manifest  # noqa: E402
from _common.entity_object import sync_entity_object_to_task_mirror, write_entity_object_index  # noqa: E402
from _common.localization import has_traditional_chars  # noqa: E402
from _common.paths import batch_entity_object_dir, batch_entity_page_input_path, batch_root, task_data  # noqa: E402
from _common.source_unit import write_source_unit  # noqa: E402
from _common.wiki_wikitext import parse_wikitext_placements  # noqa: E402
from build.handler import handle_build  # noqa: E402
from build.homepage import (  # noqa: E402
    MIN_PAGE_CHARS,
    _entity_draft_dir,
    _homepage_outline_issues,
    _homepage_source_figure_issues,
    _replace_homepage_source_asset_refs,
    _split_fact_sentences,
    materialize_entity_pages,
    validate_entity_page_inputs,
    validate_entity_pages,
)
from task.store import load_spec, save_spec  # noqa: E402

_TASK = "旅行/地域/四川省/景区/景区全覆盖"
_BATCH = "build_test"
_DOMAIN, _ETYPE, _NAME = "地点", "景区", "稻城亚丁"
# discovery_seed/2 起 geoTagRef 为物化必填（_REQUIRED_ENTITY_FIELDS）；
# coverageTargets 契约字段经 prepare payload 透传写入 _entity.json。
_GEO_TAG_REF = "Topic/地理/行政区/中国/四川省/甘孜藏族自治州/稻城县"


def _seed_spec() -> None:
    shutil.rmtree(task_data(_TASK).entities_dir(), ignore_errors=True)
    shutil.rmtree(batch_entity_object_dir(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME), ignore_errors=True)
    save_spec({
        "schemaVersion": "quwoquan.task.spec",
        "taskId": _TASK,
        "scope": {"coverageTargets": [{"entityType": "地点/景区", "name": _NAME, "geoTagRef": _GEO_TAG_REF}]},
        "conditionAxes": {"region": {"applicable": True}, "season": {"applicable": True}},
    })
    write_batch_manifest(
        _TASK,
        _BATCH,
        coverage_targets=[{"entityType": f"{_DOMAIN}/{_ETYPE}", "name": _NAME, "geoTagRef": _GEO_TAG_REF}],
        command="test:build-homepage",
    )


def _materialize_entity(regions: list[str], seasons: list[str], *, page_chars: int = 900) -> None:
    entity_dir = batch_entity_object_dir(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME)
    entity_dir.mkdir(parents=True, exist_ok=True)
    body = "稻" * page_chars
    region_text = "、".join(regions) if regions else "未限定地域"
    season_text = "、".join(seasons) if seasons else "未限定季节"
    (entity_dir / "page.md").write_text(
        f"# {_NAME}\n\n{body}\n\n事实出处：本页适合地域为{region_text}，适合季节为{season_text}。\n",
        encoding="utf-8",
    )
    evidence_refs = [
        {"field": "regions", "value": value, "source": "page.md", "path": "page.md", "note": "主页正文事实出处"}
        for value in regions
    ] + [
        {"field": "seasons", "value": value, "source": "page.md", "path": "page.md", "note": "主页正文事实出处"}
        for value in seasons
    ]
    write_json(entity_dir / "_entity.json", {
        "label": _NAME,
        "domain": _DOMAIN,
        "type": _ETYPE,
        "sourceTaskId": _TASK,
        "geoTagRef": _GEO_TAG_REF,
        "conditionProfile": {
            "regions": regions,
            "seasons": seasons,
            "altitudeMeters": 4000,
            "evidenceRefs": evidence_refs,
        },
    })
    write_json(entity_dir / "manifest.json", {"tagRefs": [], "assets": [], "generator": "agent"})


def _seed_homepage_source(asset_name: str = "cover.jpg") -> dict[str, str]:
    entity_dir = batch_entity_object_dir(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME)
    manifest = write_source_unit(
        entity_dir,
        ordinal=1,
        source_id="home_wikipedia",
        source_md=f"{_NAME} 位于高原与雪山景观之间，是百科型实体主页测试来源。",
        quality={
            "quality": "C-context",
            "score": 2,
            "fetchSucceeded": True,
        },
        platform="维基百科",
        source_category="encyclopedia",
        source_use_mode="factual_reference_only",
        research_lane="homepage",
        images=[
            {
                "fileName": asset_name,
                "bytes": b"fake-source-cover",
                "ext": Path(asset_name).suffix or ".jpg",
                "license": "CC BY-SA 4.0",
                "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                "authorizationProof": "fixture homepage image rights",
                "caption": "稻城亚丁测试主图",
            }
        ],
        task_id=_TASK,
        batch_id=_BATCH,
    )
    source_ref = manifest["sourceRef"]
    unit_ref = manifest["sourceUnitRef"]
    asset_index = read_json(batch_root(_TASK, _BATCH) / unit_ref / "assets" / "index.json")
    asset_file = asset_index["assets"][0]["fileName"]
    source_asset_ref = f"{unit_ref}/assets/{asset_file}"
    quality_dir = entity_dir / "2.quality"
    quality_dir.mkdir(exist_ok=True)
    write_json(quality_dir / "quality_analysis.json", {"baseDraft": {"sourceRef": source_ref}, "sourcePaths": [source_ref]})
    compose_dir = entity_dir / "3.compose"
    compose_dir.mkdir(exist_ok=True)
    write_json(compose_dir / "entity_page_input.json", {"payload": {"baseDraft": {"sourceRef": source_ref}}})
    return {
        "sourceRef": source_ref,
        "sourceAssetRef": source_asset_ref,
        "license": "CC BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": "fixture homepage image rights",
    }


def _homepage_asset_id(source_refs: dict[str, str]) -> str:
    manifest = load_batch_manifest(_TASK, _BATCH)
    global_batch_seq = int(manifest.get("globalBatchSeq") or 0)
    registry = load_batch_asset_registry(_TASK, _BATCH, global_batch_seq)
    return allocate_post_asset_id(
        entity_name=_NAME,
        role="cover",
        ref=source_refs["sourceAssetRef"],
        global_batch_seq=global_batch_seq,
        registry=registry,
    )


def _seed_entity_review_sidecars(source_refs: list[str]) -> None:
    entity_dir = batch_entity_object_dir(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME)
    draft_dir = entity_dir / "4.draft"
    draft_dir.mkdir(parents=True, exist_ok=True)
    draft_path = draft_dir / "page.md"
    final_path = entity_dir / "page.md"
    if not draft_path.is_file() and final_path.is_file():
        draft_path.write_text(final_path.read_text(encoding="utf-8"), encoding="utf-8")
    review_dir = entity_dir / "5.review"
    review_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        review_dir / "review.json",
        {
            "decision": "approved",
            "issues": [],
            "checks": {
                "entityPageQuality": {"passed": True, "issues": []},
                "sourceReadiness": {"passed": True, "issues": []},
            },
        },
    )
    write_json(
        review_dir / "provenance.json",
        {
            "originalSources": [{"sourceRef": ref} for ref in source_refs],
            "agentInput": {"writingPack": "fixture homepage writing pack"},
            "final": {"generator": "agent"},
        },
    )
    write_json(
        review_dir / "finalization_report.json",
        {
            "schemaVersion": "quwoquan_data.finalization_report",
            "draftArticleRef": "4.draft/page.md",
            "finalArticleRef": "page.md",
            "draftSha256": "fixture-draft-sha",
            "finalSha256": "fixture-final-sha",
        },
    )
    write_entity_object_index(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME)
    sync_entity_object_to_task_mirror(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME)


def _seed_official_homepage_source(asset_name: str = "") -> str:
    entity_dir = batch_entity_object_dir(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME)
    images = []
    if asset_name:
        images.append(
            {
                "fileName": asset_name,
                "bytes": b"fake-official-cover",
                "ext": Path(asset_name).suffix or ".jpg",
                "license": "CC BY-SA 4.0",
                "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                "authorizationProof": "fixture official homepage image",
                "caption": "官方主页配图",
            }
        )
    manifest = write_source_unit(
        entity_dir,
        ordinal=2,
        source_id="home_official",
        source_md=(
            f"{_NAME}位于四川省甘孜藏族自治州稻城县香格里拉镇。"
            f"{_NAME}以仙乃日、央迈勇、夏诺多吉三座雪山为核心景观。"
            f"{_NAME}景区包含高山湖泊、草甸、峡谷和藏族聚落等自然与人文资源。"
            f"{_NAME}游览需要关注海拔、天气、步道和交通接驳等官方提示。"
            f"{_NAME}的开放、预约和票务规则应以景区官方公告为准。"
        ),
        quality={
            "quality": "B-fact",
            "score": 6,
            "fetchSucceeded": True,
        },
        platform="景区官网",
        source_category="official",
        source_use_mode="factual_reference_only",
        research_lane="homepage",
        images=images,
        task_id=_TASK,
        batch_id=_BATCH,
    )
    return manifest["sourceRef"]


def _seed_official_judge_verdict(source_ref: str) -> None:
    """官方（非百科）主页源 fail-closed：必须有 homepage_source_judge primary verdict 才可晋升。"""
    from _common.homepage_source_judge import SOURCE_JUDGE_SCHEMA_VERSION, SOURCE_JUDGE_VERDICT_FILE

    # sourceRef 相对 batch 根（base_draft_candidates 契约）。
    unit_dir = batch_root(_TASK, _BATCH) / Path(source_ref).parent
    write_json(unit_dir / SOURCE_JUDGE_VERDICT_FILE, {
        "schemaVersion": SOURCE_JUDGE_SCHEMA_VERSION,
        "targetEntity": _NAME,
        "sourcePageType": "entity_homepage",
        "entityMatch": "exact",
        "primaryEligible": True,
        "recommendedAction": "primary",
        "confidence": 0.9,
        "reasons": ["官方页面围绕稻城亚丁本体介绍"],
        "evidence": [{"field": "headText", "quote": f"{_NAME}位于四川省甘孜藏族自治州稻城县"}],
    })


def _seed_factready_encyclopedia_homepage_source(asset_name: str = "") -> str:
    """P3 三类解耦：实体主页 base draft 主源【只限百科】。

    播种一个 fact-ready 维基百科来源单元（事实充足、可被择优为 baseDraft）。
    """
    entity_dir = batch_entity_object_dir(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME)
    images = []
    if asset_name:
        images.append(
            {
                "fileName": asset_name,
                "bytes": b"fake-encyclopedia-cover",
                "ext": Path(asset_name).suffix or ".jpg",
                "license": "CC BY-SA 4.0",
                "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                "authorizationProof": "fixture encyclopedia homepage image",
                "caption": "百科主页配图",
            }
        )
    manifest = write_source_unit(
        entity_dir,
        ordinal=2,
        source_id="home_wikipedia_factready",
        source_md=(
            f"{_NAME}位于四川省甘孜藏族自治州稻城县香格里拉镇。"
            f"{_NAME}以仙乃日、央迈勇、夏诺多吉三座雪山为核心景观。"
            f"{_NAME}景区包含高山湖泊、草甸、峡谷和藏族聚落等自然与人文资源。"
            f"{_NAME}游览需要关注海拔、天气、步道和交通接驳等官方提示。"
            f"{_NAME}的开放、预约和票务规则应以景区官方公告为准。"
        ),
        quality={
            "quality": "B-fact",
            "score": 6,
            "fetchSucceeded": True,
        },
        platform="维基百科",
        source_category="encyclopedia",
        source_use_mode="factual_reference_only",
        research_lane="homepage",
        images=images,
        task_id=_TASK,
        batch_id=_BATCH,
    )
    return manifest["sourceRef"]


def _long_section(label: str, repeated: int = 18) -> str:
    return "".join(f"稻城亚丁的{label}包含可核验的景观、方位、游览观察和背景事实。" for _ in range(repeated))


def _seed_structured_wiki_homepage_source() -> str:
    entity_dir = batch_entity_object_dir(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME)
    source_md = (
        f"{_NAME}位于四川甘孜州稻城县，是以高原雪山和湖泊为代表的自然景区。"
        f"{_NAME}的核心景观围绕仙乃日、央迈勇、夏诺多吉展开。\n\n"
        "== 三怙主雪山 ==\n"
        + _long_section("三怙主雪山")
        + "\n\n=== 仙乃日 ===\n"
        "[[File:Valley near sacred mountain Xiannairi Yading Biosphere Reserve.jpg|thumb|仙乃日峰]]\n"
        + _long_section("仙乃日")
        + "\n\n=== 央迈勇 ===\n"
        "[[File:Yading Sacred Mountain.jpg|thumb|央迈勇峰南坡]]\n"
        + _long_section("央迈勇")
        + "\n\n=== 夏诺多吉 ===\n"
        + _long_section("夏诺多吉")
        + "\n\n== 相关问题 ==\n"
        + _long_section("相关问题")
    )
    clean_md = (
        f"{_NAME}位于四川甘孜州稻城县，是以高原雪山和湖泊为代表的自然景区。"
        f"{_NAME}的核心景观围绕仙乃日、央迈勇、夏诺多吉展开。\n\n"
        + _long_section("三怙主雪山")
        + "\n\n"
        + _long_section("仙乃日")
        + "\n\n"
        + _long_section("央迈勇")
        + "\n\n"
        + _long_section("夏诺多吉")
        + "\n\n"
        + _long_section("相关问题")
    )
    outline, placements = parse_wikitext_placements(source_md, min_section_body_chars=60)
    manifest = write_source_unit(
        entity_dir,
        ordinal=3,
        source_id="home_wikipedia_structured",
        source_md=source_md,
        clean_md=clean_md,
        quality={"quality": "A-fact", "score": 9, "fetchSucceeded": True},
        platform="维基百科",
        source_category="encyclopedia",
        source_use_mode="factual_reference_only",
        research_lane="homepage",
        images=[
            {
                "fileName": "Valley_near_sacred_mountain_Xiannairi_Yading_Biosphere_Reserve.jpg",
                "bytes": b"fake-xiannairi",
                "ext": ".jpg",
                "license": "CC BY-SA 4.0",
                "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                "authorizationProof": "https://commons.wikimedia.org/wiki/File:Valley_near_sacred_mountain_Xiannairi_Yading_Biosphere_Reserve.jpg",
                "caption": "仙乃日峰",
            },
            {
                "fileName": "Yading_Sacred_Mountain.jpg",
                "bytes": b"fake-yangmaiyong",
                "ext": ".jpg",
                "license": "CC BY-SA 4.0",
                "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                "authorizationProof": "https://commons.wikimedia.org/wiki/File:Yading_Sacred_Mountain.jpg",
                "caption": "央迈勇峰南坡",
            },
        ],
        task_id=_TASK,
        batch_id=_BATCH,
    )
    meta_path = batch_root(_TASK, _BATCH) / manifest["sourceUnitRef"] / "meta.json"
    meta = read_json(meta_path)
    meta["sectionOutline"] = outline
    meta["imagePlacements"] = placements
    write_json(meta_path, meta)
    return manifest["sourceRef"]


def _materialize_entity_with_asset() -> None:
    _materialize_entity(["高原"], ["秋"])
    entity_dir = batch_entity_object_dir(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME)
    source_refs = _seed_homepage_source("cover.jpg")
    asset_id = _homepage_asset_id(source_refs)
    file_name = f"{asset_id}.jpg"
    # 三段结构契约：成品 page.md 必须在 frontmatter 声明唯一 coverImage。
    (entity_dir / "page.md").write_text(
        f"---\ncoverImage: asset://{asset_id}\n---\n\n# 稻城亚丁\n\n{'稻' * 900}\n",
        encoding="utf-8",
    )
    assets_dir = entity_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / file_name).write_bytes(b"fake-cover")
    unit_ref = source_refs["sourceRef"]
    write_json(entity_dir / "manifest.json", {
        "tagRefs": [],
        "generator": "agent",
        "textSourceRefs": [unit_ref],
        "imageSourceRefs": [unit_ref],
        "sourceRefs": [unit_ref],
        "assets": [{
            "assetId": asset_id,
            "fileName": file_name,
            "role": "cover",
            "caption": "雪山",
            **source_refs,
        }],
    })
    _seed_entity_review_sidecars([unit_ref])


def test_prepare_writes_entity_page_contract():
    _seed_spec()
    handle_build(argparse.Namespace(task=_TASK, batch=_BATCH, stage="prepare"))
    inp = batch_entity_page_input_path(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME)
    assert inp.is_file(), f"missing {inp}"
    payload = read_json(inp)["payload"]
    assert payload["minChars"] == MIN_PAGE_CHARS
    assert payload["sopTemplate"].endswith("template.md")
    assert "高原" in payload["regionMenu"] and "秋" in payload["seasonMenu"]


def test_prepare_promotes_fact_ready_encyclopedia_over_short_wiki_redirect():
    # P3 三类解耦：实体主页 base draft 主源【只限百科】——fact-ready 百科被择优为 baseDraft。
    _seed_spec()
    _seed_homepage_source("cover.jpg")  # 短 wiki redirect，非 fact-ready
    enc_ref = _seed_factready_encyclopedia_homepage_source()
    handle_build(argparse.Namespace(task=_TASK, batch=_BATCH, stage="prepare"))
    inp = batch_entity_page_input_path(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME)
    payload = read_json(inp)["payload"]
    assert payload["baseDraft"]["sourceRef"] == enc_ref
    assert len(payload["baseDraft"]["text"]) > 100


def test_prepare_promotes_official_homepage_source():
    # 主页权威源已收敛为百科/官方同级：fact-ready 官方 source 可作为 baseDraft，
    # 但官方（非百科）源必须先过 homepage_source_judge 语义判别（fail-closed）。
    _seed_spec()
    _seed_homepage_source("cover.jpg")  # 短 wiki，非 fact-ready
    official_ref = _seed_official_homepage_source()
    handle_build(argparse.Namespace(task=_TASK, batch=_BATCH, stage="prepare"))
    inp = batch_entity_page_input_path(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME)
    payload = read_json(inp)["payload"]
    # 无 verdict：灰区来源不得晋升，且判别请求已落盘等待 Agent。
    from _common.homepage_source_judge import SOURCE_JUDGE_REQUEST_FILE

    assert payload["baseDraft"] == {}
    unit_dir = batch_root(_TASK, _BATCH) / Path(official_ref).parent
    assert (unit_dir / SOURCE_JUDGE_REQUEST_FILE).is_file()
    # Agent 写回 primary verdict 后重跑 prepare → 官方源晋升 baseDraft。
    _seed_official_judge_verdict(official_ref)
    handle_build(argparse.Namespace(task=_TASK, batch=_BATCH, stage="prepare"))
    payload = read_json(inp)["payload"]
    assert payload["baseDraft"]["sourceRef"] == official_ref
    assert len(payload["baseDraft"]["text"]) > 100


def test_prepare_does_not_promote_non_fact_ready_homepage_source():
    _seed_spec()
    _seed_homepage_source("cover.jpg")
    handle_build(argparse.Namespace(task=_TASK, batch=_BATCH, stage="prepare"))
    inp = batch_entity_page_input_path(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME)
    payload = read_json(inp)["payload"]
    assert payload["baseDraft"] == {}


def test_validate_entity_page_inputs_blocks_homepage_without_publishable_asset():
    _seed_spec()
    _seed_factready_encyclopedia_homepage_source()
    handle_build(argparse.Namespace(task=_TASK, batch=_BATCH, stage="prepare"))
    issues = validate_entity_page_inputs(_TASK, _BATCH, load_spec(_TASK))
    assert any("homepage lane 无可发布图片资产" in issue for issue in issues), issues


def test_prepare_homepage_prompt_embeds_outline_and_source_asset_figures():
    _seed_spec()
    source_ref = _seed_structured_wiki_homepage_source()

    handle_build(argparse.Namespace(task=_TASK, batch=_BATCH, stage="prepare"))

    payload = read_json(batch_entity_page_input_path(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME))["payload"]
    base = payload["baseDraft"]
    assert base["sourceRef"] == source_ref
    assert "## 三怙主雪山" in base["markdown"]
    assert "### 仙乃日" in base["markdown"]
    assert "### 央迈勇" in base["markdown"]
    assert payload["availableImages"][0]["sectionAnchor"] == "仙乃日"
    assert payload["availableImages"][1]["sectionAnchor"] == "央迈勇"
    # AI 最小干扰协议：模型输入零 asset:// / :::figure；非封面同源图以
    # [[IMG:fig_NN]] 极简单行占位进入底稿原位（不含图注；图注真相源在 bindings）。
    assert "asset://" not in base["markdown"]
    assert ":::figure" not in base["markdown"]
    assert "[[IMG:fig_02]]" in base["markdown"]
    assert "[[IMG:fig_02]] 央迈勇峰南坡" not in base["markdown"]
    bindings = payload["imagePlaceholderBindings"]
    assert [row["figId"] for row in bindings] == ["fig_02"], bindings
    assert bindings[0]["sourceAssetId"] == "003_002"
    assert bindings[0]["caption"] == "央迈勇峰南坡"

    prompt = (_entity_draft_dir(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME) / "prompt.md").read_text(encoding="utf-8")
    assert "## 底稿材料" in prompt
    assert "## 三怙主雪山" in prompt
    assert "### 仙乃日" in prompt
    # 契约 partial 中允许出现 `asset://` 字样（禁令说明），但真实 asset id 不得泄漏。
    assert "asset://003_" not in prompt
    assert "[[IMG:fig_02]]" in prompt
    assert "央迈勇峰南坡" not in prompt  # 图注不进 prompt（bindings 是唯一真相源）
    assert "图片占位符纪律" in prompt
    assert "无需也不必" not in prompt


def test_homepage_contract_blocks_flattened_sections_and_dropped_figures():
    outline = [
        {"level": 2, "title": "三怙主雪山"},
        {"level": 3, "title": "仙乃日"},
        {"level": 3, "title": "央迈勇"},
    ]
    good = (
        "# 稻城亚丁\n\n"
        "## 三怙主雪山\n\n概述。\n\n"
        "### 仙乃日\n\n:::figure id=\"cover\" layout=\"fullWidth\" caption=\"仙乃日峰\"\nasset://003_001\n:::\n\n正文。\n\n"
        "### 央迈勇\n\n:::figure id=\"homepage-source-002\" layout=\"wrapRight\" caption=\"央迈勇峰南坡\"\nasset://003_002\n:::\n\n正文。\n"
    )
    flat = good.replace("### 仙乃日", "## 仙乃日")
    assert not _homepage_outline_issues(outline, good, "地点/景区/稻城亚丁")
    assert any("仙乃日" in issue and "`###`" in issue for issue in _homepage_outline_issues(outline, flat, "地点/景区/稻城亚丁"))

    base = {"markdown": ":::figure\nasset://003_001\n:::\n\n:::figure\nasset://003_002\n:::"}
    assert not _homepage_source_figure_issues(base, good, "地点/景区/稻城亚丁")
    dropped = good.replace("asset://003_002", "asset://other")
    assert any("asset://003_002" in issue for issue in _homepage_source_figure_issues(base, dropped, "地点/景区/稻城亚丁"))

    replaced = _replace_homepage_source_asset_refs(
        good,
        [
            {"sourceAssetId": "003_001", "assetId": "稻城亚丁_cover_abcd"},
            {"sourceAssetId": "003_002", "assetId": "稻城亚丁_detail_efgh"},
        ],
    )
    assert "asset://003_001" not in replaced
    assert "asset://稻城亚丁_cover_abcd" in replaced
    assert "asset://稻城亚丁_detail_efgh" in replaced


def test_validate_blocks_missing_homepage():
    _seed_spec()
    issues = validate_entity_pages(_TASK, _BATCH, load_spec(_TASK))
    assert any("page.md 缺失" in i for i in issues), issues


def test_validate_passes_when_complete():
    _seed_spec()
    _materialize_entity(["高原", "雪山"], ["秋", "冬"])
    entity_dir = batch_entity_object_dir(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME)
    page = entity_dir / "page.md"
    source_refs = _seed_homepage_source("cover.jpg")
    asset_id = _homepage_asset_id(source_refs)
    file_name = f"{asset_id}.jpg"
    # 三段结构契约：成品 page.md 必须在 frontmatter 声明唯一 coverImage。
    page.write_text(
        f"---\ncoverImage: asset://{asset_id}\n---\n\n" + page.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    (entity_dir / "assets").mkdir(parents=True, exist_ok=True)
    (entity_dir / "assets" / file_name).write_bytes(b"fake-cover")
    unit_ref = source_refs["sourceRef"]
    manifest = read_json(entity_dir / "manifest.json")
    manifest["assets"] = [{
        "assetId": asset_id,
        "fileName": file_name,
        "role": "cover",
        "caption": "雪山",
        **source_refs,
    }]
    manifest["generator"] = "agent"
    manifest["textSourceRefs"] = [unit_ref]
    manifest["imageSourceRefs"] = [unit_ref]
    manifest["sourceRefs"] = [unit_ref]
    write_json(entity_dir / "manifest.json", manifest)
    _seed_entity_review_sidecars([unit_ref])
    issues = validate_entity_pages(_TASK, _BATCH, load_spec(_TASK))
    assert issues == [], issues
    assert (entity_dir / "4.draft" / "page.md").is_file()
    assert (entity_dir / "5.review" / "review.json").is_file()
    assert (entity_dir / "5.review" / "provenance.json").is_file()
    assert (entity_dir / "5.review" / "finalization_report.json").is_file()
    assert (entity_dir / "_object.json").is_file()
    mirror_dir = task_data(_TASK).entity_dir(_DOMAIN, _ETYPE, _NAME)
    assert (mirror_dir / "page.md").is_file()
    assert (mirror_dir / "_entity.json").is_file()
    assert (mirror_dir / "manifest.json").is_file()
    assert not (mirror_dir / "4.draft").exists()
    assert not (mirror_dir / "5.review").exists()


def test_validate_blocks_short_page():
    _seed_spec()
    _materialize_entity(["高原"], ["秋"], page_chars=50)
    issues = validate_entity_pages(_TASK, _BATCH, load_spec(_TASK))
    assert any(f"< {MIN_PAGE_CHARS}" in i for i in issues), issues


def test_validate_blocks_condition_profile_out_of_catalog():
    _seed_spec()
    _materialize_entity(["火星基地"], ["雾凇季"])
    issues = validate_entity_pages(_TASK, _BATCH, load_spec(_TASK))
    assert any("regions 越界" in i for i in issues), issues
    assert any("seasons 越界" in i for i in issues), issues


def test_validate_blocks_condition_profile_without_evidence_refs():
    _seed_spec()
    _materialize_entity(["高原"], ["秋"])
    entity_dir = batch_entity_object_dir(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME)
    payload = read_json(entity_dir / "_entity.json")
    payload["conditionProfile"].pop("evidenceRefs")
    write_json(entity_dir / "_entity.json", payload)
    issues = validate_entity_pages(_TASK, _BATCH, load_spec(_TASK))
    assert any("evidenceRefs" in i for i in issues), issues


def test_validate_passes_page_asset_closure():
    _seed_spec()
    _materialize_entity_with_asset()
    issues = validate_entity_pages(_TASK, _BATCH, load_spec(_TASK))
    assert issues == [], issues


def test_validate_blocks_dangling_page_asset():
    _seed_spec()
    _materialize_entity_with_asset()
    entity_dir = batch_entity_object_dir(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME)
    asset = read_json(entity_dir / "manifest.json")["assets"][0]
    (entity_dir / "assets" / asset["fileName"]).unlink()
    issues = validate_entity_pages(_TASK, _BATCH, load_spec(_TASK))
    assert any("asset file missing on disk" in i for i in issues), issues


def test_validate_blocks_engineering_template_pollution():
    _seed_spec()
    _materialize_entity(["高原"], ["秋"], page_chars=900)
    entity_dir = batch_entity_object_dir(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME)
    (entity_dir / "page.md").write_text(
        "# 稻城亚丁\n\n" + ("稻" * 900) + "\n\n## 为什么值得关注\n\n"
        "稻城亚丁 属于「地点/景区」实体，是内容冷启动、搜索承接、推荐召回和小艺主动服务都需要识别的基础节点。"
        "本页图片均来自同级 assets 目录，并在 manifest.json 中登记。\n",
        encoding="utf-8",
    )
    issues = validate_entity_pages(_TASK, _BATCH, load_spec(_TASK))
    assert any("engineering/template phrase" in i for i in issues), issues


def test_validate_blocks_repeated_padding_homepage():
    _seed_spec()
    _materialize_entity(["高原"], ["秋"], page_chars=900)
    entity_dir = batch_entity_object_dir(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME)
    repeated = "稻城亚丁是四川重要景区，山水与人文资源兼具，适合按季节规划行程。"
    (entity_dir / "page.md").write_text(
        "# 稻城亚丁\n\n"
        "先写一段正常概况。\n\n"
        f"{repeated}\n\n"
        f"{repeated}\n\n"
        f"{repeated}\n\n"
        f"{repeated}\n\n"
        "## 实用信息\n\n"
        "秋季更适合慢走，雨后石阶湿滑要小心。\n",
        encoding="utf-8",
    )
    issues = validate_entity_pages(_TASK, _BATCH, load_spec(_TASK))
    assert any("intraDocRepetition" in i for i in issues), issues


# 会话模型在底稿基础上轻改创作的实体主页正文（逐句改写、保留底稿枚举事实、≥800 字、不照搬）。
# 经 base_draft_similarity 实测对官方底稿贴合度约 0.91 ∈ [0.55, 0.995]，无模板指纹/质量门问题。
# AI 最小干扰协议：创作 agent 只写纯文字 + 多级标题，不书写 asset:// / :::figure；
# 封面与配图注入全部由 finalize 代码侧完成。
_AGENT_HOMEPAGE_DRAFT = (
    "# 稻城亚丁\n\n"
    "稻城亚丁位于四川省甘孜藏族自治州稻城县香格里拉镇，是川西高原上重要的自然景区。"
    "它以仙乃日、央迈勇、夏诺多吉三座雪山为核心景观，三座雪峰共同勾勒出稻城亚丁最具代表性的天际线。\n\n"
    "稻城亚丁景区包含高山湖泊、草甸、峡谷和藏族聚落等自然与人文资源，自然景观与人文线索在这里彼此交织。"
    "游客既能看到冰川融水汇成的高山湖泊，也能在草甸与峡谷之间体会高原独有的空间层次。\n\n"
    "前往稻城亚丁游览需要关注海拔、天气、步道和交通接驳等官方提示；"
    "高原环境下身体反应因人而异，合理安排节奏往往比一味赶点更重要。"
    "稻城亚丁的开放、预约和票务规则应以景区官方公告为准，临行前最好再次核对最新信息。\n\n"
    "认识稻城亚丁，可以从它的高原区位、雪山景观、高山湖泊、草甸和藏族文化几个角度切入，"
    "这些稳定信息共同构成了搜索、阅读与后续行程规划的基础，本页只整理实体本身可核验的事实。\n\n"
    "从空间结构看，仙乃日、央迈勇、夏诺多吉三座雪山与环绕其间的高山湖泊、草甸、峡谷，"
    "构成了稻城亚丁层次分明的自然骨架；藏族聚落散布在谷地与山坡之间，让核心景观之外多了人文厚度。"
    "无论是远观雪峰，还是沿步道靠近海子，都建议把海拔、天气和体力消耗一起纳入当天节奏判断。\n\n"
    "在不同区域之间转换时，路况、海拔与天气都可能发生明显变化，这也是高原景区游览体验的重要组成部分。"
    "稻城亚丁的草甸、峡谷与高山湖泊在不同光线下呈现出不同质感，停下来观察往往比快速穿行更能理解这片土地。\n\n"
    "对第一次到访的人来说，提前了解仙乃日、央迈勇、夏诺多吉三座雪山的相对位置，"
    "再结合官方公布的步道与交通接驳信息安排路线，会让整段行程更从容；"
    "遇到天气骤变时，及时调整目标、缩短在风口与湿滑路段的停留，比勉强完成既定计划更稳妥。\n\n"
    "此外，稻城亚丁的高山湖泊、草甸与峡谷分布在不同海拔层次上，"
    "沿途植被与景观随高度变化而过渡，构成了从谷地到雪线的完整自然序列；"
    "游览前结合季节、天气与自身体力做一次整体评估，再决定当天重点观赏哪一段，"
    "通常比把所有点位都塞进同一天更能保留稻城亚丁这片高原景观真正值得停留的体验。\n"
)


def test_finalize_materializes_agent_homepage_draft_with_generator_agent():
    _seed_spec()
    # P3：事实底稿与图片均来自 fact-ready 百科来源单元（实体主页主源只限百科）。
    _seed_homepage_source("cover.jpg")
    _seed_factready_encyclopedia_homepage_source("enc_cover.jpg")
    handle_build(argparse.Namespace(task=_TASK, batch=_BATCH, stage="prepare"))
    entity_dir = batch_entity_object_dir(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME)
    draft_page = _entity_draft_dir(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME) / "page.md"
    assert draft_page.is_file(), "prepare 应已下发占位 4.draft/page.md"
    # 会话模型在底稿基础上轻改创作，覆盖占位草稿。
    draft_page.write_text(_AGENT_HOMEPAGE_DRAFT, encoding="utf-8")
    issues = materialize_entity_pages(_TASK, _BATCH, load_spec(_TASK))
    assert issues == [], issues
    # finalize 产出真实 Agent 出处，而非脚本拼接伪装。
    manifest = read_json(entity_dir / "manifest.json")
    assert manifest["generator"] == "agent", manifest
    final_page = (entity_dir / "page.md").read_text(encoding="utf-8")
    assert "稻城亚丁位于四川省甘孜藏族自治州稻城县香格里拉镇" in final_page
    assert manifest["assets"]
    assert manifest["assets"][0]["role"] == "cover"
    # 三段结构契约：封面只在 frontmatter 声明，正文不重复展示封面（Agent 内联的
    # 封面 figure 由 finalize 代码侧剥离）；仅有封面一张图时正文无 figure 属合法形态。
    cover_asset_id = manifest["assets"][0]["assetId"]
    assert final_page.startswith("---\n"), final_page[:80]
    assert f"coverImage: asset://{cover_asset_id}" in final_page
    body = final_page.split("\n---\n", 1)[1]
    assert f"asset://{cover_asset_id}" not in body, "封面不得在正文重复展示"
    validate_issues = validate_entity_pages(_TASK, _BATCH, load_spec(_TASK))
    assert validate_issues == [], validate_issues


def test_finalize_folds_traditional_homepage_text_to_simplified():
    _seed_spec()
    _seed_homepage_source("cover.jpg")
    _seed_factready_encyclopedia_homepage_source("enc_cover.jpg")
    handle_build(argparse.Namespace(task=_TASK, batch=_BATCH, stage="prepare"))
    entity_dir = batch_entity_object_dir(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME)
    draft_page = _entity_draft_dir(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME) / "page.md"
    draft_page.write_text(
        _AGENT_HOMEPAGE_DRAFT
        + "\n\n山區雲霧會隨季節變化，遊覽時經龍門一線也應留意天氣。\n",
        encoding="utf-8",
    )

    issues = materialize_entity_pages(_TASK, _BATCH, load_spec(_TASK))

    assert issues == [], issues
    final_page = (entity_dir / "page.md").read_text(encoding="utf-8")
    assert "山区云雾会随季节变化" in final_page
    assert not has_traditional_chars(final_page)
    validate_issues = validate_entity_pages(_TASK, _BATCH, load_spec(_TASK))
    assert validate_issues == [], validate_issues


def test_validate_homepage_fidelity_folds_traditional_base_text():
    _seed_spec()
    _seed_homepage_source("cover.jpg")
    source_ref = _seed_factready_encyclopedia_homepage_source("enc_cover.jpg")
    source_path = batch_root(_TASK, _BATCH) / source_ref
    source_dir = source_path.parent
    original_source = (source_dir / "source.md").read_text(encoding="utf-8")
    clean_path = source_dir / "source.clean.md"
    original_clean = clean_path.read_text(encoding="utf-8") if clean_path.is_file() else None
    traditional_base = (
        "# 稻城亚丁\n\n"
        "稻城亚丁位於四川省甘孜藏族自治州稻城縣香格里拉鎮。"
        "稻城亚丁以仙乃日、央邁勇、夏諾多吉三座雪山為核心景觀。"
        "稻城亚丁景區包含高山湖泊、草甸、峽谷和藏族聚落等自然與人文資源。"
        "稻城亚丁遊覽需要關注海拔、天氣、步道和交通接駁等官方提示。"
        "稻城亚丁的開放、預約和票務規則應以景區官方公告為準。"
    )
    try:
        (source_dir / "source.md").write_text(traditional_base, encoding="utf-8")
        (source_dir / "source.clean.md").write_text(traditional_base, encoding="utf-8")
        handle_build(argparse.Namespace(task=_TASK, batch=_BATCH, stage="prepare"))
        draft_page = _entity_draft_dir(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME) / "page.md"
        draft_page.write_text(_AGENT_HOMEPAGE_DRAFT, encoding="utf-8")

        issues = materialize_entity_pages(_TASK, _BATCH, load_spec(_TASK))

        assert issues == [], issues
        validate_issues = validate_entity_pages(_TASK, _BATCH, load_spec(_TASK))
        assert validate_issues == [], validate_issues
    finally:
        (source_dir / "source.md").write_text(original_source, encoding="utf-8")
        if original_clean is None:
            clean_path.unlink(missing_ok=True)
        else:
            clean_path.write_text(original_clean, encoding="utf-8")


def test_finalize_waits_when_agent_draft_is_placeholder():
    _seed_spec()
    _seed_homepage_source("cover.jpg")
    _seed_factready_encyclopedia_homepage_source("enc_cover.jpg")
    handle_build(argparse.Namespace(task=_TASK, batch=_BATCH, stage="prepare"))
    # 不写回正文：占位草稿应让 finalize 返回等待项，绝不退回脚本拼接。
    issues = materialize_entity_pages(_TASK, _BATCH, load_spec(_TASK))
    assert any("4.draft/page.md" in i for i in issues), issues
    entity_dir = batch_entity_object_dir(_TASK, _BATCH, _DOMAIN, _ETYPE, _NAME)
    assert not (entity_dir / "page.md").is_file(), "占位态不得物化成品 page.md"


def test_homepage_fact_split_filters_official_ui_copy():
    facts = _split_fact_sentences(
        "您好，欢迎访问蜀南竹海旅游度假区景区官方网站！"
        "蜀南竹海景区全年开放，部分体验性产品开放时间以实际为准。",
        entity_name="蜀南竹海",
    )
    assert facts == ["蜀南竹海景区全年开放，部分体验性产品开放时间以实际为准。"]


def test_homepage_fact_split_accepts_encyclopedia_alias_and_structural_facts():
    facts = _split_fact_sentences(
        "八达岭是位于北京市延庆区内临近居庸关的一个山峰，最高点1,015米。"
        "地处于北京西北。"
        "八达岭最著名的是它的长城。"
        "它是中国开放最早的一段长城，也是至今为止保护最好，最著名的一段明代长城。"
        "其可行部分全长3,741米。"
        "它建于1504年，关城有东西二门。",
        entity_name="八达岭—慕田峪长城旅游区",
    )
    assert len(facts) >= 4
    assert any("最高点1,015米" in fact for fact in facts)
    assert any("全长3,741米" in fact for fact in facts)
    assert any("建于1504年" in fact for fact in facts)


def test_homepage_fact_split_counts_broken_official_intro_clauses():
    facts = _split_fact_sentences(
        "沙湖风光-宁夏沙湖旅游官方网站 国家AAAAA级景区 中文 English 首页 沙湖风光 玩转沙湖 "
        "沙湖概况 宁夏沙 湖，国家5A级景区和中国十大魅力 湿地、宁夏新十景之一，"
        "镶嵌在贺兰山 下、黄河金岸，距宁夏回族自治区首府银 川市42公里，"
        "景区总面积为80.10平方公 里，22.52平方公里的沙漠与45平方公 里的水域毗邻而居，"
        "融合江南水乡之灵秀与塞北大漠之雄浑为一体。",
        entity_name="沙湖旅游景区",
    )
    assert len(facts) >= 4
    assert any("国家5A级景区" in fact for fact in facts)
    assert any("42公里" in fact for fact in facts)
    assert any("80.10平方公里" in fact for fact in facts)
    assert any("22.52平方公里" in fact and "45平方公里" in fact for fact in facts)


def test_homepage_fact_split_accepts_short_alias_in_packed_wiki_paragraph():
    facts = _split_fact_sentences(
        "云龙湖，位于徐州南部，史称“石狗湖”，原为一低洼之地。"
        "后为解决水患将其扩建成水库，因位于云龙山脚下而得名，是江苏省级风景名胜区。"
        "波光浩渺，三面青山，景区内风光如画，文物古迹众多，旅游资源丰富，其中包括考古发现的“汉画像石”。"
        "湖南面部分地区曾有莲藕种植和鱼类养殖业，现已逐步改造成为风景区。"
        "2016年8月云龙湖风景区被授予国家AAAAA级景区。"
        "== 外部链接 == 徐州云龙湖旅游景区 （页面存档备份，存于互联网档案馆）",
        entity_name="云龙湖景区",
    )
    assert len(facts) >= 4
    assert any("云龙湖，位于徐州南部" in fact for fact in facts)
    assert any("扩建成水库" in fact for fact in facts)
    assert not any("外部链接" in fact for fact in facts)


def test_homepage_fact_split_rejects_official_json_api_payload():
    facts = _split_fact_sentences(
        '{"code":200,"msg":"操作成功","data":[{"newsId":"1","newsName":"长影世纪城国庆假日省歌强势助阵",'
        '"newsContext":"详情请咨询游客服务中心","sightId":"2","sightName":"银河宫","sightDescription":"游客可现场体验"}]}',
        entity_name="长影世纪城景区",
    )
    assert facts == []


def test_homepage_fact_split_counts_official_meta_level_titles():
    facts = _split_fact_sentences(
        "金华双龙风景旅游区位于浙江省金华市北郊的金华山麓，"
        "是国家首批AAAA级旅游景区、国家级风景名胜区和国家森林公园。"
        "有双龙洞、黄大仙、尖峰山、大盘天、赤松山、家园里六大景区。",
        entity_name="双龙风景旅游区",
    )
    assert len(facts) >= 4
    assert any("位于浙江省金华市北郊" in fact for fact in facts)
    assert any("AAAA级旅游景区" in fact for fact in facts)
    assert any("国家级风景名胜区" in fact for fact in facts)
    assert any("六大景区" in fact for fact in facts)


def test_homepage_tag_refs_merge_master_list_type_and_geo_tags():
    """WP3 统一打标：typeTagRefs + geoTagRef/geoTagRefs 全量并进 tagRefs（不编造）。"""
    from build.homepage import _homepage_tag_refs

    payload = {
        "typeTagRefs": ["Entity/地点/景区/4A景区", "Entity/地点/博物馆"],
        "geoTagRef": "Topic/地理/行政区/中国/四川省/成都市/武侯区",
        "geoTagRefs": ["Topic/地理/行政区/中国/四川省/成都市/武侯区"],
        "tagRefs": ["Topic/旅行/玩法/观光游览"],
    }
    refs = _homepage_tag_refs(_DOMAIN, _ETYPE, "武侯祠", payload)

    assert refs[:3] == [
        "Entity/地点/景区/4A景区",
        "Entity/地点/博物馆",
        "Topic/地理/行政区/中国/四川省/成都市/武侯区",
    ]
    assert "Topic/旅行/玩法/观光游览" in refs
    # geoTagRef 与 geoTagRefs 重复项去重，只出现一次。
    assert refs.count("Topic/地理/行政区/中国/四川省/成都市/武侯区") == 1
    # Format 最小集兜底仍在（manifest.tagRefs >= 2 合法 ref 契约）。
    assert any(ref.startswith("Format/") for ref in refs)


def test_homepage_tag_refs_do_not_fabricate_when_master_list_fields_missing():
    from build.homepage import _homepage_tag_refs

    refs = _homepage_tag_refs(_DOMAIN, _ETYPE, "无契约字段景区", {})

    assert not any(ref.startswith("Entity/") for ref in refs)
    assert not any(ref.startswith("Topic/地理/") for ref in refs)
    # Topic/Format 最小集兜底仍保证非空。
    assert len(refs) == 2


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"build homepage tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
