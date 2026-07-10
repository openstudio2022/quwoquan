"""目录与资产证据链静态门 + 文风门 契约 (T1)。

可直接运行：python3 quwoquan_data/tests/local_contract/verify/test_directory_evidence_gate__local_contract_test.py
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
from unittest.mock import patch

sys.path.insert(0, str(SCRIPTS_ROOT))

os.environ["QWQ_RUNTIME_ROOT"] = tempfile.mkdtemp()

from _common.batch_asset_registry import BatchAssetRegistry, allocate_post_asset_id  # noqa: E402
from _common.batch_manifest import load_batch_manifest, write_batch_manifest  # noqa: E402
from _common.content_object import content_object_dir, register_content_object  # noqa: E402
from _common.entity_object import sync_entity_object_to_task_mirror, write_entity_object_index  # noqa: E402
from _common.article_package import compute_document_sha256, sha256_text  # noqa: E402
from _common.io import write_json  # noqa: E402
from _common.paths import (  # noqa: E402
    batch_entity_object_dir,
    batch_post_object_dir,
    batch_root,
    ensure_task_layout,
    task_root,
    task_shared_dir,
)
from _common.prose_style import mechanical_ending_title_issues  # noqa: E402
from _common.source_unit import write_source_unit  # noqa: E402
from build.homepage import materialize_entity_pages, validate_entity_pages  # noqa: E402
from task import ops  # noqa: E402
from verify.verify_directory_evidence_chain import scan_batch, scan_task  # noqa: E402

TASK = "旅行/地域/四川省/景区/景区全覆盖"


def _seed_batch_manifest(batch: str, *, content_type: str = "") -> None:
    write_batch_manifest(TASK, batch, command="task_run", content_type=content_type)


def _seed_homepage_spec(name: str) -> dict:
    return {
        "schemaVersion": "quwoquan.task.spec",
        "taskId": TASK,
        "scope": {"coverageTargets": [{"entityType": "地点/景区", "name": name}]},
    }


def _seed_entity_review_sidecars(
    ent: Path,
    *,
    batch: str,
    source_refs: list[str],
    writing_pack: str = "fixture homepage writing pack",
) -> None:
    draft_dir = ent / "4.draft"
    draft_dir.mkdir(parents=True, exist_ok=True)
    draft_path = draft_dir / "page.md"
    final_path = ent / "page.md"
    if not draft_path.is_file() and final_path.is_file():
        draft_path.write_text(final_path.read_text(encoding="utf-8"), encoding="utf-8")
    review_dir = ent / "5.review"
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
            "agentInput": {"writingPack": writing_pack},
            "final": {"generator": "agent"},
        },
    )
    write_json(
        review_dir / "finalization_report.json",
        {
            "schemaVersion": "quwoquan_data.finalization_report",
            "draftArticleRef": "4.draft/page.md",
            "finalArticleRef": "page.md",
            "draftSha256": compute_document_sha256(draft_path.read_text(encoding="utf-8")),
            "finalSha256": compute_document_sha256(final_path.read_text(encoding="utf-8")),
        },
    )
    write_entity_object_index(TASK, batch, "地点", "景区", ent.name)
    sync_entity_object_to_task_mirror(TASK, batch, "地点", "景区", ent.name)


def test_mechanical_title_detected_and_natural_ok():
    bad = "# 海螺沟\n\n正文\n\n## 它到底适合谁\n\n收尾。"
    assert mechanical_ending_title_issues(bad), "应识别机械收尾标题"
    good = "# 海螺沟\n\n正文\n\n## 出发前要确认的事\n\n值不值得专程跑一趟，于我是值的。"
    assert not mechanical_ending_title_issues(good)


def test_gate_flags_loose_images():
    batch = "gate_loose"
    _seed_batch_manifest(batch)
    ensure_task_layout(TASK)
    obj = batch_entity_object_dir(TASK, batch, "地点", "景区", "海螺沟")
    (obj / "images").mkdir(parents=True, exist_ok=True)
    (obj / "images" / "img_01.jpg").write_bytes(b"\xff\xd8\xff\x00data")
    write_json(obj / "_entity.json", {"label": "海螺沟", "domain": "地点", "type": "景区"})
    issues = scan_batch(TASK, batch, require_stage_tree=False)
    assert any("散落 images/" in i for i in issues), issues


def test_gate_flags_absolute_path_and_mechanical_and_weather():
    batch = "gate_abs"
    _seed_batch_manifest(batch)
    ensure_task_layout(TASK)
    post = batch_post_object_dir(TASK, batch, "article", "环线", "海螺沟两天", 1)
    post.mkdir(parents=True, exist_ok=True)
    (post / "article.md").write_text("# 海螺沟\n\n正文\n\n## 适合谁\n\n收尾", encoding="utf-8")
    write_json(
        post / "manifest.json",
        {
            "topicId": "海螺沟两天",
            "assets": [],
            "citedSourceRefs": ["/Users/x/quwoquan/.../source.md"],
        },
    )
    # 无类别 weather_* 来源单元
    ent = batch_entity_object_dir(TASK, batch, "地点", "景区", "九寨沟")
    write_source_unit(
        ent,
        ordinal=1,
        source_id="weather_jzg",
        source_md="天气数据",
        platform="web",
        source_category="web",
        url="https://weather",
        title="天气",
        target_ref="/entity/地点/景区/九寨沟",
    )
    issues = scan_batch(TASK, batch, require_stage_tree=False)
    assert any("绝对路径" in i for i in issues), issues
    assert any("机械收尾标题" in i for i in issues), issues
    assert any("天气类来源" in i for i in issues), issues


def test_gate_passes_clean_object():
    batch = "gate_clean"
    _seed_batch_manifest(batch)
    ensure_task_layout(TASK)
    ent = batch_entity_object_dir(TASK, batch, "地点", "景区", "峨眉山")
    global_seq = int(load_batch_manifest(TASK, batch)["globalBatchSeq"])
    registry = BatchAssetRegistry(task_id=TASK, batch_id=batch, global_batch_seq=global_seq)
    source_manifest = write_source_unit(
        ent,
        ordinal=1,
        source_id="overview_baike",
        source_md="# 峨眉山\n\n概述",
        platform="维基百科",
        source_category="encyclopedia",
        url="https://zh.wikipedia.org/wiki/峨眉山",
        title="峨眉山（百科）",
        target_ref="/entity/地点/景区/峨眉山",
        images=[
            {
                "bytes": b"cover",
                "ext": ".jpg",
                "slug": "cover",
                "license": "CC-BY-SA 4.0",
                "termsUrl": "https://zh.wikipedia.org/wiki/Wikipedia:CC",
                "caption": "峨眉山云海",
            }
        ],
        build_variants=False,
    )
    source_ref = str(source_manifest["sourceRef"])
    source_unit_ref = str(source_manifest["sourceUnitRef"])
    source_asset_ref = f"{source_unit_ref}/assets/001_cover.jpg"
    write_json(
        ent / "_entity.json",
        {
            "label": "峨眉山",
            "domain": "地点",
            "type": "景区",
            "sourceTaskId": TASK,
            "geoTagRef": "Topic/地理/行政区/中国/四川省/乐山市/峨眉山市",
        },
    )
    paragraphs = [
        "峨眉山的核心体验不只在登顶本身，还在沿途寺院、林间坡道与观景停顿组成的节奏感里。",
        "如果把路线拆成山脚适应、半山停留、重点视角和返程收束四段，行程会更稳定，也更容易控制体力。",
        "清晨上山通常能换来更安静的石阶与更柔和的光线，适合把主要观景与拍摄时段放在前半天。",
        "午后云雾和游客流量都可能增加，因此需要提前决定是继续上探，还是把重点转回文化参观点。",
        "寺院密集区适合慢走阅读空间关系，不建议把它当作简单打卡点，否则会错过整条路径的层次变化。",
        "遇到临时天气变化时，最重要的是及时缩短暴露在风口与湿滑路段的时间，而不是勉强完成既定线路。",
        "如果同行者步速差异较大，可以提前约定几个会合节点，避免在长坡或岔路附近频繁等待造成节奏打断。",
        "索道、步道与观景台之间的切换最好在出发前做一轮优先级排序，这样当天临场调整时会更从容。",
        "对第一次前往的人来说，保留一定机动时间比塞满点位更重要，因为山地体验的价值常来自停下来观察。",
        "真正让人记住峨眉山的，往往不是某一个单点风景，而是山路、植被、古建与天气共同形成的连续感受。",
        "从体验完整性看，山脚交通衔接、半山补给选择、上行节奏控制和返程窗口判断，其实同样决定这次访问是否顺畅。",
        "若计划在一天内完成主要目标，建议把最耗体力的路段尽量前置，把留影、休整和临场决策放到更容易调整的后段。",
        "很多人低估了山地路线里的停顿价值，适当的停顿不仅帮助恢复体力，也能让视线和观察重点从赶路切回体验本身。",
        "当路线穿过树荫、台阶、平台和建筑边界时，环境变化会非常明显，这些变化本身就是行程叙事的重要组成部分。",
        "如果是第一次为别人规划峨眉山路线，最稳妥的方法往往不是堆更多点位，而是明确每一段为什么值得停、停多久、何时转场。",
        "把观察、停顿和转场都纳入计划之后，路线会从单纯抵达目标，变成一条更完整、也更容易复盘的体验曲线。",
    ]
    asset_id = allocate_post_asset_id(
        entity_name="峨眉山",
        role="cover",
        ref="峨眉山_主页",
        global_batch_seq=global_seq,
        registry=registry,
    )
    (ent / "page.md").write_text(
        "---\n"
        f"coverImage: asset://{asset_id}\n"
        "---\n"
        "# 峨眉山\n\n"
        "## 概况\n\n"
        + "\n\n".join(paragraphs[:5])
        + "\n\n## 路线节奏\n\n"
        + "\n\n".join(paragraphs[5:11])
        + "\n\n## 出发前\n\n"
        + "\n\n".join(paragraphs[11:])
        + "\n",
        encoding="utf-8",
    )
    write_json(
        ent / "2.quality" / "quality_analysis.json",
        {
            "schemaVersion": "quwoquan.entity.quality_analysis",
            "baseDraft": {"sourceRef": source_ref},
            "recommendation": "proceed",
            "sourcePaths": [source_ref],
            "selectedBaseSourceRef": source_ref,
            "selectedSourceRefs": [source_ref],
            "selectionReason": "百科概述覆盖基础事实，作为主页底稿来源。",
        },
    )
    write_json(
        ent / "manifest.json",
        {
            "generator": "agent",
            "assets": [
                {
                    "assetId": asset_id,
                    "fileName": f"{asset_id}.jpg",
                    "role": "cover",
                    "caption": "峨眉山云海",
                    "sourceRef": source_ref,
                    "sourceAssetRef": source_asset_ref,
                    "termsUrl": "https://zh.wikipedia.org/wiki/Wikipedia:CC",
                }
            ],
            "citedSourceRefs": [source_ref],
        },
    )
    (ent / "assets").mkdir(parents=True, exist_ok=True)
    (ent / "assets" / f"{asset_id}.jpg").write_bytes(b"cover")
    _seed_entity_review_sidecars(ent, batch=batch, source_refs=[source_ref])
    write_json(ent / "3.compose" / "entity_page_input.json", {"payload": {"name": "峨眉山"}})
    issues = validate_entity_pages(TASK, batch, _seed_homepage_spec("峨眉山"))
    assert not issues, issues
    issues = scan_batch(TASK, batch)
    assert not issues, issues


def test_gate_entity_homepage_writes_review_sidecars():
    batch = "gate_entity_review"
    _seed_batch_manifest(batch)
    ensure_task_layout(TASK)
    ent = batch_entity_object_dir(TASK, batch, "地点", "景区", "都江堰")
    global_seq = int(load_batch_manifest(TASK, batch)["globalBatchSeq"])
    registry = BatchAssetRegistry(task_id=TASK, batch_id=batch, global_batch_seq=global_seq)
    write_source_unit(
        ent,
        ordinal=1,
        source_id="overview_baike",
        source_md="# 都江堰\n\n概述",
        clean_md="# 都江堰\n\n概述",
        platform="维基百科",
        source_category="encyclopedia",
        url="https://example.com/djy",
        title="都江堰百科",
        target_ref="/entity/地点/景区/都江堰",
    )
    write_json(
        ent / "_entity.json",
        {
            "label": "都江堰",
            "domain": "地点",
            "type": "景区",
            "sourceTaskId": TASK,
            "geoTagRef": "Topic/地理/行政区/中国/四川省/成都市/都江堰市",
        },
    )
    asset_id = allocate_post_asset_id(
        entity_name="都江堰",
        role="cover",
        ref="都江堰_主页",
        global_batch_seq=global_seq,
        registry=registry,
    )
    base_sections = [
        "都江堰位于成都平原西部，核心看点是延续至今的古代水利工程体系。",
        "理解这处景区，重点不只在分水鱼嘴本身，也在河道、山势与城市关系如何一起展开。",
        "第一次到访时，适合先用步行把几处关键观察点串起来，再决定是否补充更长的停留路线。",
        "沿着堤岸走到安澜索桥附近，可以同时看到分水、泄洪与引水三段结构如何衔接。",
        "如果只想抓住主线，可以把注意力集中在工程逻辑、观景停顿和沿线解说的衔接上。",
        "丰水期和枯水期的视觉感受差异明显，出发前最好先确认当天水位与步道开放信息。",
        "离堆公园一侧的步道相对平缓，带老人和孩子同行时可以优先从这里开始游览。",
        "把节奏放慢之后，更容易看清它为什么既是工程遗产，也是今天仍在运转的城市基础设施。",
    ]
    page_text = (
        "# 都江堰\n\n## 概况\n\n"
        + "\n\n".join(base_sections[:4])
        + "\n\n## 现场观察\n\n"
        + "\n\n".join(base_sections[4:])
    )
    (ent / "page.md").write_text(page_text, encoding="utf-8")
    (ent / "assets").mkdir(parents=True, exist_ok=True)
    (ent / "assets" / f"{asset_id}.jpg").write_bytes(b"cover")
    homepage_source_manifest = write_source_unit(
        ent,
        ordinal=2,
        source_id="baike_overview",
        source_md="# 都江堰\n\n百科概述",
        clean_md="# 都江堰\n\n百科概述",
        platform="百度百科",
        source_category="encyclopedia",
        research_lane="homepage",
        url="https://baike.example.com/djy",
        title="都江堰百科",
        target_ref="/entity/地点/景区/都江堰",
        images=[
            {
                "bytes": b"cover",
                "ext": ".jpg",
                "slug": "cover",
                "license": "fixture-license",
                "termsUrl": "https://baike.example.com/license",
                "caption": "水利工程",
            }
        ],
        build_variants=False,
    )
    homepage_source_ref = str(homepage_source_manifest["sourceRef"])
    homepage_source_asset_ref = f"{homepage_source_manifest['sourceUnitRef']}/assets/001_cover.jpg"
    write_json(
        ent / "2.quality" / "quality_analysis.json",
        {
            "entityRef": "/entity/地点/景区/都江堰",
            "baseDraft": {"sourceRef": homepage_source_ref},
            "candidateCount": 1,
            "candidates": [],
            "recommendation": "proceed",
            "issues": [],
            "sourcePaths": [homepage_source_ref],
        },
    )
    write_json(
        ent / "manifest.json",
        {
            "generator": "agent",
            "assets": [
                {
                    "assetId": asset_id,
                    "fileName": f"{asset_id}.jpg",
                    "role": "cover",
                    "caption": "水利工程",
                    "sourceRef": homepage_source_ref,
                    "sourceAssetRef": homepage_source_asset_ref,
                    "termsUrl": "https://baike.example.com/license",
                }
            ]
        },
    )
    write_json(
        ent / "3.compose" / "entity_page_input.json",
        {
            "payload": {
                "name": "都江堰",
                # discovery_seed/2 起 geoTagRef 为物化必填，经 prepare payload 透传写入 _entity.json。
                "geoTagRef": "Topic/地理/行政区/中国/四川省/成都市/都江堰市",
                "baseDraft": {
                        "text": "\n".join(
                            base_sections
                            + [
                                "遇到游客高峰时，先把桥面和观景台的人流节点避开，整体体验会稳定很多。",
                                "若想把工程原理看得更清楚，最好结合现场指示牌与河道走向一起理解。",
                            ]
                        ),
                    "sourceRef": homepage_source_ref,
                    "primaryEvidenceRef": homepage_source_ref,
                    "sourceUseMode": "factual_reference_only",
                    "sectionOutline": [],
                },
            }
        },
    )
    (ent / "4.draft").mkdir(parents=True, exist_ok=True)
    (ent / "4.draft" / "page.md").write_text(page_text, encoding="utf-8")
    with patch(
        "build.homepage._pick_homepage_assets",
        return_value=[
            {
                "path": batch_root(TASK, batch) / homepage_source_asset_ref,
                "sourceRef": homepage_source_ref,
                "sourceAssetRef": homepage_source_asset_ref,
                "termsUrl": "https://baike.example.com/license",
                "authorizationProof": "fixture homepage asset rights",
                "caption": "水利工程",
                "sha256": "fixture-homepage-asset-sha",
            }
        ],
    ):
        materialize_issues = materialize_entity_pages(TASK, batch, _seed_homepage_spec("都江堰"))
    assert not materialize_issues, materialize_issues
    issues = validate_entity_pages(TASK, batch, _seed_homepage_spec("都江堰"))
    assert not issues, issues
    assert (ent / "5.review" / "review.json").is_file()
    assert (ent / "5.review" / "provenance.json").is_file()
    assert (ent / "5.review" / "finalization_report.json").is_file()


def test_gate_flags_missing_entity_review_sidecars():
    batch = "gate_entity_sidecar_missing"
    _seed_batch_manifest(batch)
    ensure_task_layout(TASK)
    ent = batch_entity_object_dir(TASK, batch, "地点", "景区", "都江堰")
    global_seq = int(load_batch_manifest(TASK, batch)["globalBatchSeq"])
    registry = BatchAssetRegistry(task_id=TASK, batch_id=batch, global_batch_seq=global_seq)
    source_manifest = write_source_unit(
        ent,
        ordinal=1,
        source_id="overview_baike",
        source_md="# 都江堰\n\n概述",
        clean_md="# 都江堰\n\n概述",
        platform="维基百科",
        source_category="encyclopedia",
        url="https://example.com/djy",
        title="都江堰百科",
        target_ref="/entity/地点/景区/都江堰",
    )
    source_ref = str(source_manifest["sourceRef"])
    write_json(
        ent / "_entity.json",
        {
            "label": "都江堰",
            "domain": "地点",
            "type": "景区",
            "sourceTaskId": TASK,
            "geoTagRef": "Topic/地理/行政区/中国/四川省/成都市/都江堰市",
        },
    )
    asset_id = allocate_post_asset_id(
        entity_name="都江堰",
        role="cover",
        ref="都江堰_主页",
        global_batch_seq=global_seq,
        registry=registry,
    )
    (ent / "page.md").write_text(
        f"# 都江堰\n\n" + ("都" * 900) + f"\n\n{{asset://{asset_id}|wrapRight|水利工程|width=45%}}\n",
        encoding="utf-8",
    )
    (ent / "assets").mkdir(parents=True, exist_ok=True)
    (ent / "assets" / f"{asset_id}.jpg").write_bytes(b"cover")
    write_json(ent / "manifest.json", {"assets": [{"assetId": asset_id, "fileName": f"{asset_id}.jpg", "caption": "水利工程"}]})
    (ent / "2.quality").mkdir(parents=True, exist_ok=True)
    write_json(
        ent / "2.quality" / "quality_analysis.json",
        {
            "entityRef": "/entity/地点/景区/都江堰",
            "baseDraft": {"sourceRef": source_ref},
            "candidateCount": 1,
            "candidates": [],
            "recommendation": "proceed",
            "issues": [],
            "sourcePaths": [source_ref],
        },
    )
    # 故意不写 4.draft/page.md 与 5.review/*.json，让静态门直接报红。
    issues = scan_batch(TASK, batch)
    assert any("4.draft/page.md" in i for i in issues), issues
    assert any("5.review/review.json" in i for i in issues), issues
    assert any("5.review/provenance.json" in i for i in issues), issues
    assert any("5.review/finalization_report.json" in i for i in issues), issues


def test_gate_flags_stage_first_regression():
    batch = "gate_regress"
    _seed_batch_manifest(batch)
    ensure_task_layout(TASK)
    # M3/M4 已迁对象根的 compose 报告被回写到 task_produce/results/compose → 必须 BLOCK。
    d = batch_root(TASK, batch) / "task_produce" / "results" / "compose"
    d.mkdir(parents=True, exist_ok=True)
    write_json(d / "九寨沟.json", {"payload": {"generator": "agent"}})
    issues = scan_batch(TASK, batch, require_stage_tree=False)
    assert any("stage-first 回退" in i for i in issues), issues


def test_gate_flags_legacy_hash_source_unit_dir_and_accepts_readable():
    """命名门（spec §3）：批次 sources/ 必须用 {实体名}__{sourceKind}__{hash8}，su_ 哈希名 BLOCK。"""
    batch = "gate_src_naming"
    _seed_batch_manifest(batch)
    ensure_task_layout(TASK)
    sources_root = batch_root(TASK, batch) / "sources"
    (sources_root / "su_eabdce24810af4b94427").mkdir(parents=True, exist_ok=True)
    (sources_root / "黄龙风景名胜区__home_wikipedia__ab12cd34").mkdir(parents=True, exist_ok=True)
    (sources_root / "随意目录名").mkdir(parents=True, exist_ok=True)
    issues = scan_batch(TASK, batch, require_stage_tree=False)
    assert any("su_eabdce24810af4b94427" in i and "已废弃" in i for i in issues), issues
    assert any("随意目录名" in i and "可读命名" in i for i in issues), issues
    assert not any("黄龙风景名胜区__home_wikipedia__ab12cd34" in i for i in issues), issues


def test_gate_flags_legacy_v1_asset_names_and_accepts_v2():
    """assets 命名门（spec §4.1）：成品图片文件名必须是 v2 assetId（含图注段）。

    - v2 `实体_角色_图注_批次号_hash8` → PASS
    - v1 `实体_角色_批次号_hash8`（无图注段）→ BLOCK
    - 不可解析的任意文件名 → BLOCK
    """
    batch = "gate_asset_naming"
    _seed_batch_manifest(batch)
    ensure_task_layout(TASK)
    ent = batch_entity_object_dir(TASK, batch, "地点", "景区", "黄龙")
    assets_dir = ent / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    # 对象根判定依赖 _entity.json（iter_batch_object_dirs）。
    write_json(ent / "_entity.json", {"label": "黄龙", "domain": "地点", "type": "景区"})
    (assets_dir / "黄龙_cover_五彩池_42_a1b2c3d4.jpg").write_bytes(b"v2")
    (assets_dir / "黄龙_cover_42_a1b2c3d4.jpg").write_bytes(b"v1")
    (assets_dir / "random_name.jpg").write_bytes(b"junk")
    issues = scan_batch(TASK, batch, require_stage_tree=False)
    assert any("黄龙_cover_42_a1b2c3d4.jpg" in i and "缺图注段" in i for i in issues), issues
    assert any("random_name.jpg" in i and "不可解析" in i for i in issues), issues
    assert not any("黄龙_cover_五彩池_42_a1b2c3d4.jpg" in i for i in issues), issues


def test_source_unit_id_readable_naming_contract():
    """sourceUnitId 可读命名：实体语境产 {实体名}__{kind}__{hash8}；无语境回退 su_ 哈希。"""
    import re

    import _common.ops_governance as og

    readable = og.source_unit_id(
        canonical_url="https://zh.wikipedia.org/wiki/黄龙风景名胜区",
        snapshot_hash="sha256:abc",
        source_ref="01.home_wikipedia",
        entity_name="黄龙风景名胜区",
        source_kind="home_wikipedia",
    )
    assert re.match(r"^黄龙风景名胜区__home_wikipedia__[0-9a-f]{8}$", readable), readable
    # 同输入稳定可复算。
    assert readable == og.source_unit_id(
        canonical_url="https://zh.wikipedia.org/wiki/黄龙风景名胜区",
        snapshot_hash="sha256:abc",
        source_ref="01.home_wikipedia",
        entity_name="黄龙风景名胜区",
        source_kind="home_wikipedia",
    )
    legacy = og.source_unit_id(source_ref="sources/x/source.md")
    assert re.match(r"^su_[0-9a-f]{20}$", legacy), legacy


def test_batch_source_unit_dir_preserves_chinese_entity_name():
    from _common.paths import batch_source_unit_dir

    unit = batch_source_unit_dir(TASK, "gate_src_naming2", "黄龙风景名胜区__home_wikipedia__ab12cd34")
    assert unit.name == "黄龙风景名胜区__home_wikipedia__ab12cd34"


def test_gate_flags_illegal_top_level_entry():
    batch = "gate_toplevel"
    _seed_batch_manifest(batch)
    ensure_task_layout(TASK)
    b = batch_root(TASK, batch)
    b.mkdir(parents=True, exist_ok=True)
    # 旧 produce_trace.json 散在批次顶层 → 顶层结构门拦截。
    (b / "produce_trace.json").write_text("{}", encoding="utf-8")
    issues = scan_batch(TASK, batch, require_stage_tree=False)
    assert any("非法批次顶层条目" in i for i in issues), issues


def test_gate_flags_illegal_object_child_dir():
    batch = "gate_naming"
    _seed_batch_manifest(batch)
    ensure_task_layout(TASK)
    ent = batch_entity_object_dir(TASK, batch, "地点", "景区", "贡嘎")
    (ent / "weird_stage").mkdir(parents=True, exist_ok=True)
    write_json(ent / "_entity.json", {"label": "贡嘎", "domain": "地点", "type": "景区"})
    issues = scan_batch(TASK, batch, require_stage_tree=False)
    assert any("非法对象子目录" in i for i in issues), issues


def test_gate_flags_dual_scenic_location_entity_trees():
    batch = "gate_dual_scenic_types"
    _seed_batch_manifest(batch)
    ensure_task_layout(TASK)
    scenic = batch_entity_object_dir(TASK, batch, "地点", "景区", "都江堰")
    scenic.mkdir(parents=True, exist_ok=True)
    write_json(scenic / "_entity.json", {"label": "都江堰", "domain": "地点", "type": "景区"})
    spot = batch_entity_object_dir(TASK, batch, "地点", "打卡地", "都江堰")
    spot.mkdir(parents=True, exist_ok=True)
    write_json(spot / "_entity.json", {"label": "都江堰", "domain": "地点", "type": "打卡地"})
    issues = scan_batch(TASK, batch, require_stage_tree=False)
    assert any("dual scenic-location trees" in i for i in issues), issues


def test_gate_flags_unregistered_post_object_drift():
    batch = "gate_drift"
    _seed_batch_manifest(batch)
    ensure_task_layout(TASK)
    # 未经路由登记直接落成品对象 → 同步门判漂移。
    post = batch_post_object_dir(TASK, batch, "article", "攻略", "贡嘎两日", 1)
    post.mkdir(parents=True, exist_ok=True)
    (post / "article.md").write_text("# 贡嘎\n\n正文\n\n## 出发前\n\n值得。", encoding="utf-8")
    write_json(post / "manifest.json", {"assets": [], "citedSourceRefs": []})
    issues = scan_batch(TASK, batch, require_stage_tree=False)
    assert any("未登记内容路由" in i for i in issues), issues


def test_gate_passes_registered_post_object():
    batch = "gate_registered"
    _seed_batch_manifest(batch, content_type="article")
    ensure_task_layout(TASK)
    ref = "贡嘎_体验"
    register_content_object(TASK, batch, ref, content_type="article", angle="攻略", title="贡嘎两日")
    post = content_object_dir(TASK, batch, ref)
    post.mkdir(parents=True, exist_ok=True)
    (post / "article.md").write_text("# 贡嘎\n\n正文\n\n## 出发前\n\n值得一去。", encoding="utf-8")
    write_json(post / "manifest.json", {"assets": [], "citedSourceRefs": []})
    for stage in ("1.download", "2.quality", "3.compose", "4.draft", "5.review"):
        (post / stage).mkdir(parents=True, exist_ok=True)
    issues = scan_batch(TASK, batch)
    assert not any("未登记内容路由" in i for i in issues), issues
    assert not any("命名违规" in i for i in issues), issues


def test_gate_flags_missing_post_source_refs_and_finalization_report():
    batch = "gate_post_evidence_missing"
    _seed_batch_manifest(batch, content_type="article")
    ensure_task_layout(TASK)
    ref = "都江堰_攻略"
    register_content_object(TASK, batch, ref, content_type="article", angle="攻略", title="都江堰一日游怎么玩")
    post = content_object_dir(TASK, batch, ref)
    post.mkdir(parents=True, exist_ok=True)
    (post / "article.md").write_text("# 都江堰\n\n正文\n\n## 出发前\n\n值得。", encoding="utf-8")
    (post / "4.draft").mkdir(parents=True, exist_ok=True)
    (post / "4.draft" / "draft.article.md").write_text("# 都江堰\n\n正文\n", encoding="utf-8")
    write_json(post / "manifest.json", {"assets": [], "citedSourceRefs": []})
    for stage in ("1.download", "2.quality", "3.compose", "5.review"):
        (post / stage).mkdir(parents=True, exist_ok=True)
    issues = scan_batch(TASK, batch)
    assert any("source_refs.json" in i for i in issues), issues
    assert any("finalization_report.json" in i for i in issues), issues


def test_gate_passes_post_evidence_chain_sidecars():
    batch = "gate_post_evidence_ok"
    _seed_batch_manifest(batch, content_type="article")
    ensure_task_layout(TASK)
    ref = "都江堰_攻略_ok"
    register_content_object(TASK, batch, ref, content_type="article", angle="攻略", title="都江堰一日游怎么玩")
    post = content_object_dir(TASK, batch, ref)
    post.mkdir(parents=True, exist_ok=True)
    article = "# 都江堰\n\n正文\n\n## 出发前\n\n值得。"
    (post / "article.md").write_text(article, encoding="utf-8")
    (post / "4.draft").mkdir(parents=True, exist_ok=True)
    (post / "4.draft" / "draft.article.md").write_text(article, encoding="utf-8")
    source_md = "# 都江堰\n\n概述"
    ent = batch_entity_object_dir(TASK, batch, "地点", "景区", "都江堰")
    source_manifest = write_source_unit(
        ent,
        ordinal=1,
        source_id="overview_baike",
        source_md=source_md,
        clean_md=source_md,
        platform="维基百科",
        source_category="encyclopedia",
        url="https://example.com/djy",
        title="都江堰百科",
        target_ref="/entity/地点/景区/都江堰",
    )
    source_ref = str(source_manifest["sourceRef"])
    source_unit_ref = str(source_manifest["sourceUnitRef"])
    write_json(
        post / "manifest.json",
        {"assets": [], "citedSourceRefs": [source_ref]},
    )
    for stage in ("1.download", "2.quality", "3.compose", "5.review"):
        (post / stage).mkdir(parents=True, exist_ok=True)
    write_json(
        post / "1.download" / "source_refs.json",
        {
            "schemaVersion": "quwoquan_data.source_refs/2",
            "baseSourceRef": source_ref,
            "sources": [
                {
                    "sourceRef": source_ref,
                    "sourceUnitRef": source_unit_ref,
                    "role": "base",
                    "sourceFileSha256": sha256_text(source_md),
                }
            ],
        },
    )
    write_json(
        post / "5.review" / "finalization_report.json",
        {
            "schemaVersion": "quwoquan_data.finalization_report",
            "draftArticleRef": "4.draft/draft.article.md",
            "finalArticleRef": "article.md",
            "draftSha256": compute_document_sha256(article),
            "finalSha256": compute_document_sha256(article),
        },
    )
    issues = scan_batch(TASK, batch)
    assert not any("source_refs.json" in i for i in issues), issues
    assert not any("finalization_report.json" in i for i in issues), issues


def test_stage_tree_completeness_default_on():
    batch = "gate_stage_tree"
    _seed_batch_manifest(batch, content_type="article")
    ensure_task_layout(TASK)
    # 内容对象只有成品但缺过程阶段 → 默认即被拦截。
    ref = "四姑娘山_体验"
    register_content_object(TASK, batch, ref, content_type="article", angle="攻略", title="四姑娘山两日")
    post = content_object_dir(TASK, batch, ref)
    post.mkdir(parents=True, exist_ok=True)
    (post / "article.md").write_text("# 四姑娘山\n\n正文\n\n## 出发前\n\n值得。", encoding="utf-8")
    write_json(post / "manifest.json", {"assets": [], "citedSourceRefs": []})

    issues = scan_batch(TASK, batch)
    assert any("阶段树不完整" in i for i in issues), issues
    relaxed = scan_batch(TASK, batch, require_stage_tree=False)
    assert not any("阶段树不完整" in i for i in relaxed), relaxed

    # 补齐 1-5 阶段后通过
    for stage in ("1.download", "2.quality", "3.compose", "4.draft", "5.review"):
        (post / stage).mkdir(parents=True, exist_ok=True)
    strict2 = scan_batch(TASK, batch)
    assert not any("阶段树不完整" in i for i in strict2), strict2


def test_stage_tree_completeness_covers_image_work_by_manifest():
    """图片作品没有 article.md/gallery.md，成品判定改用 manifest，阶段树同样必须完整。"""
    batch = "gate_stage_tree_image"
    _seed_batch_manifest(batch, content_type="image")
    ensure_task_layout(TASK)
    ref = "结构化组图_画报"
    register_content_object(TASK, batch, ref, content_type="image", angle="画报", title="九寨沟组图")
    post = content_object_dir(TASK, batch, ref)
    post.mkdir(parents=True, exist_ok=True)
    # 图片作品成品：manifest(carrier=image) + assets/<image>，无 article.md/gallery.md。
    write_json(
        post / "manifest.json",
        {"contentType": "image", "carrier": "image", "assets": [], "citedSourceRefs": []},
    )
    (post / "assets").mkdir(parents=True, exist_ok=True)
    (post / "assets" / "001_cover.jpg").write_bytes(b"\xff\xd8\xff\x00img")

    # 缺过程阶段（含 1.download）→ 默认即被拦截。
    issues = scan_batch(TASK, batch)
    stage_issues = [i for i in issues if "阶段树不完整" in i]
    assert stage_issues, issues
    assert any("1.download" in i for i in stage_issues), stage_issues
    # 已有 assets/<image>，不应报缺关键资产。
    assert not any("缺关键资产" in i for i in issues), issues

    # 补齐 1-5 阶段后通过；图片作品不要求 article.md。
    for stage in ("1.download", "2.quality", "3.compose", "4.draft", "5.review"):
        (post / stage).mkdir(parents=True, exist_ok=True)
    strict2 = scan_batch(TASK, batch)
    assert not any("阶段树不完整" in i for i in strict2), strict2
    assert not any("缺关键文件 article.md" in i for i in strict2), strict2


def test_stage_tree_completeness_flags_image_work_missing_assets():
    """图片作品成品缺落盘资产 → 关键文件门拦截。"""
    batch = "gate_stage_tree_image_no_asset"
    _seed_batch_manifest(batch, content_type="image")
    ensure_task_layout(TASK)
    ref = "空资产组图_画报"
    register_content_object(TASK, batch, ref, content_type="image", angle="画报", title="无资产组图")
    post = content_object_dir(TASK, batch, ref)
    post.mkdir(parents=True, exist_ok=True)
    write_json(
        post / "manifest.json",
        {"contentType": "image", "carrier": "image", "assets": [], "citedSourceRefs": []},
    )
    # assets/ 目录存在但为空（成品被识别，但缺真实落盘资产）。
    (post / "assets").mkdir(parents=True, exist_ok=True)
    for stage in ("1.download", "2.quality", "3.compose", "4.draft", "5.review"):
        (post / stage).mkdir(parents=True, exist_ok=True)
    issues = scan_batch(TASK, batch)
    assert any("图片作品成品缺关键资产" in i for i in issues), issues


def test_gate_flags_orphan_post_object_residue():
    batch = "gate_orphan"
    _seed_batch_manifest(batch)
    ensure_task_layout(TASK)
    orphan = batch_post_object_dir(TASK, batch, "article", "攻略", "1", 1)
    (orphan / "2.quality").mkdir(parents=True, exist_ok=True)
    write_json(orphan / "manifest.json", {"assets": [], "citedSourceRefs": []})
    issues = scan_batch(TASK, batch, require_stage_tree=False)
    assert any("孤儿内容对象残骸" in i for i in issues), issues


def test_task_gate_flags_legacy_root_entries():
    ensure_task_layout(TASK)
    legacy_posts = task_root(TASK) / "posts"
    legacy_posts.mkdir(parents=True, exist_ok=True)
    issues = scan_task(TASK)
    assert any("历史兼容位仍存在" in i and "task/posts" in i for i in issues), issues


def test_cleanup_runtime_migrates_shared_files_and_removes_legacy_entries():
    ensure_task_layout(TASK)
    root = task_root(TASK)
    (root / "catalog.ndjson").write_text('{"x":1}\n', encoding="utf-8")
    (root / "dedup_ledger.json").write_text('{"schemaVersion":"x"}\n', encoding="utf-8")
    (root / "entity_pages").mkdir(parents=True, exist_ok=True)
    (root / "posts").mkdir(parents=True, exist_ok=True)
    result = ops.cleanup_runtime(TASK)
    assert "catalog.ndjson" in result["migrated"], result
    assert "dedup_ledger.json" in result["migrated"], result
    assert "entity_pages" in result["removed"], result
    assert "posts" in result["removed"], result
    assert (task_shared_dir(TASK) / "catalog.ndjson").is_file()
    assert (task_shared_dir(TASK) / "dedup_ledger.json").is_file()
    assert not (root / "entity_pages").exists()
    assert not (root / "posts").exists()
    assert not scan_task(TASK), scan_task(TASK)


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"directory evidence gate tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()

def test_gate_reports_list_top_level_source_refs_without_crash():
    """agent 把 source_refs.json 顶层写成数组（WP5 舟山岱山县实测）时，
    证据链扫描必须报契约 issue 而不是 AttributeError 崩溃中断整个 verify。"""
    batch = "gate_bad_source_refs"
    _seed_batch_manifest(batch)
    ensure_task_layout(TASK)
    ent = batch_entity_object_dir(TASK, batch, "地点", "景区", "东沙古镇")
    dl = ent / "1.download"
    dl.mkdir(parents=True, exist_ok=True)
    write_json(dl / "source_refs.json", [])
    write_json(ent / "_entity.json", {"label": "东沙古镇", "domain": "地点", "type": "景区"})
    # 无成品时只走 _object_source_unit_records：不得崩溃。
    issues = scan_batch(TASK, batch, require_stage_tree=False)
    assert isinstance(issues, list)
    # 有成品时 _source_refs_issues 必须报顶层类型契约违规。
    (ent / "article.md").write_text("# 东沙古镇\n\n正文。\n", encoding="utf-8")
    issues = scan_batch(TASK, batch, require_stage_tree=False)
    assert any("顶层必须是 object" in i for i in issues), issues

def test_iter_source_units_tolerates_list_top_level():
    from _common.source_unit import iter_source_units

    batch = "gate_bad_source_refs_iter"
    _seed_batch_manifest(batch)
    ensure_task_layout(TASK)
    ent = batch_entity_object_dir(TASK, batch, "地点", "景区", "秀山岛")
    dl = ent / "1.download"
    dl.mkdir(parents=True, exist_ok=True)
    write_json(dl / "source_refs.json", [])
    assert iter_source_units(ent) == []
