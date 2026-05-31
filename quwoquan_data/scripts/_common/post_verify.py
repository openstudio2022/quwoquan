"""Post package 校验逻辑库（被 verify CLI / 旧 verify 薄壳 / pipeline 复用）。

审计语义（标准 CI 模型：批量门禁针对**交付面 release/**，中间产物在 produce 时由 review
门禁把关、并可按需显式校验；不删数据、不伪造来源）：
- scope='current'（门禁默认）：校验 release/ 中**当前 schema**的 posts 根（pre-schema release 透明 skip）；
- scope='all'：校验 release/ 下全部 posts 根（含旧 schema release，作为发布面审计）；
- 显式 task+batch / release：精确校验该目标 posts（runtime 中间批次仅在此显式入口校验）。

注：runtime/tasks/**/batches/**/produce/posts 是临时中间产物，质量由 `produce` 的 review
门禁在产出时强制（不达标即 fail，不落地），不纳入批量审计；需要时用 `--task/--batch` 显式校验。
"""
from __future__ import annotations

from pathlib import Path

from _common.article_package import MARKDOWN_VERSION
from _common.io import read_json
from _common.paths import RELEASE_ROOT, batch_command_root
from _common.schema import validate_result


def _import_verifiers():
    from verify_content_quality import verify_posts  # noqa: WPS433
    from verify_content_semantics import verify_semantics  # noqa: WPS433

    return verify_posts, verify_semantics


def _is_current_schema_root(posts_root: Path) -> bool:
    manifests = list(posts_root.rglob("manifest.json"))
    if not manifests:
        return False
    for manifest_path in manifests:
        data = read_json(manifest_path)
        if data.get("articleMarkdownVersion") != MARKDOWN_VERSION:
            return False
    return True


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


def legacy_posts_roots(scope: str = "all") -> list[Path]:
    """返回 pre-schema 遗留 posts 根（无当前 articleMarkdownVersion），用于透明审计上报。"""
    return [root for root in _all_posts_roots(scope) if not _is_current_schema_root(root)]


def resolve_posts_roots(*, task: str | None = None, batch: str | None = None, release: str | None = None, scope: str = "current") -> list[Path]:
    """范围解析见模块 docstring。"""
    roots: list[Path] = []
    explicit = bool((task and batch) or release)
    if task and batch:
        pr = batch_command_root(task, batch, "produce") / "posts"
        if pr.is_dir():
            roots.append(pr)
    if release:
        rel = RELEASE_ROOT / release
        roots.extend(p for p in sorted(rel.rglob("posts")) if p.is_dir())
    if explicit:
        return _dedupe(roots)
    # 非显式批量：均针对 release 发布面。current 过滤当前 schema（旧 schema release 另行 skip 上报）；
    # all 校验全部 release posts（含旧 schema release）。
    release_roots = _all_posts_roots(scope)
    if scope == "all":
        return release_roots
    return [root for root in release_roots if _is_current_schema_root(root)]


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
