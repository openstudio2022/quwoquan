"""Exit gate for publish command."""
from __future__ import annotations

from _common.paths import release_root
from _common.io import read_json, read_ndjson


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

    entities_path = root / "entities" / "entities.ndjson"
    if not entities_path.exists():
        issues.append("entities/entities.ndjson missing")

    tags_path = root / "tags" / "tags.ndjson"
    if not tags_path.exists():
        issues.append("tags/tags.ndjson missing")

    posts_dir = root / "posts"
    if not posts_dir.exists() or not any(posts_dir.rglob("manifest.json")):
        issues.append("No posts with manifest.json found")

    entity_pages_dir = root / "entity_pages"
    if not entity_pages_dir.exists() or not any(entity_pages_dir.iterdir()):
        issues.append("No entity pages found")

    graph_path = root / "graph" / "relations.ndjson"
    if not graph_path.exists():
        issues.append("graph/relations.ndjson missing")

    return issues
