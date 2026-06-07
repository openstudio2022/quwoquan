"""目录与资产证据链静态门 + 文风门 契约 (T1)。

可直接运行：python3 quwoquan_data/tests/verify/test_directory_evidence_gate.py
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

from _common.content_object import content_object_dir, register_content_object  # noqa: E402
from _common.batch_manifest import write_batch_manifest  # noqa: E402
from _common.io import write_json  # noqa: E402
from _common.paths import (  # noqa: E402
    batch_entity_object_dir,
    batch_post_object_dir,
    batch_root,
    ensure_task_layout,
)
from _common.prose_style import mechanical_ending_title_issues  # noqa: E402
from _common.source_unit import write_source_unit  # noqa: E402
from verify.verify_directory_evidence_chain import scan_batch  # noqa: E402

TASK = "旅行/地域/四川省/景区/景区全覆盖"


def _seed_batch_manifest(batch: str) -> None:
    write_batch_manifest(TASK, batch, command="task_run")


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
    issues = scan_batch(TASK, batch)
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
    issues = scan_batch(TASK, batch)
    assert any("绝对路径" in i for i in issues), issues
    assert any("机械收尾标题" in i for i in issues), issues
    assert any("天气类来源" in i for i in issues), issues


def test_gate_passes_clean_object():
    batch = "gate_clean"
    _seed_batch_manifest(batch)
    ensure_task_layout(TASK)
    ent = batch_entity_object_dir(TASK, batch, "地点", "景区", "峨眉山")
    write_source_unit(
        ent,
        ordinal=1,
        source_id="overview_baike",
        source_md="# 峨眉山\n\n概述",
        platform="baike",
        source_category="overview_baike",
        url="https://zh.wikipedia.org/wiki/峨眉山",
        title="峨眉山（百科）",
        target_ref="/entity/地点/景区/峨眉山",
    )
    write_json(ent / "_entity.json", {"label": "峨眉山", "domain": "地点", "type": "景区"})
    (ent / "page.md").write_text("# 峨眉山\n\n概述与体验。\n\n## 出发前\n\n值得一去。", encoding="utf-8")
    write_json(ent / "manifest.json", {"assets": [], "citedSourceRefs": ["entities/地点/景区/峨眉山/1.download/sources/01.overview_baike/source.md"]})
    issues = scan_batch(TASK, batch)
    assert not issues, issues


def test_gate_flags_stage_first_regression():
    batch = "gate_regress"
    _seed_batch_manifest(batch)
    ensure_task_layout(TASK)
    # M3/M4 已迁对象根的 compose 报告被回写到 task_produce/results/compose → 必须 BLOCK。
    d = batch_root(TASK, batch) / "task_produce" / "results" / "compose"
    d.mkdir(parents=True, exist_ok=True)
    write_json(d / "九寨沟.json", {"payload": {"generator": "agent"}})
    issues = scan_batch(TASK, batch)
    assert any("stage-first 回退" in i for i in issues), issues


def test_gate_flags_illegal_top_level_entry():
    batch = "gate_toplevel"
    _seed_batch_manifest(batch)
    ensure_task_layout(TASK)
    b = batch_root(TASK, batch)
    b.mkdir(parents=True, exist_ok=True)
    # 旧 produce_trace.json 散在批次顶层 → 顶层结构门拦截。
    (b / "produce_trace.json").write_text("{}", encoding="utf-8")
    issues = scan_batch(TASK, batch)
    assert any("非法批次顶层条目" in i for i in issues), issues


def test_gate_flags_illegal_object_child_dir():
    batch = "gate_naming"
    _seed_batch_manifest(batch)
    ensure_task_layout(TASK)
    ent = batch_entity_object_dir(TASK, batch, "地点", "景区", "贡嘎")
    (ent / "weird_stage").mkdir(parents=True, exist_ok=True)
    write_json(ent / "_entity.json", {"label": "贡嘎", "domain": "地点", "type": "景区"})
    issues = scan_batch(TASK, batch)
    assert any("非法对象子目录" in i for i in issues), issues


def test_gate_flags_unregistered_post_object_drift():
    batch = "gate_drift"
    _seed_batch_manifest(batch)
    ensure_task_layout(TASK)
    # 未经路由登记直接落成品对象 → 同步门判漂移。
    post = batch_post_object_dir(TASK, batch, "article", "攻略", "贡嘎两日", 1)
    post.mkdir(parents=True, exist_ok=True)
    (post / "article.md").write_text("# 贡嘎\n\n正文\n\n## 出发前\n\n值得。", encoding="utf-8")
    write_json(post / "manifest.json", {"assets": [], "citedSourceRefs": []})
    issues = scan_batch(TASK, batch)
    assert any("未登记内容路由" in i for i in issues), issues


def test_gate_passes_registered_post_object():
    batch = "gate_registered"
    _seed_batch_manifest(batch)
    ensure_task_layout(TASK)
    ref = "贡嘎_体验"
    register_content_object(TASK, batch, ref, content_type="article", angle="攻略", title="贡嘎两日")
    post = content_object_dir(TASK, batch, ref)
    post.mkdir(parents=True, exist_ok=True)
    (post / "article.md").write_text("# 贡嘎\n\n正文\n\n## 出发前\n\n值得一去。", encoding="utf-8")
    write_json(post / "manifest.json", {"assets": [], "citedSourceRefs": []})
    issues = scan_batch(TASK, batch)
    assert not any("未登记内容路由" in i for i in issues), issues
    assert not any("命名违规" in i for i in issues), issues


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"directory evidence gate tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
