"""Exit gate for publish command."""
from __future__ import annotations

import json
from pathlib import Path

from _common.io import read_json
from _common.paths import batch_root, release_root
from _common.release_integrity import release_integrity_issues

_ROOT_ALLOWED = {"release_manifest.json", "evidence_index.json", "entities", "posts"}
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


def _source_runtime_root(release_root_path: Path) -> Path | None:
    manifest = _payload(release_root_path / "release_manifest.json")
    task_id = str(manifest.get("sourceTaskId") or "").strip()
    batch_id = str(manifest.get("sourceBatchId") or "").strip()
    if not task_id or not batch_id:
        return None
    root = batch_root(task_id, batch_id)
    return root if root.is_dir() else None


def _abandoned_content_refs(runtime_root: Path | None) -> set[str]:
    if runtime_root is None:
        return set()
    state_path = runtime_root / "_shared" / "task_workflow_state.json"
    if not state_path.is_file():
        return set()
    state = _payload(state_path)
    refs: set[str] = set()
    for item in state.get("abandonedContentObjects") or []:
        if isinstance(item, dict):
            if str(item.get("status") or "").strip() != "abandoned":
                continue
            ref = str(item.get("ref") or "").strip()
            if ref:
                refs.add(ref)
    return refs


def _post_kind(manifest: dict) -> str:
    carrier = str(manifest.get("carrier") or manifest.get("contentType") or "article")
    if carrier in {"gallery", "image"}:
        return "image"
    if carrier == "video":
        return "video"
    return "article"


def _planned_post_refs(runtime_root: Path | None) -> dict[str, str] | None:
    if runtime_root is None:
        return None
    packet_path = runtime_root / "_shared" / "content_plan_packet.json"
    if not packet_path.is_file():
        return None
    packet = _payload(packet_path)
    items = packet.get("items")
    if not isinstance(items, list):
        return None
    abandoned = _abandoned_content_refs(runtime_root)
    expected: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("ref") or "").strip()
        if not ref or ref in abandoned:
            continue
        expected[ref] = _post_kind(item)
    return expected


