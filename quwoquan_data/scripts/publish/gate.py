"""Exit gate for publish command."""
from __future__ import annotations

from pathlib import Path

from _common.io import read_json
from _common.paths import release_root

_ROOT_ALLOWED = {"release_manifest.json", "entities", "posts"}
_OBJECT_ALLOWED = {"article.md", "gallery.md", "page.md", "_entity.json", "manifest.json", "assets", "5.review"}
_REVIEW_ALLOWED = {
    "review.json",
    "review_gate.json",
    "ref_review_gate.json",
    "media_check.json",
    "media_check_gate.json",
    "review_ledger.json",
    "review_entities.json",
    "provenance.json",
    "finalization_report.json",
}


def _payload(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = read_json(path)
    except Exception:  # noqa: BLE001
        return {}
    if isinstance(data, dict) and isinstance(data.get("payload"), dict):
        return data["payload"]
    return data if isinstance(data, dict) else {}


def _release_surface_issues(root: Path) -> list[str]:
    issues: list[str] = []
    for child in root.iterdir():
        if child.name not in _ROOT_ALLOWED:
            issues.append(f"release whitelist: unexpected root entry {child.name}")
    for base_name in ("entities", "posts"):
        base = root / base_name
        if not base.is_dir():
            continue
        for manifest in base.rglob("manifest.json"):
            leaf = manifest.parent
            for child in leaf.iterdir():
                if child.name not in _OBJECT_ALLOWED:
                    issues.append(
                        f"release whitelist: unexpected object entry {child.relative_to(root)}"
                    )
            review_dir = leaf / "5.review"
            if review_dir.is_dir():
                for child in review_dir.iterdir():
                    if child.name not in _REVIEW_ALLOWED:
                        issues.append(
                            f"release whitelist: unexpected review sidecar {child.relative_to(root)}"
                        )
                review = _payload(review_dir / "review.json")
                gates = [
                    _payload(review_dir / name)
                    for name in ("review_gate.json", "ref_review_gate.json", "media_check_gate.json")
                    if (review_dir / name).is_file()
                ]
                if str(review.get("decision") or "") == "approved":
                    for gate in gates:
                        if gate.get("passed") is False or gate.get("issues"):
                            issues.append(
                                f"{leaf.relative_to(root)}: approved review conflicts with failing gate"
                            )
                if str(review.get("decision") or "") not in ("", "approved"):
                    issues.append(f"{leaf.relative_to(root)}: review decision is not approved")
    return issues


def _quota_issues(root: Path) -> list[str]:
    manifest = _payload(root / "release_manifest.json")
    task_id = str(manifest.get("sourceTaskId") or "")
    if not task_id:
        return []
    try:
        from task import store

        spec = store.load_spec(task_id)
    except Exception:  # noqa: BLE001
        return []
    targets = [
        str(target.get("name") or "").strip()
        for target in ((spec.get("scope") or {}).get("coverageTargets") or [])
        if str(target.get("name") or "").strip()
    ]
    quotas = ((spec.get("content") or {}).get("quotas") or {})
    article_q = int(quotas.get("entityArticlesPerTarget") or 0)
    gallery_q = int(quotas.get("galleryPostsPerTarget") or 0)
    homepage_q = int(quotas.get("entityHomepagesPerTarget") or 0)
    if not (article_q or gallery_q or homepage_q):
        return []
    issues: list[str] = []
    entity_pages = list((root / "entities").rglob("page.md")) if (root / "entities").is_dir() else []
    if len(entity_pages) != len(targets) * homepage_q:
        issues.append(
            f"release entity quota: expected {len(targets) * homepage_q}, got {len(entity_pages)}"
        )
    counts = {target: {"article": 0, "gallery": 0} for target in targets}
    for path in (root / "posts").rglob("manifest.json") if (root / "posts").is_dir() else []:
        data = _payload(path)
        carrier = str(data.get("carrier") or data.get("contentType") or "article")
        kind = "gallery" if carrier in ("gallery", "image") else "article"
        refs = [str(ref) for ref in (data.get("entityRefs") or [])]
        matched = [target for target in targets if any(ref.rstrip("/").endswith("/" + target) for ref in refs)]
        if len(matched) == 1:
            counts[matched[0]][kind] += 1
    for target, row in counts.items():
        if row["article"] != article_q:
            issues.append(f"{target}: release article quota {article_q}, got {row['article']}")
        if row["gallery"] != gallery_q:
            issues.append(f"{target}: release gallery quota {gallery_q}, got {row['gallery']}")
    return issues


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

    issues.extend(_release_surface_issues(root))
    issues.extend(_quota_issues(root))
    return issues
