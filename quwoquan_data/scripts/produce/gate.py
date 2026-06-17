"""Exit gate for produce command（对象优先：成品落 batch/posts/{type}/{angle}/{title}/{seq}）。"""
from __future__ import annotations

from pathlib import Path
from collections.abc import Iterable

from _common.io import read_json
from _common.paths import batch_post_roots
from _common.post_verify import verify_posts_root
from _common.release_integrity import scan_runtime_batch_integrity
from _common.stage_reports import iter_stage_envelopes
from media.gate import gate_media_check


def _allowed_post_rels(task_id: str, batch_id: str, refs: Iterable[str] | None) -> set[str]:
    if refs is None:
        return set()
    from _common import content_object

    allowed: set[str] = set()
    for ref in refs:
        try:
            allowed.add(content_object.content_object_rel(task_id, batch_id, str(ref)))
        except KeyError:
            continue
    return allowed


def _content_post_leaves(
    task_id: str,
    batch_id: str,
    content_type: str,
    *,
    refs: Iterable[str] | None = None,
) -> list[Path]:
    """该 content_type 的成品 post 叶子目录（manifest.json + 正文存在），对象优先。"""
    leaves: list[Path] = []
    allowed_rels = _allowed_post_rels(task_id, batch_id, refs)
    for posts_root in batch_post_roots(task_id, batch_id):
        type_root = posts_root / content_type
        if not type_root.is_dir():
            continue
        for manifest_path in sorted(type_root.rglob("manifest.json")):
            pd = manifest_path.parent
            if allowed_rels:
                rel = pd.relative_to(posts_root.parent).as_posix()
                if rel not in allowed_rels:
                    continue
            if (pd / "article.md").exists() or (pd / "gallery.md").exists():
                leaves.append(pd)
            else:
                manifest = read_json(manifest_path)
                if str(manifest.get("carrier") or manifest.get("contentType") or "") in {"image", "gallery"}:
                    leaves.append(pd)
    return leaves


def gate_produce(
    task_id: str,
    batch_id: str,
    content_type: str,
    *,
    refs: Iterable[str] | None = None,
) -> list[str]:
    """Check produce exit criteria."""
    issues: list[str] = []
    allowed = {str(ref) for ref in refs or []}
    allowed_rels = _allowed_post_rels(task_id, batch_id, refs)
    quality_envelopes = [
        row for row in iter_stage_envelopes(task_id, batch_id, "produce", "quality_analysis")
        if not allowed or row[0] in allowed
    ]
    review_envelopes = [
        row for row in iter_stage_envelopes(task_id, batch_id, "produce", "review")
        if not allowed or row[0] in allowed
    ]
    if not quality_envelopes:
        issues.append("No quality_analysis results produced")
    if not review_envelopes:
        issues.append("No review results produced")
    issues.extend(gate_media_check(task_id, batch_id, allow_needs_review=True, refs=allowed or None))

    post_dirs = _content_post_leaves(task_id, batch_id, content_type, refs=refs)
    if not post_dirs:
        issues.append(f"No approved posts produced for type '{content_type}'")
        return issues

    for pd in post_dirs:
        manifest_path = pd / "manifest.json"
        manifest = read_json(manifest_path)
        label = pd.relative_to(pd.parents[3]).as_posix() if len(pd.parents) >= 4 else pd.name
        if not manifest.get("entityRefs"):
            issues.append(f"{label}: no entityRefs")
        if not manifest.get("tagRefs") or len(manifest["tagRefs"]) < 2:
            issues.append(f"{label}: tagRefs < 2")
        if manifest.get("reviewDecision") != "approved":
            issues.append(f"{label}: reviewDecision is not approved")
        if not manifest.get("storySpine"):
            issues.append(f"{label}: missing storySpine")
        if not manifest.get("sourceUrls"):
            issues.append(f"{label}: missing sourceUrls")

    # 发布面质量门统一在对象 posts 根上跑（verify_posts + 语义 + manifest 契约）。
    for posts_root in batch_post_roots(task_id, batch_id):
        issues.extend(
            verify_posts_root(
                posts_root,
                task_id=task_id,
                batch_id=batch_id,
                post_rels=allowed_rels or None,
            )
        )
    runtime_integrity = scan_runtime_batch_integrity(task_id, batch_id, refs=allowed or None)
    issues.extend(str(issue) for issue in runtime_integrity.get("issues") or [])
    return issues
