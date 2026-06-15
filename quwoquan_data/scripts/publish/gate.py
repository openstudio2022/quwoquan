"""Exit gate for publish command."""
from __future__ import annotations

import json
from pathlib import Path

from _common.io import read_json
from _common.paths import release_root
from _common.release_integrity import release_integrity_issues

_ROOT_ALLOWED = {"release_manifest.json", "entities", "posts"}
_OBJECT_ALLOWED = {"article.md", "page.md", "_entity.json", "manifest.json", "assets", "5.review"}
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

_IMAGE_SOURCE_ALIASES = {
    "sourceCollectionId": ("sourceCollectionId", "collectionId", "sourceId"),
    "creator": ("creator", "credit"),
    "collectionPageUrl": (
        "collectionPageUrl",
        "page",
        "sourcePage",
        "sourcePageUrl",
        "sourceUrl",
        "url",
    ),
    "license": ("license",),
    "termsUrl": ("termsUrl",),
    "authorizationProof": ("authorizationProof", "licenseProof", "licenseSnapshot"),
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


def _source_fact(payload: dict, field: str):
    for alias in _IMAGE_SOURCE_ALIASES[field]:
        value = payload.get(alias)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict) and value:
            return value
    if field == "collectionPageUrl":
        urls = [str(url).strip() for url in (payload.get("sourceUrls") or []) if str(url).strip()]
        if len(set(urls)) == 1:
            return urls[0]
    legacy_proof = payload.get("licenseProof")
    if isinstance(legacy_proof, dict):
        legacy_key = {
            "license": "license",
            "termsUrl": "termsUrl",
            "authorizationProof": "proofUrl",
        }.get(field)
        if legacy_key:
            value = legacy_proof.get(legacy_key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, dict) and value:
                return value
    return None


def _fact_key(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _post_contract_issues(leaf: Path, root: Path, manifest: dict) -> list[str]:
    rel = leaf.relative_to(root)
    issues: list[str] = []
    is_image = str(manifest.get("contentType") or "") == "image" or str(
        manifest.get("carrier") or ""
    ) in ("image", "gallery")
    article_path = leaf / "article.md"
    gallery_path = leaf / "gallery.md"
    if is_image:
        if article_path.exists() or gallery_path.exists():
            issues.append(f"{rel}: image work must not contain article.md or gallery.md")
        title = manifest.get("title", "")
        caption = manifest.get("caption", "")
        if not isinstance(title, str) or len(title) > 80:
            issues.append(f"{rel}: image title must be a string with at most 80 characters")
        if not isinstance(caption, str) or len(caption) > 300:
            issues.append(f"{rel}: image caption must be a string with at most 300 characters")
        assets = manifest.get("assets")
        if not isinstance(assets, list) or not 1 <= len(assets) <= 20:
            issues.append(f"{rel}: image work must contain 1..20 assets")
            assets = assets if isinstance(assets, list) else []
        source_facts = {
            field: _source_fact(manifest, field)
            for field in _IMAGE_SOURCE_ALIASES
        }
        for field in ("sourceCollectionId", "creator", "collectionPageUrl", "license"):
            value = source_facts[field]
            if value is None:
                issues.append(f"{rel}: image source contract missing {field}")
        if source_facts["termsUrl"] is None and source_facts["authorizationProof"] is None:
            issues.append(
                f"{rel}: image source contract missing license proof "
                "(termsUrl or authorizationProof)"
            )
        for field, work_value in source_facts.items():
            asset_values = [
                value
                for asset in assets
                if isinstance(asset, dict)
                and (value := _source_fact(asset, field)) is not None
            ]
            distinct = {_fact_key(value) for value in asset_values}
            if len(distinct) > 1:
                issues.append(f"{rel}: image assets do not share one {field}")
            elif work_value is not None and distinct and _fact_key(work_value) not in distinct:
                issues.append(f"{rel}: image work {field} conflicts with asset source")
        review_dir = leaf / "5.review"
        for name in ("review.json", "provenance.json"):
            if not (review_dir / name).is_file():
                issues.append(f"{rel}: image review sidecar missing 5.review/{name}")
    else:
        if not article_path.is_file():
            issues.append(f"{rel}: article work missing article.md")
        if gallery_path.exists():
            issues.append(f"{rel}: article work must not contain gallery.md")

    assets = manifest.get("assets") if isinstance(manifest.get("assets"), list) else []
    for asset in assets:
        if not isinstance(asset, dict):
            issues.append(f"{rel}: manifest asset must be an object")
            continue
        caption = asset.get("caption", "")
        if is_image and (not isinstance(caption, str) or len(caption) > 300):
            issues.append(f"{rel}: image asset caption must be a string with at most 300 characters")
        file_name = str(asset.get("fileName") or "")
        if not file_name or not (leaf / "assets" / file_name).is_file():
            issues.append(f"{rel}: asset file missing: assets/{file_name or '<empty>'}")
    return issues


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
            manifest_payload = _payload(manifest)
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
            if base_name == "posts":
                issues.extend(_post_contract_issues(leaf, root, manifest_payload))
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
    content = spec.get("content") or {}
    quotas = (content.get("quotas") or {})
    separated_research = str(content.get("modalityContract") or "") == "separated_research"
    article_q = int(quotas.get("entityArticlesPerTarget") or 0)
    image_q = int(quotas.get("imageWorksPerTarget") or 0)
    if not separated_research and not image_q:
        image_q = int(quotas.get("galleryPostsPerTarget") or 0)
    homepage_q = int(quotas.get("entityHomepagesPerTarget") or 0)
    if separated_research and int(quotas.get("galleryPostsPerTarget") or 0):
        return ["release quota: separated_research must use imageWorksPerTarget, not galleryPostsPerTarget"]
    if not (article_q or image_q or homepage_q):
        return []
    issues: list[str] = []
    entity_pages = list((root / "entities").rglob("page.md")) if (root / "entities").is_dir() else []
    if len(entity_pages) != len(targets) * homepage_q:
        issues.append(
            f"release entity quota: expected {len(targets) * homepage_q}, got {len(entity_pages)}"
        )
    counts = {target: {"article": 0, "image": 0} for target in targets}
    for path in (root / "posts").rglob("manifest.json") if (root / "posts").is_dir() else []:
        data = _payload(path)
        carrier = str(data.get("carrier") or data.get("contentType") or "article")
        kind = "image" if carrier in ("gallery", "image") else "article"
        refs = [str(ref) for ref in (data.get("entityRefs") or [])]
        matched = [target for target in targets if any(ref.rstrip("/").endswith("/" + target) for ref in refs)]
        if len(matched) == 1:
            counts[matched[0]][kind] += 1
    for target, row in counts.items():
        if row["article"] != article_q:
            issues.append(f"{target}: release article quota {article_q}, got {row['article']}")
        if row["image"] != image_q:
            issues.append(f"{target}: release imageWorks quota {image_q}, got {row['image']}")
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
    issues.extend(release_integrity_issues(release_id))
    return issues
