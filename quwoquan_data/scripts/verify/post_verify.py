"""Post package 校验逻辑库（被 verify CLI / workflow 复用）。

审计语义（标准 CI 模型）：
- scope='current'（门禁默认）：校验 release/ 中的当前 posts 根；
- scope='all'：校验 release/ 下全部 posts 根；
- 显式 execution / release：精确校验该目标 posts。

注：data/tasks/<executionId>/posts 是临时中间产物，质量由 post 的 review
门禁在产出时强制（不达标即 fail，不落地），不纳入 release 聚合审计；需要时用 `--execution-id` 显式校验。
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

from core.io import read_json
from core.paths import RELEASE_ROOT
from core.schema import validate_result

CURRENT_POST_MANIFEST_SCHEMA = "quwoquan_data.post_manifest"


def _import_verifiers():
    from verify.verify_content_quality import verify_posts  # noqa: WPS433
    from verify.verify_content_semantics import verify_semantics  # noqa: WPS433

    return verify_posts, verify_semantics


def _all_posts_roots(scope: str) -> list[Path]:
    """聚合审计只针对交付面 release；execution 中间产物仅显式校验。"""
    roots: list[Path] = []
    if RELEASE_ROOT.exists():
        roots.extend(p for p in sorted(RELEASE_ROOT.rglob("posts")) if p.is_dir())
    if scope == "current":
        roots = [root for root in roots if _posts_root_uses_current_schema(root)]
    return _dedupe(roots)


def _posts_root_uses_current_schema(posts_root: Path) -> bool:
    """current scope 只纳入当前 post manifest schema 的 release 根。"""
    manifests = sorted(posts_root.rglob("manifest.json"))
    if not manifests:
        return False
    for manifest_path in manifests:
        try:
            payload = read_json(manifest_path)
        except Exception:
            return False
        if payload.get("schemaVersion") != CURRENT_POST_MANIFEST_SCHEMA:
            return False
    return True


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


def resolve_posts_roots(*, execution_id: str | None = None, release: str | None = None, scope: str = "current") -> list[Path]:
    """范围解析见模块 docstring。"""
    roots: list[Path] = []
    explicit = bool(execution_id or release)
    if execution_id:
        from core.paths import execution_root

        pr = execution_root(execution_id) / "posts"
        if pr.is_dir():
            roots.append(pr)
    if release:
        rel = RELEASE_ROOT / release
        roots.extend(p for p in sorted(rel.rglob("posts")) if p.is_dir())
    if explicit:
        return _dedupe(roots)
    # 非显式校验均针对 release 发布面。
    release_roots = _all_posts_roots(scope)
    return release_roots


def _post_rel(posts_root: Path, post_dir: Path) -> str:
    try:
        return post_dir.relative_to(posts_root.parent).as_posix()
    except ValueError:
        return post_dir.as_posix()


def _post_allowed(posts_root: Path, post_dir: Path, post_rels: set[str] | None) -> bool:
    if post_rels is None:
        return True
    return _post_rel(posts_root, post_dir) in post_rels


def verify_posts_root(
    posts_root: Path,
    *,
    execution_id: str | None = None,
    post_rels: set[str] | None = None,
) -> list[str]:
    verify_posts, verify_semantics = _import_verifiers()
    issues: list[str] = [str(i) for i in verify_posts(posts_root, post_rels=post_rels)]
    issues.extend(
        str(i)
        for i in verify_semantics(
            posts_root,
            execution_id=execution_id,
            post_rels=post_rels,
        )
    )
    for manifest_path in sorted(posts_root.rglob("manifest.json")):
        if not _post_allowed(posts_root, manifest_path.parent, post_rels):
            continue
        payload = read_json(manifest_path)
        for error in validate_result(payload, "content", "post_manifest"):
            issues.append(f"{manifest_path}: {error}")
    return issues


def verify_scope(*, execution_id: str | None = None, release: str | None = None, scope: str = "current") -> tuple[list[Path], list[str]]:
    roots = resolve_posts_roots(execution_id=execution_id, release=release, scope=scope)
    issues: list[str] = []
    for root in roots:
        issues.extend(verify_posts_root(root, execution_id=execution_id))
    return roots, issues
