"""锁定 verify 审计范围语义：

- 批量审计只针对 release；
- `.qwq_output/data/tasks/<executionId>` 中间产物由执行门禁把关；
- 显式 execution 工作包校验保持严格。

可直接运行：python3 quwoquan_data/tests/user_acceptance/quality/test_verify_scope_semantics__behavior__functional__user_acceptance_test.py
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


from core.io import write_json  # noqa: E402
from core.paths import RELEASE_ROOT, execution_root, ensure_execution_command_layout, ensure_execution_layout  # noqa: E402
from verify import post_verify  # noqa: E402

EXECUTION_ID = "20260711--travel-homepage-scope-semantics--test-region-b--pilot-001"


def _seed_runtime_execution_with_defect() -> Path:
    ensure_execution_layout(EXECUTION_ID)
    ensure_execution_command_layout(EXECUTION_ID, "post")
    posts = execution_root(EXECUTION_ID) / "posts" / "article" / "缺字段帖"
    posts.mkdir(parents=True, exist_ok=True)
    # 缺 topicId / sourcePaths / sourceUrls 等必填，故意制造缺陷
    write_json(posts / "manifest.json", {"contentType": "article", "entityRefs": ["地点/景区/X"], "tagRefs": ["Topic/旅行"]})
    (posts / "article.md").write_text("# 缺字段帖\n\n正文。\n", encoding="utf-8")
    return posts


def test_bulk_audit_excludes_execution_work_packages():
    _seed_runtime_execution_with_defect()
    for scope in ("current", "all"):
        roots = post_verify.resolve_posts_roots(scope=scope)
        for root in roots:
            assert RELEASE_ROOT in root.parents or root.parent == RELEASE_ROOT or str(RELEASE_ROOT) in str(root), (
                f"批量审计 scope={scope} 不应包含非 release 根: {root}"
            )
        assert all("runtime" not in str(r) or "release" in str(r) for r in roots), roots


def test_current_scope_filters_retired_release_schema():
    original_release_root = post_verify.RELEASE_ROOT
    with tempfile.TemporaryDirectory(prefix="release_scope_") as tmp:
        release_root = Path(tmp)
        current_posts = release_root / "current_release" / "posts" / "article" / "攻略" / "当前" / "1"
        retired_posts = release_root / "retired_release" / "posts" / "article" / "攻略" / "旧稿" / "1"
        current_posts.mkdir(parents=True)
        retired_posts.mkdir(parents=True)
        write_json(
            current_posts / "manifest.json",
            {
                "schema": post_verify.CURRENT_POST_MANIFEST_SCHEMA,
                "topicId": "current",
                "contentType": "article",
                "entityRefs": [],
                "normalizedEntityRefs": [],
                "tagRefs": ["Topic/旅行"],
            },
        )
        write_json(
            retired_posts / "manifest.json",
            {
                "topicId": "retired",
                "contentType": "article",
                "entityRefs": [],
                "tagRefs": ["Topic/旅行"],
            },
        )
        post_verify.RELEASE_ROOT = release_root
        try:
            current_roots = post_verify.resolve_posts_roots(scope="current")
            all_roots = post_verify.resolve_posts_roots(scope="all")
        finally:
            post_verify.RELEASE_ROOT = original_release_root

    assert current_roots == [current_posts.parents[3]], current_roots
    assert set(all_roots) == {current_posts.parents[3], retired_posts.parents[3]}, all_roots


def test_explicit_execution_still_strict():
    _seed_runtime_execution_with_defect()
    roots, issues = post_verify.verify_scope(execution_id=EXECUTION_ID, scope="current")
    assert roots, "显式 execution 校验必须定位到中间工作包 posts"
    assert issues, "显式校验中间工作包必须仍能查出缺陷（门禁不放水）"
    assert any("topicId" in i for i in issues), issues


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"verify scope semantics tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