def _post_refs_in_release(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    posts_root = root / "posts"
    for path in posts_root.rglob("manifest.json") if posts_root.is_dir() else []:
        data = _payload(path)
        ref = str(data.get("topicId") or data.get("ref") or "").strip()
        if not ref:
            continue
        out[ref] = _post_kind(data)
    return out


def _entity_rel_from_ref(raw: object) -> str:
    text = str(raw or "").strip().strip("/")
    if not text:
        return ""
    if text.startswith("entity/"):
        parts = text.split("/")
        if len(parts) >= 4:
            return (Path("entities") / parts[1] / parts[2] / "/".join(parts[3:])).as_posix()
    if text.startswith("entities/"):
        return text
    return ""


def _primary_entity_rels_in_release_posts(root: Path) -> set[str]:
    out: set[str] = set()
    posts_root = root / "posts"
    for path in posts_root.rglob("manifest.json") if posts_root.is_dir() else []:
        data = _payload(path)
        refs = data.get("entityRefs") or []
        if not isinstance(refs, list) or not refs:
            continue
        rel = _entity_rel_from_ref(refs[0])
        if rel:
            out.add(rel)
    return out


def _entity_rels_in_release(root: Path) -> set[str]:
    entities_root = root / "entities"
    if not entities_root.is_dir():
        return set()
    return {
        path.parent.relative_to(root).as_posix()
        for path in entities_root.rglob("page.md")
    }


def _release_entity_scope_issues(root: Path) -> list[str]:
    expected = _primary_entity_rels_in_release_posts(root)
    if not expected:
        return []
    actual = _entity_rels_in_release(root)
    issues: list[str] = []
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        issues.append(
            "release missing primary entity homepage(s): "
            + ", ".join(missing[:20])
            + (" ..." if len(missing) > 20 else "")
        )
    if extra:
        issues.append(
            "release contains entity homepage(s) outside primary post refs: "
            + ", ".join(extra[:20])
            + (" ..." if len(extra) > 20 else "")
        )
    if len(actual) != len(expected):
        issues.append(f"release entity quota: expected {len(expected)}, got {len(actual)}")
    return issues


def _partial_publish_allowed(root: Path) -> bool:
    manifest = _payload(root / "release_manifest.json")
    task_id = str(manifest.get("sourceTaskId") or "").strip()
    if not task_id:
        return True
    try:
        from task import store

        spec = store.load_spec(task_id)
    except Exception:  # noqa: BLE001
        return True
    policy = spec.get("workflowPolicy") if isinstance(spec.get("workflowPolicy"), dict) else {}
    return bool(policy.get("allowPartialContent", True) is not False)


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
    kind = _post_kind(manifest)
    is_image = kind == "image"
    is_video = kind == "video"
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
    elif is_video:
        if article_path.exists() or gallery_path.exists():
            issues.append(f"{rel}: video work must not contain article.md or gallery.md")
        assets = manifest.get("assets")
        if not isinstance(assets, list) or not assets:
            issues.append(f"{rel}: video work must contain at least one asset")
            assets = assets if isinstance(assets, list) else []
        video_assets = [
            asset
            for asset in assets
            if isinstance(asset, dict) and str(asset.get("kind") or "").strip() == "video"
        ]
        if not video_assets:
            issues.append(f"{rel}: video work must contain a kind=video asset")
        for asset in video_assets:
            asset_id = str(asset.get("assetId") or asset.get("fileName") or "<unknown>").strip()
            has_video_ref = any(
                str(asset.get(field) or "").strip()
                for field in ("cdnUrl", "objectKey", "videoUrl", "videoAssetId")
            )
            if not has_video_ref:
                issues.append(f"{rel}: video asset {asset_id} missing videoUrl/objectKey/cdnUrl")
            has_cover_ref = any(
                str(asset.get(field) or "").strip()
                for field in ("thumbnailUrl", "coverUrl")
            )
            if not has_cover_ref:
                issues.append(f"{rel}: video asset {asset_id} missing thumbnailUrl or coverUrl")
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
    entity_scope_issues = _release_entity_scope_issues(root)
    runtime_root = _source_runtime_root(root)
    planned = _planned_post_refs(runtime_root)
    if planned is not None:
        actual = _post_refs_in_release(root)
        issues: list[str] = list(entity_scope_issues)
        missing = sorted(set(planned) - set(actual))
        extra = sorted(set(actual) - set(planned))
        wrong_type = sorted(
            ref for ref in set(planned) & set(actual)
            if planned.get(ref) != actual.get(ref)
        )
        if missing and not _partial_publish_allowed(root):
            issues.append(
                "release missing planned post ref(s): "
                + ", ".join(missing[:20])
                + (" ..." if len(missing) > 20 else "")
            )
        if extra:
            issues.append(
                "release contains post ref(s) outside effective content_plan: "
                + ", ".join(extra[:20])
                + (" ..." if len(extra) > 20 else "")
            )
        for ref in wrong_type[:20]:
            issues.append(
                f"{ref}: release carrier {actual.get(ref)} != planned {planned.get(ref)}"
            )
        return issues
    try:
        from task import store

        spec = store.load_spec(task_id)
    except Exception:  # noqa: BLE001
        return entity_scope_issues
    content = spec.get("content") or {}
    quotas = (content.get("quotas") or {})
    separated_research = str(content.get("modalityContract") or "") == "separated_research"
    if separated_research and int(quotas.get("galleryPostsPerTarget") or 0):
        return ["release quota: separated_research must use imageWorksPerTarget, not galleryPostsPerTarget"]
    return entity_scope_issues


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

    posts_dir = root / "posts"
    if not posts_dir.exists() or not any(posts_dir.rglob("manifest.json")):
        issues.append("No posts with manifest.json found")

    issues.extend(_release_surface_issues(root))
    issues.extend(_quota_issues(root))
    issues.extend(release_integrity_issues(release_id))
    return issues
