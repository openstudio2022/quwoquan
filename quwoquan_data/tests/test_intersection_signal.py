"""交集信号 intersectionHints 红绿测试 ——「明」：讲清推荐理由 + 对齐 IntersectionReason 口径。

覆盖：
- 契约字段对齐：hint 字段集 ⊆ intersection_reason.yaml 的 client_projection.fields。
- build_intersection_hints：entityRefs→content、Topic tag→interest、region→location。
- 完备性门：缺维度/不足条数/枚举非法/锚点悬空/off-contract 字段均报。
- materialize 端到端：产出 manifest.intersectionHints 且完备性门全绿。

可直接运行：python3 quwoquan_data/tests/test_intersection_signal.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

os.environ["QWQ_RUNTIME_ROOT"] = tempfile.mkdtemp()

from _common.intersection_signal import (  # noqa: E402
    HINT_FIELDS,
    build_intersection_hints,
    contract_field_names,
    intersection_hint_issues,
)
from _common.io import read_json, write_json  # noqa: E402
from _common.paths import batch_command_root, ensure_batch_layout, ensure_task_layout  # noqa: E402
from produce.materialize import materialize_posts  # noqa: E402

_MANIFEST = {
    "entityRefs": ["/entity/地点/景区/九寨沟"],
    "tagRefs": ["Topic/旅行/景区", "Format/内容角度/攻略"],
    "conditionContext": {"region": "四川"},
}


def test_hint_fields_align_with_contract():
    contract = contract_field_names()
    assert contract, "必须能读到 intersection_reason.yaml 契约字段"
    assert set(HINT_FIELDS) <= contract, set(HINT_FIELDS) - contract


def test_build_hints_covers_content_interest_location():
    hints = build_intersection_hints(_MANIFEST)
    dims = {h["dimension"] for h in hints}
    assert {"content", "interest", "location"} <= dims, dims
    assert intersection_hint_issues(hints, _MANIFEST) == []


def test_missing_interest_dimension_flagged():
    manifest = {"entityRefs": ["/entity/地点/景区/九寨沟"], "tagRefs": ["Format/内容角度/攻略"]}
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
        {"dimension": "content", "source": "entityRef", "actionType": "view_object", "actionTargetId": "/entity/地点/景区/稻城亚丁", "tagRefs": [], "label": "稻城亚丁"},
        {"dimension": "xxx", "source": "tagRef", "actionType": "join", "actionTargetId": "Topic/x", "tagRefs": ["Topic/x"], "label": "x", "foo": 1},
    ]
    issues = intersection_hint_issues(bad, manifest)
    assert any("not in manifest.entityRefs" in i for i in issues), issues
    assert any("tag not in manifest.tagRefs" in i for i in issues), issues
    assert any("dimension invalid" in i for i in issues), issues
    assert any("off-contract" in i for i in issues), issues


def _seed_and_materialize() -> Path:
    task, batch = "交集信号_gwt", "pilot"
    ensure_task_layout(task)
    ensure_batch_layout(task, batch, "produce")
    produce_root = batch_command_root(task, batch, "produce")
    import shutil

    posts = produce_root / "posts"
    if posts.exists():
        shutil.rmtree(posts)
    review_dir = produce_root / "results" / "review"
    compose_dir = produce_root / "results" / "compose"
    review_dir.mkdir(parents=True, exist_ok=True)
    compose_dir.mkdir(parents=True, exist_ok=True)
    ref = "九寨沟"
    write_json(review_dir / f"{ref}.json", {"ref": ref, "payload": {"decision": "approved"}})
    write_json(
        compose_dir / f"{ref}.json",
        {
            "payload": {
                "generator": "agent",
                "articleMarkdown": "# 九寨沟看水攻略\n\n正文真实展开，长度足够通过字数门校验。" * 12,
                "title": "九寨沟看水攻略",
                "publishTitle": "九寨沟看水攻略",
                "carrier": "article",
                "entityRefs": ["/entity/地点/景区/九寨沟"],
                "tagRefs": ["Topic/旅行/景区", "Format/内容角度/攻略"],
                "conditionContext": {"region": "四川"},
                "assets": [],
            }
        },
    )
    paths = materialize_posts(task, batch, "article")
    assert len(paths) == 1, paths
    return paths[0]


def test_materialize_emits_complete_intersection_hints():
    post_dir = _seed_and_materialize()
    manifest = read_json(post_dir / "manifest.json")
    hints = manifest.get("intersectionHints")
    assert isinstance(hints, list) and hints, "materialize 必须产出 intersectionHints"
    assert intersection_hint_issues(hints, manifest) == []


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"intersection signal tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
