"""Exit gate for publish command."""
from __future__ import annotations

from _common.paths import release_root


def gate_publish(release_id: str) -> list[str]:
    """Check release completeness."""
    issues = []
    root = release_root(release_id)

    if not root.exists():
        issues.append(f"Release directory not found: {root}")
        return issues

    manifest_path = root / "release_manifest.json"
    if not manifest_path.exists():
        issues.append("release_manifest.json missing")

    entities_dir = root / "entities"
    if not entities_dir.exists() or not any(entities_dir.rglob("page.md")):
        issues.append("No entity pages found under release/entities")

    posts_dir = root / "posts"
    if not posts_dir.exists() or not any(posts_dir.rglob("manifest.json")):
        issues.append("No posts with manifest.json found")

    return issues
