"""Exit gate for produce command."""
from __future__ import annotations

from _common.paths import batch_command_root
from _common.io import read_json
from _common.post_verify import verify_posts_root


def gate_produce(task_id: str, batch_id: str, content_type: str) -> list[str]:
    """Check produce exit criteria."""
    issues = []
    produce_root = batch_command_root(task_id, batch_id, "produce")
    qa_dir = produce_root / "results" / "quality_analysis"
    review_dir = produce_root / "results" / "review"
    if not qa_dir.exists() or not any(qa_dir.glob("*.json")):
        issues.append("No quality_analysis results produced")
    if not review_dir.exists() or not any(review_dir.glob("*.json")):
        issues.append("No review results produced")
    posts_dir = batch_command_root(task_id, batch_id, "produce") / "posts" / content_type

    if not posts_dir.exists():
        issues.append(f"No posts directory for type '{content_type}'")
        return issues

    post_dirs = [d for d in posts_dir.iterdir() if d.is_dir()]
    if not post_dirs:
        issues.append("No approved posts produced")
        return issues

    for pd in post_dirs:
        # materialize 把成品落在 <post>/<version>/manifest.json（版本子目录）。
        # 兼容两种布局：优先 post 目录顶层，否则取最新版本子目录。
        manifest_path = pd / "manifest.json"
        if not manifest_path.exists():
            version_manifests = sorted(pd.glob("*/manifest.json"))
            if version_manifests:
                manifest_path = version_manifests[-1]
        if not manifest_path.exists():
            issues.append(f"{pd.name}: missing manifest.json")
            continue
        manifest = read_json(manifest_path)
        if not manifest.get("entityRefs"):
            issues.append(f"{pd.name}: no entityRefs")
        if not manifest.get("tagRefs") or len(manifest["tagRefs"]) < 2:
            issues.append(f"{pd.name}: tagRefs < 2")
        if manifest.get("reviewDecision") != "approved":
            issues.append(f"{pd.name}: reviewDecision is not approved")
        if not manifest.get("storySpine"):
            issues.append(f"{pd.name}: missing storySpine")
        if not manifest.get("sourceUrls"):
            issues.append(f"{pd.name}: missing sourceUrls")
    issues.extend(verify_posts_root(posts_dir, task_id=task_id, batch_id=batch_id))

    return issues
