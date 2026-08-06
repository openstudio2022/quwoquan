"""交集信号 intersectionHints 红绿测试 ——「明」：讲清推荐理由 + 对齐 IntersectionReason 口径。

覆盖：
- 契约字段对齐：hint 字段集 ⊆ feature_profile_view/intersection_reason.yaml 的 fields。
- build_intersection_hints：entityRefs→content、非地理 tag→interest。
- 完备性门：缺维度/不足条数/枚举非法/锚点悬空/off-contract 字段均报。
- materialize 端到端：产出 manifest.intersectionHints 且完备性门全绿。

可直接运行：python3 quwoquan_data/tests/local_contract/core/test_intersection_signal__behavior__functional__local_contract_test.py
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


from core.intersection_signal import (  # noqa: E402
    HINT_FIELDS,
    INTERSECTION_CONTRACT_PATH,
    build_intersection_hints,
    contract_field_names,
    intersection_hint_issues,
)
from content.post.article.draft_io import write_agent_draft  # noqa: E402
from core.io import read_json, write_json  # noqa: E402
from core.paths import (  # noqa: E402
    ensure_execution_command_layout,
    ensure_execution_layout,
    execution_command_root,
    execution_root,
)
from content.execution.stage_reports import write_stage_result  # noqa: E402
from content.post.materialize_apply import materialize_posts  # noqa: E402

_MANIFEST = {
    "entityRefs": ["/entity/地点/景区/九寨沟"],
    "normalizedEntityRefs": ["entity:景区:九寨沟"],
    "tagRefs": ["主题/山水风光", "Format/内容角度/攻略"],
}


def test_hint_fields_align_with_contract():
    contract = contract_field_names()
    assert contract, "必须能读到 feature_profile_view/intersection_reason.yaml 契约字段"
    assert set(HINT_FIELDS) <= contract, set(HINT_FIELDS) - contract


def test_intersection_contract_uses_current_feature_profile_owner():
    assert INTERSECTION_CONTRACT_PATH.parts[-3:] == (
        "recommendation_feature_profile_view",
        "projections",
        "intersection_reason.yaml",
    )


def test_build_hints_covers_content_interest():
    hints = build_intersection_hints(_MANIFEST)
    dims = {h["dimension"] for h in hints}
    assert {"content", "interest"} <= dims, dims
    assert intersection_hint_issues(hints, _MANIFEST) == []


def test_missing_interest_dimension_flagged():
    manifest = {
        "entityRefs": ["/entity/地点/景区/九寨沟"],
        "normalizedEntityRefs": ["entity:景区:九寨沟"],
        "tagRefs": ["地理/行政区/test-region-b"],
    }
    hints = build_intersection_hints(manifest)
    issues = intersection_hint_issues(hints, manifest)
    assert any("dimension missing: interest" in i for i in issues), issues


def test_too_few_hints_flagged():
    manifest = {"entityRefs": [], "tagRefs": []}
    issues = intersection_hint_issues(build_intersection_hints(manifest), manifest)
    assert any("intersectionHints < " in i for i in issues), issues


def test_ungrounded_and_offcontract_and_enum_flagged():
    manifest = _MANIFEST
    bad = [
        {"dimension": "content", "source": "entityRef", "actionType": "view_object", "actionTargetId": "entity:景区:稻城亚丁", "tagRefs": [], "label": "稻城亚丁"},
        {"dimension": "xxx", "source": "tagRef", "actionType": "join", "actionTargetId": "Topic/x", "tagRefs": ["Topic/x"], "label": "x", "foo": 1},
    ]
    issues = intersection_hint_issues(bad, manifest)
    assert any("not in manifest.entityRefs" in i for i in issues), issues
    assert any("tag not in manifest.tagRefs" in i for i in issues), issues
    assert any("dimension invalid" in i for i in issues), issues
    assert any("off-contract" in i for i in issues), issues


def _seed_and_materialize() -> Path:
    task = "20260711--travel-article-intersection--test-region-b--pilot-001"
    from support.execution_manifest_fixture import build_execution_fixture

    build_execution_fixture(task)
    ensure_execution_layout(task)
    ensure_execution_command_layout(task, "post")
    post_root = execution_command_root(task, "post")
    import shutil

    posts = post_root / "posts"
    if posts.exists():
        shutil.rmtree(posts)
    ref = "九寨沟"
    source_dir = (
        execution_root(task)
        / "entities/地点/景区/九寨沟/1.download/sources/001-intersection"
    )
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "source.md").write_text(
        "九寨沟看水攻略的测试底稿。" * 80,
        encoding="utf-8",
    )
    write_json(
        source_dir / "meta.json",
        {
            "title": "九寨沟看水攻略",
            "platform": "local_contract",
            "assetCount": 0,
        },
    )
    write_json(source_dir / "assets/index.json", {"assets": []})
    base_source_ref = (
        (source_dir / "source.md").relative_to(execution_root(task)).as_posix()
    )
    from content.post.object_index import register_content_object
    register_content_object(task, ref, content_type="article", angle="攻略", title="九寨沟看水攻略")
    write_stage_result(task, "post", "review", ref, {"decision": "approved"})
    write_stage_result(
        task,
        "post",
        "compose",
        ref,
        {
            "generator": "agent",
            "articleMarkdown": "# 九寨沟看水攻略\n\n正文真实展开，长度足够通过字数门校验。" * 12,
            "title": "九寨沟看水攻略",
            "publishTitle": "九寨沟看水攻略",
            "carrier": "article",
            "baseSourceRef": base_source_ref,
            "publishMediaMode": "text_only",
            "entityRefs": ["/entity/地点/景区/九寨沟"],
            "normalizedEntityRefs": ["entity:景区:九寨沟"],
            "tagRefs": ["主题/山水风光", "Format/内容角度/攻略"],
            "assets": [],
        },
    )
    article = "# 九寨沟看水攻略\n\n正文真实展开，长度足够通过字数门校验。" * 12
    write_agent_draft(
        task,
        ref,
        article,
        model="test-agent/intersection",
        cited_source_paths=[base_source_ref],
        covered_facts=[],
        agent_run_id="run-intersection",
        agent_id="agent-intersection",
    )
    paths = materialize_posts(task, "article")
    assert len(paths) == 1, paths
    return paths[0]


def test_materialize_emits_complete_intersection_hints():
    post_dir = _seed_and_materialize()
    manifest = read_json(post_dir / "manifest.json")
    hints = manifest.get("intersectionHints")
    assert isinstance(hints, list) and hints, "materialize 必须产出 intersectionHints"
    assert manifest.get("normalizedEntityRefs") == ["entity:景区:九寨沟"]
    assert hints[0]["actionTargetId"] == "entity:景区:九寨沟"
    assert intersection_hint_issues(hints, manifest) == []


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"intersection signal tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
