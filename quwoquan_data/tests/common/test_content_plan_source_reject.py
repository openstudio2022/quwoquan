"""content_plan 证据准入门 contract test：source_screen=reject 来源不得进入 content_plan。

可直接运行：python3 quwoquan_data/tests/common/test_content_plan_source_reject.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

_TMP = tempfile.mkdtemp(prefix="qwq_content_plan_test_")
os.environ["QWQ_RUNTIME_ROOT"] = _TMP

from _common import content_plan as cp  # noqa: E402
from _common.base_draft import assign_base_draft, base_draft_candidates, base_draft_fidelity_issues, load_base_draft_text  # noqa: E402
from _common.io import write_json  # noqa: E402
from _common.paths import batch_content_plan_packet_path, batch_results_dir  # noqa: E402
from _common.source_unit import resolve_entity_object_dir, write_source_unit  # noqa: E402

TASK = "旅行/地域/四川省/景区/景区精选"
BATCH = "test_batch_reject"


def _seed():
    reject_dir = batch_results_dir(TASK, BATCH, "download", "source_screen")
    write_json(reject_dir / "reject1.json", {"sourceId": "reject1", "decision": "reject"})
    write_json(reject_dir / "keep1.json", {"sourceId": "keep1", "decision": "retain"})
    packet = {
        "schemaVersion": cp.CONTENT_PLAN_SCHEMA,
        "items": [
            {
                "ref": "x",
                "kind": "entity",
                "title": "样例",
                "entityRefs": ["e1"],
                "evidenceRefs": ["1.download/sources/reject1.md"],
                "rationale": "r",
                "writingIntent": "planning_consultation",
                "baseSourceRef": "1.download/sources/reject1.md",
            }
        ],
    }
    write_json(batch_content_plan_packet_path(TASK, BATCH), packet)


def test_reject_source_ids_collects_only_rejects():
    _seed()
    rejects = cp.reject_source_ids(TASK, BATCH)
    assert rejects == {"reject1"}


def test_content_plan_blocks_rejected_source():
    _seed()
    issues = cp.validate_content_plan(TASK, BATCH, {})
    assert any("cites rejected source" in i and "reject1" in i for i in issues), issues


def test_content_plan_quotas_required_includes_gallery_posts():
    spec = {"content": {"quotas": {"galleryPosts": 2}}}
    assert cp.content_plan_quotas_required(spec) is True


def test_base_draft_candidates_exclude_reject_sources():
    obj = resolve_entity_object_dir(TASK, BATCH, "九寨沟", etype_hint="景区")
    write_source_unit(
        obj,
        ordinal=1,
        source_id="reject_probe",
        source_md="---\nretained: false\n---\n\nmanual_source_plan_note: 探针页\n",
        quality={"sourceId": "reject_probe", "quality": "Reject", "score": 0},
        platform="mafengwo",
        source_category="travelogue",
        url="https://example.com/r",
        title="探针页",
        target_ref="/entity/地点/景区/九寨沟",
    )
    write_source_unit(
        obj,
        ordinal=2,
        source_id="good_story",
        source_md="# 九寨沟\n\n真实正文，含开放时间与体验判断。",
        quality={"sourceId": "good_story", "quality": "A-story", "score": 8},
        platform="baike",
        source_category="overview_baike",
        url="https://example.com/g",
        title="可用正文",
        target_ref="/entity/地点/景区/九寨沟",
    )
    brief = {"entityRefs": ["地点/景区/九寨沟"]}
    candidates = base_draft_candidates(TASK, BATCH, brief)
    refs = [row["sourceRef"] for row in candidates]
    assert any("good_story" in ref for ref in refs), refs
    assert not any("reject_probe" in ref for ref in refs), refs


def test_assign_base_draft_rejects_declared_reject_source():
    obj = resolve_entity_object_dir(TASK, BATCH, "黄龙", etype_hint="景区")
    write_source_unit(
        obj,
        ordinal=1,
        source_id="reject_probe",
        source_md="---\nretained: false\n---\n\nmanual_source_plan_note: 探针页\n",
        quality={"sourceId": "reject_probe", "quality": "Reject", "score": 0},
        platform="mafengwo",
        source_category="travelogue",
        url="https://example.com/r2",
        title="探针页",
        target_ref="/entity/地点/景区/黄龙",
    )
    write_source_unit(
        obj,
        ordinal=2,
        source_id="good_story",
        source_md="# 黄龙\n\n真实正文，含体验判断与出行信息。",
        quality={"sourceId": "good_story", "quality": "A-story", "score": 9},
        platform="baike",
        source_category="overview_baike",
        url="https://example.com/g2",
        title="可用正文",
        target_ref="/entity/地点/景区/黄龙",
    )
    chosen = assign_base_draft(
        TASK,
        BATCH,
        "post://黄龙",
        {
            "entityRefs": ["地点/景区/黄龙"],
            "baseSourceRef": "entities/地点/景区/黄龙/1.download/sources/01.reject_probe/source.md",
        },
    )
    assert chosen and "good_story" in chosen, chosen


def test_assign_base_draft_reassigns_when_declared_source_taken_by_peer():
    obj = resolve_entity_object_dir(TASK, BATCH, "都江堰", etype_hint="景区")
    write_source_unit(
        obj,
        ordinal=1,
        source_id="wiki_dujiangyan",
        source_md="# 都江堰\n\n概述底稿，含基础事实。",
        quality={"sourceId": "wiki_dujiangyan", "quality": "A", "score": 9},
        platform="wikipedia",
        source_category="overview_baike",
        url="https://example.com/wiki",
        title="都江堰概述",
        target_ref="/entity/地点/景区/都江堰",
    )
    write_source_unit(
        obj,
        ordinal=2,
        source_id="ctrip_dujiangyan",
        source_md="# 都江堰游记\n\n长篇游记底稿，保留现场叙事。",
        quality={"sourceId": "ctrip_dujiangyan", "quality": "A-story", "score": 8},
        platform="ctrip",
        source_category="travelogue",
        url="https://example.com/ctrip",
        title="都江堰游记",
        target_ref="/entity/地点/景区/都江堰",
    )
    first = assign_base_draft(
        TASK,
        BATCH,
        "post://都江堰_画报",
        {"entityRefs": ["地点/景区/都江堰"], "baseSourceRef": "wiki_dujiangyan"},
    )
    second = assign_base_draft(
        TASK,
        BATCH,
        "post://都江堰_攻略",
        {"entityRefs": ["地点/景区/都江堰"], "baseSourceRef": "wiki_dujiangyan"},
    )
    assert first and "wiki_dujiangyan" in first, first
    assert second and "ctrip_dujiangyan" in second, second
    assert first != second


def test_load_base_draft_text_prefers_source_clean():
    obj = resolve_entity_object_dir(TASK, BATCH, "峨眉山", etype_hint="景区")
    write_source_unit(
        obj,
        ordinal=1,
        source_id="wiki_emeishan",
        source_md="raw source with frontmatter-ish noise\nmanual_source_plan_note: 不该优先命中",
        clean_md="clean source body only",
        quality={"sourceId": "wiki_emeishan", "quality": "A", "score": 9},
        platform="wikipedia",
        source_category="overview_baike",
        url="https://example.com/emeishan",
        title="峨眉山概述",
        target_ref="/entity/地点/景区/峨眉山",
    )
    text = load_base_draft_text(
        TASK,
        BATCH,
        "entities/地点/景区/峨眉山/1.download/sources/01.wiki_emeishan/source.md",
    )
    assert text == "clean source body only"


def test_load_base_draft_text_extracts_signal_body_from_noisy_clean_source():
    obj = resolve_entity_object_dir(TASK, BATCH, "都江堰", etype_hint="景区")
    write_source_unit(
        obj,
        ordinal=2,
        source_id="ctrip_noisy",
        source_md="raw fallback",
        clean_md=(
            "登录\n注册\n我的订单\n"
            "都江堰景区，位于都江堰市城西岷江干流上，由秦国蜀郡太守李冰及其子于西元前256年左右修建，是目前中国保存完整的古代水利工程。\n"
            "工程由鱼嘴分水堤、飞沙堰溢洪道、宝瓶口引水口三大主体工程和百丈堤、人字堤等附属工程构成，把岷江分隔成外江和内江。\n"
            "用户点评\n"
            "附近景点\n"
            "都江堰真的很值得一看，古人的智慧太了不起了。\n"
        ),
        quality={"sourceId": "ctrip_noisy", "quality": "B-fact", "score": 4},
        platform="ctrip",
        source_category="travelogue",
        url="https://example.com/ctrip-noisy",
        title="都江堰 noisy",
        target_ref="/entity/地点/景区/都江堰",
    )
    text = load_base_draft_text(
        TASK,
        BATCH,
        "entities/地点/景区/都江堰/1.download/sources/02.ctrip_noisy/source.md",
    )
    assert "登录" not in text
    assert "附近景点" not in text
    assert "都江堰景区，位于都江堰市城西岷江干流上" in text
    assert "工程由鱼嘴分水堤、飞沙堰溢洪道、宝瓶口引水口三大主体工程" in text


def test_base_draft_fidelity_gallery_uses_leading_excerpt_window():
    tail = "\\n\\n".join(
        f"尾段延伸事实{i:03d}：这一段只用于拉长底稿窗口，不应要求画报全文覆盖。"
        for i in range(120)
    )
    base = (
        "第一段先写景区概况与主景。\\n\\n"
        "第二段继续写最核心的观看顺序与现场感。\\n\\n"
        "第三段补充一些延伸事实。\\n\\n"
        + tail
    )
    article = (
        "# 图集\\n\\n"
        "第一段先写景区概况与主景。\\n\\n"
        "第二段继续写最核心的观看顺序与现场感。\\n\\n"
        "第三段补充一些延伸事实。\\n"
    )
    assert base_draft_fidelity_issues(article, base)  # article 口径仍会被长尾底稿拉低
    assert base_draft_fidelity_issues(article, base, carrier="gallery") == []


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"content_plan source-reject tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
