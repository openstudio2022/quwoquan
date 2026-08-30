"""实体（非线路）内容 composer 红绿契约 + 端到端 GWT。

覆盖：is_entity_brief 分类、单实体成稿（开篇动机/亮点/不足/实用提醒就地融入）、
图片门、体裁一致、来源痕迹清洗、materialize + verify 全绿。

可直接运行：python3 quwoquan_data/tests/local_contract/post/test_entity_composer__behavior__functional__local_contract_test.py
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
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(SCRIPTS_ROOT))


import numpy as np  # noqa: E402
import cv2  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.io import read_json, write_json  # noqa: E402
from core.article_package import compute_document_sha256  # noqa: E402
from core.control_types import ContentType, PostStage  # noqa: E402
from core.data_issue import (  # noqa: E402
    DataIssueCode,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)
from content.execution.runtime_state import write_execution_runtime_state  # noqa: E402
from core.paths import (  # noqa: E402
    execution_inputs_dir,
    execution_root,
    ensure_execution_command_layout,
    ensure_execution_layout,
)
from content.post.article.evidence_bundle import public_byline_label  # noqa: E402
from content.post.object_index import read_brief_object, write_brief_object  # noqa: E402
from content.post.article.base_draft import save_base_draft_ledger  # noqa: E402
from content.post.article.draft_io import (  # noqa: E402
    read_draft_article,
    read_draft_meta,
    read_writing_pack,
    write_agent_draft,
)
from verify.post_verify import verify_scope  # noqa: E402
from content.source.source_unit import resolve_entity_object_dir, write_source_unit  # noqa: E402
from content.execution.stage_reports import stage_result_path, write_repair_report  # noqa: E402
from content.post.article.route_analysis import analyze_route_ref  # noqa: E402
from content.post.article.entity_composition import (  # noqa: E402
    build_entity_writing_pack,
    is_entity_brief,
)
from content.post.article.entity_review import review_entity_draft  # noqa: E402
from content.post.materialize_apply import materialize_posts  # noqa: E402
from content.post.handler import PostStageRequest, handle_post  # noqa: E402
from support.article_source_registry_fixture import (  # noqa: E402
    article_registry_write_kwargs,
)
from support.execution_manifest_fixture import build_execution_fixture  # noqa: E402
def _faithful_entity_draft(title: str, byline: str) -> str:
    """模拟会话模型"轻改底稿"：保留 _BASE_PARAS 骨架（高留存率），按 brief.structure
    必需小节(进馆第一印象/最停留的展厅/参观动线/离开后的感受)组织，仅对第 6 段(不足)
    做语气轻改，使 baseDraftFidelity 落在 [55%,99.5%]——既非脱稿，也非整篇逐字照搬。"""
    p = _BASE_PARAS
    parts = [
        f"# {title}",
        f"> {byline} · 资料整理后的编辑判断",
        "## 进馆第一印象",
        p[0],
        p[1],
        "## 最停留的展厅",
        p[2],
        "## 参观动线",
        p[3],
        p[4],
        "## 离开后的感受",
        _REWORDED_DRAWBACK,
        p[6],
        p[7],
        p[8],
        p[9],
    ]
    return "\n\n".join(parts) + "\n"


def _compose_entity_agent_draft(execution_id: str, ref: str, brief: dict):
    """共享：prepare 写作契约 → 模拟会话模型创作 entity 正文写回草稿。返回 (quality, pack)。"""
    quality = analyze_route_ref(execution_id, ref, brief)
    pack = build_entity_writing_pack(execution_id, ref, brief, quality)
    byline = public_byline_label(str(brief.get("templateId")), brief.get("creator") or {})
    article = _faithful_entity_draft(brief["titleHint"], byline)
    write_agent_draft(
        execution_id,
        ref,
        article,
        model="test-agent/contract",
        cited_source_paths=quality.get("sourcePaths") or [],
        covered_facts=pack.get("mustIncludeFacts") or [],
        agent_run_id=f"run-{ref}",
        agent_id=f"agent-{ref}",
    )
    return quality, pack

EXECUTION_ID = "20260711--travel-article-composer--test-region-b--pilot-001"
REF = "三星堆博物馆_体验"
ENTITY = "三星堆博物馆"

def _source_unit_for_ref(source_ref: str) -> Path:
    return (execution_root(EXECUTION_ID) / source_ref).parent

# 底稿（base draft）：富叙事长文，含动机/第一印象/停留展厅/参观时间/推荐动线/不足/
# 离开感受，覆盖 mustIncludeFacts（参观时间、推荐动线、停留展厅）。1:1 模型下成品须轻改
# 自此底稿（base_draft_similarity 留存率 ∈ [55%,99.5%]），故各段措辞即成品骨架。
_BASE_PARAS = [
    "出发前我其实有点犹豫，怕三星堆博物馆只是被名气架起来的网红打卡地，担心人挤人又看不出门道，真正走进去之后才发现展陈在清晨光线里安静得让人愿意慢下来，那份顾虑也就慢慢放下了。",
    "进馆第一印象不是被名气震慑，而是一种被允许放慢的松弛，我没急着赶往下一处，而是先在入口附近站了一会儿，让自己从一路奔波的赶路状态里慢慢缓过来，再决定从哪里看起。",
    "我在馆里停留最久的，是青铜大立人和黄金面具所在的那几间停留展厅，人少的时候最能看清那些纹路、铸造痕迹与修复的接缝，也最能体会到古蜀工匠那种不慌不忙的耐心。",
    "关于参观时间，我会诚实地建议留出大半天甚至更从容一些，把最想细看的停留展厅排在开馆后人还不多的时段，主动错开午后的高峰，别让排队把好心情磨没了。",
    "在参观动线上，我推荐先按馆方给出的推荐动线走完主力展厅，再回头补看自己感兴趣的次要展区，这样既不浪费体力，也不会在人潮里反复折返、走冤枉路。",
    "当然也得说说不足，让我不太舒服的是午后排队和讲解扎堆，连续看展下来确实会有点累，注意力也容易被周围此起彼伏的人声分散，怕吵的人要有心理准备。",
    "离开后再回想，这趟最值得的并不是把每一个展厅都打卡看完，而是把停留展厅和参观时间认真排进当天计划、避开午后高峰之后，那份能安静看展的从容与踏实。",
    "如果你也想认真看展而不是匆匆打卡，我会建议你为真正打动自己的细节多留一些时间，按自己的节奏慢慢走，三星堆博物馆值得你专门来一趟。",
    "我不会假装它处处完美，但只要避开高峰、跟着推荐动线安排好参观时间，它给我的那份安静和惊喜，远比出发前的犹豫要多得多。",
    "临走在文创区我也没急着离开，慢慢翻看那些以面具和神树为灵感的小物，算是给这趟安静的看展之旅留一个温和的收尾。",
]

# 底稿来源页：attribution 的 sourcePostUrl 与 source.md frontmatter 的 url 必须
# 同源，compose 期会比对两者，漂移即判来源被换过。
BASE_SOURCE_URL = "https://travel.qunar.com/youji/sanxingdui"

SOURCE_TEXT = (
    "---\n"
    f"url: {BASE_SOURCE_URL}\n"
    "platform: qunar\n"
    "license: factual-reference-only\n"
    "allowedUse: internal_reference\n"
    "title: sample\n"
    "entity: 三星堆博物馆\n"
    "retained: true\n"
    "---\n\n"
    + "景区官方电话：010-12345678。\n\n"
    + "\n\n".join(_BASE_PARAS)
    + "\n"
)

# 第 6 段（不足）的轻改版本：成品对底稿做去语病/语气适配的"轻改"，使留存率落在
# [55%,99.5%]（既非脱稿从零另写，也非整篇零加工逐字照搬）。其余段落保留底稿骨架。
_REWORDED_DRAWBACK = (
    "需要提醒的是体验上的小遗憾：临近中午，入口与讲解点常常排起长队、人声鼎沸，"
    "一路看下来体力会被悄悄耗掉，专注力也难免被打散，对声音敏感的朋友最好提前做好准备。"
)


def _clean_image(path: Path, seed: int) -> None:
    img = np.zeros((220, 300, 3), np.uint8)
    rng = np.random.default_rng(seed)
    img[:] = rng.integers(0, 255, size=3, dtype=np.uint8)
    cv2.circle(img, (140 + seed * 6, 110), 30 + seed * 5, (int(seed * 53) % 255, 90, 150), -1)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img)


def _entity_brief() -> dict:
    return {
        "templateId": "博物馆_体验",
        "titleHint": "三星堆博物馆体验指南",
        "subject": {"kind": "entity", "type": "地点/博物馆"},
        "entityRefs": [f"地点/博物馆/{ENTITY}"],
        "vertical": "travel",
        "carrier": "article",
        "creator": {
            "creatorProfileId": "qwq_creator_travel_blogger_001",
            "authorId": "builtin_travel_blogger",
            "creatorArchetype": "travel_blogger",
        },
        "render": {"articleTemplate": "journal", "fontPreset": "handwritten"},
        "structure": {"required": ["进馆第一印象", "最停留的展厅", "参观动线", "离开后的感受"]},
        "hooks": ["在{name}，我停留最久的是这个展柜"],
        "mustIncludeFacts": ["参观时间", "推荐动线", "停留展厅"],
        "wordCount": {"min": 700, "max": 1600},
        "imagePlan": [{"slot": "外观", "imageLayout": "fullWidth"}, {"slot": "展陈细节", "imageLayout": "wrapRight"}],
        "tagRefs": ["Format/内容角度/体验/亲身体验", "Format/内容载体/文章/长文", "Topic/旅行/玩法/博物馆展览"],
    }


def _seed_sources() -> str:
    """落盘单一底稿来源单元（curated_story，含 3 张同源图）。返回其 sourceRef。

    1:1 底稿中心：生产经 handler._assign_base_draft 给 brief 赋 baseSourceRef；
    这些直连 compose 的单测须显式把返回的 sourceRef 写回 brief['baseSourceRef']，
    否则 RC4 同源硬门下文章无可用配图（imageGate 失败）。
    """
    build_execution_fixture(EXECUTION_ID)
    ensure_execution_layout(EXECUTION_ID)
    ensure_execution_command_layout(EXECUTION_ID, "source")
    ensure_execution_command_layout(EXECUTION_ID, "post")
    write_execution_runtime_state(EXECUTION_ID, command="execution")
    import shutil

    d = execution_root(EXECUTION_ID) / "drafts"
    if d.exists():
        shutil.rmtree(d)
    # 对象优先：草稿已迁到 batch posts 对象目录，需连同路由索引一并重置，避免跨用例残留 agent 草稿。
    posts_root = execution_root(EXECUTION_ID) / "posts"
    if posts_root.exists():
        shutil.rmtree(posts_root)
    index_file = execution_root(EXECUTION_ID) / "_shared" / "content_object_index.json"
    if index_file.exists():
        index_file.unlink()
    write_json(execution_inputs_dir(EXECUTION_ID, "post", "compose") / f"{REF}.json", _entity_brief())
    obj = resolve_entity_object_dir(EXECUTION_ID, ENTITY, etype_hint="地点/博物馆")
    image_root = Path(tempfile.mkdtemp(prefix="entity_composer_sources_"))
    image_paths: list[Path] = []
    for k in range(3):
        image_path = image_root / f"{ENTITY}_{k}.jpg"
        _clean_image(image_path, seed=k + 1)
        image_paths.append(image_path)
    base_manifest = write_source_unit(
        obj,
        ordinal=1,
        source_id="curated_story",
        source_md=SOURCE_TEXT,
        quality={
            "sourceId": "curated_story",
            "quality": "A-story",
            "score": 8,
            "reasons": ["length_ok", "scene_rich"],
            "excerpt": f"{ENTITY} 真正影响体验的是参观时间和停留展厅的取舍。",
            "url": BASE_SOURCE_URL,
        },
        title="sample",
        target_ref=f"/entity/地点/博物馆/{ENTITY}",
        relevance=f"{ENTITY} 的参观与展陈体验",
        # 文章车道的可交付来源单元必须由注册表解析出身份与 attribution：内部整理
        # 来源没有注册表条目，写盘期即 fail-closed，因此底稿来源走登记站点。
        **article_registry_write_kwargs(
            url=BASE_SOURCE_URL,
            platform="qunar",
            publish_media_mode="illustrated",
        ),
        images=[{"sourcePath": str(path), "caption": f"{ENTITY} 图{k}", "relevance": f"{ENTITY} 图{k}"} for k, path in enumerate(image_paths)],
    )
    return str(base_manifest["sourceRef"])


def test_is_entity_brief_classification():
    assert is_entity_brief(_entity_brief()) is True
    route_like = {"subject": {"kind": "topic", "type": "旅行/线路"}, "templateId": "线路_环线攻略", "entityRefs": ["a"]}
    assert is_entity_brief(route_like) is False


def test_normalize_entity_refs_full_path():
    """回归：主实体引用必须补全为发布门可识别的全路径 /entity/{domain}/{type}/{name}。

    历史 bug：composer 仅拼 /entity/{name}，publish_filter._parse_entity_ref 需 domain/type/name
    三段，导致主实体被误判「无主页」过滤，post 失去实体关联。
    """
    from governance.coverage.entity_extract import normalize_entity_refs
    from content.review.publish_filter import _parse_entity_ref

    # 短名 + subject.type 补全
    assert normalize_entity_refs(["稻城亚丁"], "地点/景区") == ["/entity/地点/景区/稻城亚丁"]
    # 已是 domain/type/name（无 /entity/ 前缀）
    assert normalize_entity_refs(["地点/博物馆/三星堆博物馆"], "地点/博物馆") == [
        "/entity/地点/博物馆/三星堆博物馆"
    ]
    # 已带 /entity/ 前缀的全路径，原样规范化
    assert normalize_entity_refs(["/entity/地点/景区/四姑娘山"], "地点/景区") == [
        "/entity/地点/景区/四姑娘山"
    ]
    # 输出必须被 publish_filter 解析为完整三段（修复前会解析失败 → 过滤）
    domain, etype, name = _parse_entity_ref(normalize_entity_refs(["稻城亚丁"], "地点/景区")[0])
    assert (domain, etype, name) == ("地点", "景区", "稻城亚丁")


def test_entity_placeholder_blocks_then_agent_draft_green():
    base_ref = _seed_sources()
    brief = _entity_brief()
    brief["baseSourceRef"] = base_ref
    # prepare：写作契约 + 占位草稿；占位阶段出处门必须拦截。
    quality = analyze_route_ref(EXECUTION_ID, REF, brief)
    pack = build_entity_writing_pack(EXECUTION_ID, REF, brief, quality)
    assert pack["allowedContactNumbers"] == ["01012345678"]
    assert read_writing_pack(EXECUTION_ID, REF) is not None
    placeholder = review_entity_draft(EXECUTION_ID, REF, brief, quality)
    assert placeholder["decision"] == "revision_needed"
    assert not placeholder["checks"]["generatorProvenance"]["passed"]

    # 会话模型创作 → review 全绿。
    quality, pack = _compose_entity_agent_draft(EXECUTION_ID, REF, brief)
    review = review_entity_draft(EXECUTION_ID, REF, brief, quality)
    assert review["decision"] == "approved", review["issues"]
    assert "travelogueDensity" in review["checks"]
    assert review["checks"]["entityCoverage"]["passed"]
    assert review["checks"]["imageGate"]["passed"]
    assert review["checks"]["generatorProvenance"]["passed"]
    assert review["checks"]["factTraceability"]["passed"], review["checks"]["factTraceability"]["issues"]
    assert review["generator"] == "agent"


def test_entity_annotation_refreshes_draft_provenance():
    base_ref = _seed_sources()
    brief = _entity_brief()
    brief["baseSourceRef"] = base_ref
    write_brief_object(EXECUTION_ID, REF, brief, content_type="article")
    _compose_entity_agent_draft(EXECUTION_ID, REF, brief)

    handle_post(
        PostStageRequest(
            execution_id=EXECUTION_ID,
            content_type=ContentType.ARTICLE,
            stage=PostStage.ANNOTATE_ENTITIES,
            refs=(REF,),
        )
    )

    article = read_draft_article(EXECUTION_ID, REF)
    meta = read_draft_meta(EXECUTION_ID, REF)
    assert article is not None
    assert meta is not None
    assert f"[{ENTITY}](/entity/地点/博物馆/{ENTITY})" in article
    assert meta["annotatedEntityRefs"] == [f"/entity/地点/博物馆/{ENTITY}"]
    assert meta["draftSha256"] == compute_document_sha256(article)


def test_entity_review_approval_clears_stale_repair_report():
    base_ref = _seed_sources()
    brief = _entity_brief()
    brief["baseSourceRef"] = base_ref
    quality, _pack = _compose_entity_agent_draft(EXECUTION_ID, REF, brief)
    repair_path = write_repair_report(
        execution_id=EXECUTION_ID,
        command="post",
        ref=REF,
        failed_stage=DataIssueStage.REVIEW,
        failed_gate="contentReview",
        issues=[data_issue(
            DataIssueCode.QUALITY_FAILED,
            stage=DataIssueStage.REVIEW,
            ref=REF,
            recovery=DataRecoveryAction.REWIND_COMPOSE,
            message="old issue",
        )],
        fallback_stage="agent_compose",
        rerun_chain=["agent_compose", "review", "materialize"],
    )
    assert repair_path.is_file()

    review = review_entity_draft(EXECUTION_ID, REF, brief, quality)

    assert review["decision"] == "approved", review["issues"]
    assert not stage_result_path(EXECUTION_ID, "post", "repair_report", REF).exists()


def test_entity_e2e_materialize_verify_green():
    base_ref = _seed_sources()
    brief = _entity_brief()
    brief["baseSourceRef"] = base_ref
    quality, _pack = _compose_entity_agent_draft(EXECUTION_ID, REF, brief)
    review = review_entity_draft(EXECUTION_ID, REF, brief, quality)
    assert review["decision"] == "approved", review["issues"]
    posts = materialize_posts(EXECUTION_ID, "article")
    assert posts, "materialize produced no entity post"
    # 回归：materialized manifest 的 entityRefs 必须是发布门可识别的全路径。
    import json as _json
    from content.review.publish_filter import _parse_entity_ref

    mani = _json.loads((Path(str(posts[0])) / "manifest.json").read_text(encoding="utf-8"))
    assert mani["entityRefs"] == [f"/entity/地点/博物馆/{ENTITY}"], mani["entityRefs"]
    assert mani["allowedContactNumbers"] == ["01012345678"]
    assert _parse_entity_ref(mani["entityRefs"][0]) == ("地点", "博物馆", ENTITY)
    published_mentions = [
        m for m in mani.get("semanticMentions", [])
        if m.get("status") == "published"
    ]
    mention_refs = {
        (m.get("kind"), m.get("targetRef"))
        for m in published_mentions
    }
    for entity_ref in mani["entityRefs"]:
        assert ("entity", entity_ref) in mention_refs
    for tag_ref in mani["tagRefs"]:
        assert ("tag", tag_ref) in mention_refs
    roots, issues = verify_scope(execution_id=EXECUTION_ID, scope="current")
    assert roots, "verify found no posts root"
    assert not issues, "entity pilot verify must be green:\n" + "\n".join(issues[:40])


def test_compose_brief_persists_reassigned_base_source_ref():
    _seed_sources()
    brief = _entity_brief()
    write_brief_object(EXECUTION_ID, REF, brief, content_type="article")
    obj = resolve_entity_object_dir(EXECUTION_ID, ENTITY, etype_hint="博物馆")
    source_refs = read_json(obj / "1.download" / "source_refs.json")
    initial_ref = next(
        row["sourceRef"]
        for row in source_refs["sources"]
        if row.get("sourceId") == "curated_story"
    )
    save_base_draft_ledger(
        EXECUTION_ID,
        {
            "schema": "quwoquan_data.base_draft_ledger",
            "assignments": {initial_ref: "三星堆博物馆_图集"},
        },
    )

    image_root = Path(tempfile.mkdtemp(prefix="entity_composer_reassign_sources_"))
    image_path = image_root / f"{ENTITY}_reassigned.jpg"
    _clean_image(image_path, seed=8)
    story_manifest = write_source_unit(
        obj,
        ordinal=2,
        source_id="museum_story",
        source_md="# 三星堆博物馆\n\n这是一条可写底稿，保留现场叙事。",
        clean_md="# 三星堆博物馆\n\n这是一条可写底稿，保留现场叙事。",
        quality={"sourceId": "museum_story", "quality": "A-story", "score": 8},
        title="museum story",
        target_ref=f"/entity/地点/博物馆/{ENTITY}",
        **article_registry_write_kwargs(
            url="https://travel.qunar.com/youji/sanxingdui-story",
            platform="qunar",
            publish_media_mode="illustrated",
        ),
        images=[
            {
                "sourcePath": str(image_path),
                "caption": f"{ENTITY} 展厅图",
                "relevance": f"{ENTITY} 展厅图来自重分配底稿来源",
            }
        ],
    )

    handle_post(
        PostStageRequest(
            execution_id=EXECUTION_ID,
            content_type=ContentType.ARTICLE,
            stage=PostStage.COMPOSE_BRIEF,
            refs=(REF,),
            writer_group_size=1,
            materialize=False,
            allow_partial=False,
        )
    )
    persisted = read_brief_object(EXECUTION_ID, REF)
    assert persisted is not None
    # 可读命名契约（spec §3）：sources/{实体名}__{sourceKind}__{hash8}/。
    assert re.match(r"^sources/[^/]+__[A-Za-z0-9_\-]+__[0-9a-f]{8}/", persisted["baseSourceRef"]), persisted["baseSourceRef"]
    persisted_meta = read_json(_source_unit_for_ref(persisted["baseSourceRef"]) / "meta.json")
    assert persisted_meta["sourceId"] == "museum_story"


def test_entity_article_blocks_cross_source_visual_support_when_base_image_missing():
    _seed_sources()
    brief = _entity_brief()
    obj = resolve_entity_object_dir(EXECUTION_ID, ENTITY, etype_hint="地点/博物馆")
    import shutil

    for dirname in ("30.no_image_base_for_fallback", "31.article_visual_support_for_fallback"):
        shutil.rmtree(obj / "1.download" / "sources" / dirname, ignore_errors=True)

    base_manifest = write_source_unit(
        obj,
        ordinal=30,
        source_id="no_image_base_for_fallback",
        source_md="三星堆博物馆的参观时间、推荐动线和停留展厅信息都可核验，但该底稿无可发布图片。",
        clean_md="三星堆博物馆的参观时间、推荐动线和停留展厅信息都可核验，但该底稿无可发布图片。",
        quality={"sourceId": "no_image_base_for_fallback", "quality": "A-story", "score": 8},
        title="no image base",
        target_ref=f"/entity/地点/博物馆/{ENTITY}",
        relevance=f"{ENTITY} 的无图底稿",
        images=[],
        **article_registry_write_kwargs(
            url="https://travel.qunar.com/youji/sanxingdui-no-image-base",
            platform="qunar",
        ),
    )
    image_root = Path(tempfile.mkdtemp(prefix="entity_visual_support_"))
    image_path = image_root / f"{ENTITY}_visual_support.jpg"
    _clean_image(image_path, seed=13)
    visual_manifest = write_source_unit(
        obj,
        ordinal=31,
        source_id="article_visual_support_for_fallback",
        source_md="三星堆博物馆开放授权视觉支持素材。",
        clean_md="三星堆博物馆开放授权视觉支持素材。",
        quality={"sourceId": "article_visual_support_for_fallback", "quality": "A-image", "score": 7},
        title="visual support",
        target_ref=f"/entity/地点/博物馆/{ENTITY}",
        relevance=f"{ENTITY} 的可发布视觉支持",
        **article_registry_write_kwargs(
            url="https://travel.qunar.com/youji/sanxingdui-visual-support",
            platform="qunar",
            source_role="supporting",
            publish_media_mode="illustrated",
        ),
        images=[
            {
                "sourcePath": str(image_path),
                "caption": f"{ENTITY} 可发布视觉支持图",
                "relevance": f"{ENTITY} 可发布视觉支持图",
                "license": "internal-curated",
                "credit": "Quwoquan",
                "termsUrl": "https://example.com/terms",
                "authorizationProof": "https://example.com/proof",
                "usageScope": "app_publish",
            }
        ],
    )
    brief["baseSourceRef"] = base_manifest["sourceRef"]

    quality = analyze_route_ref(EXECUTION_ID, REF, brief)
    try:
        build_entity_writing_pack(EXECUTION_ID, REF, brief, quality)
    except RuntimeError as exc:
        assert "article base draft source has no usable source images" in str(exc)
    else:
        raise AssertionError("cross-source article visual support must not replace base source images")


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"entity composer tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
