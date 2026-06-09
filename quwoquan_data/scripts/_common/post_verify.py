"""Post package 校验逻辑库（被 verify CLI / workflow 复用）。

审计语义（标准 CI 模型）：
- scope='current'（门禁默认）：校验 release/ 中的当前 posts 根；
- scope='all'：校验 release/ 下全部 posts 根；
- 显式 task+batch / release：精确校验该目标 posts（runtime 中间批次仅在此显式入口校验）。

注：runtime/tasks/**/batches/**/posts 是临时中间产物，质量由 `produce` 的 review
门禁在产出时强制（不达标即 fail，不落地），不纳入批量审计；需要时用 `--task/--batch` 显式校验。
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

from pathlib import Path

from _common.io import read_json
from _common.paths import RELEASE_ROOT
from _common.schema import validate_result


def _import_verifiers():
    from verify.verify_content_quality import verify_posts  # noqa: WPS433
    from verify.verify_content_semantics import verify_semantics  # noqa: WPS433

    return verify_posts, verify_semantics


def _all_posts_roots(scope: str) -> list[Path]:
    """批量审计只针对交付面 release/；runtime/tasks 中间产物仅显式校验。"""
    roots: list[Path] = []
    if RELEASE_ROOT.exists():
        roots.extend(p for p in sorted(RELEASE_ROOT.rglob("posts")) if p.is_dir())
    return _dedupe(roots)


def _dedupe(roots: list[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for root in roots:
        key = str(root.resolve())
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def resolve_posts_roots(*, task: str | None = None, batch: str | None = None, release: str | None = None, scope: str = "current") -> list[Path]:
    """范围解析见模块 docstring。"""
    roots: list[Path] = []
    explicit = bool((task and batch) or release)
    if task and batch:
        # 对象优先：成品落 batch 根 posts/{type}/{angle}/{title}/{seq}/。
        from _common.paths import batch_root
        pr = batch_root(task, batch) / "posts"
        if pr.is_dir():
            roots.append(pr)
    if release:
        rel = RELEASE_ROOT / release
        roots.extend(p for p in sorted(rel.rglob("posts")) if p.is_dir())
    if explicit:
        return _dedupe(roots)
    # 非显式批量：均针对 release 发布面。
    release_roots = _all_posts_roots(scope)
    return release_roots


def verify_posts_root(posts_root: Path, *, task_id: str | None = None, batch_id: str | None = None) -> list[str]:
    verify_posts, verify_semantics = _import_verifiers()
    issues: list[str] = [str(i) for i in verify_posts(posts_root)]
    try:
        issues.extend(str(i) for i in verify_semantics(posts_root, task_id, batch_id))
    except TypeError:
        issues.extend(str(i) for i in verify_semantics(posts_root))
    for manifest_path in sorted(posts_root.rglob("manifest.json")):
        payload = read_json(manifest_path)
        for error in validate_result(payload, "produce", "post_manifest"):
            issues.append(f"{manifest_path}: {error}")
    return issues


def verify_scope(*, task: str | None = None, batch: str | None = None, release: str | None = None, scope: str = "current") -> tuple[list[Path], list[str]]:
    roots = resolve_posts_roots(task=task, batch=batch, release=release, scope=scope)
    issues: list[str] = []
    for root in roots:
        issues.extend(verify_posts_root(root, task_id=task, batch_id=batch))
    return roots, issues
