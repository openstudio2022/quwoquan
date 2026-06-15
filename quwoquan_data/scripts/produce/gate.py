"""Exit gate for produce command（对象优先：成品落 batch/posts/{type}/{angle}/{title}/{seq}）。"""
from __future__ import annotations

from pathlib import Path

from _common.io import read_json
from _common.paths import batch_post_roots
from _common.post_verify import verify_posts_root
from _common.stage_reports import iter_stage_envelopes
from media.gate import gate_media_check


def _content_post_leaves(task_id: str, batch_id: str, content_type: str) -> list[Path]:
    """该 content_type 的成品 post 叶子目录（manifest.json + 正文存在），对象优先。"""
    leaves: list[Path] = []
    for posts_root in batch_post_roots(task_id, batch_id):
        type_root = posts_root / content_type
        if not type_root.is_dir():
            continue
        for manifest_path in sorted(type_root.rglob("manifest.json")):
            pd = manifest_path.parent
            if (pd / "article.md").exists() or (pd / "gallery.md").exists():
                leaves.append(pd)
    return leaves


def gate_produce(task_id: str, batch_id: str, content_type: str) -> list[str]:
    """Check produce exit criteria."""
    issues: list[str] = []
    if not iter_stage_envelopes(task_id, batch_id, "produce", "quality_analysis"):
        issues.append("No quality_analysis results produced")
    if not iter_stage_envelopes(task_id, batch_id, "produce", "review"):
        issues.append("No review results produced")
    issues.extend(gate_media_check(task_id, batch_id, allow_needs_review=True))

    post_dirs = _content_post_leaves(task_id, batch_id, content_type)
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
        issues.extend(verify_posts_root(posts_root, task_id=task_id, batch_id=batch_id))
    return issues
