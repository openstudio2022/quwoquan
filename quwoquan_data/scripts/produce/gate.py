"""Exit gate for produce command."""
from __future__ import annotations

from _common.paths import batch_command_root
from _common.io import read_json


def gate_produce(task_id: str, batch_id: str, content_type: str) -> list[str]:
    """Check produce exit criteria."""
    issues = []
    posts_dir = batch_command_root(task_id, batch_id, "produce") / "posts" / content_type

    if not posts_dir.exists():
        issues.append(f"No posts directory for type '{content_type}'")
        return issues

    post_dirs = [d for d in posts_dir.iterdir() if d.is_dir()]
    if not post_dirs:
        issues.append("No approved posts produced")
        return issues

    for pd in post_dirs:
        manifest_path = pd / "manifest.json"
        if not manifest_path.exists():
            issues.append(f"{pd.name}: missing manifest.json")
            continue
        manifest = read_json(manifest_path)
        if not manifest.get("entityRefs"):
            issues.append(f"{pd.name}: no entityRefs")
        if not manifest.get("tagRefs") or len(manifest["tagRefs"]) < 2:
            issues.append(f"{pd.name}: tagRefs < 2")

    return issues
