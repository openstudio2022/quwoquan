"""Exit gate for publish command."""
from __future__ import annotations

import json
from pathlib import Path

from core.io import read_json
from core.paths import execution_root, release_root
from core.release_layout import payload_file
from content.release.canonical.integrity import release_integrity_issues
from governance.coverage.license import rights_proof_required

_ROOT_ALLOWED = {"release_manifest.json", "evidence_index.json", "entities", "posts"}
_OBJECT_ALLOWED = {
    "article.md",
    "page.md",
    "_entity.json",
    "manifest.json",
    "assets",
    "attestation.json",
    "evidence_index.json",
}

_IMAGE_SOURCE_FIELDS = (
    "sourceCollectionId",
    "creator",
    "collectionPageUrl",
    "license",
    "termsUrl",
    "authorizationProof",
)


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
    execution_id = str(manifest.get("executionId") or "").strip()
    if not execution_id:
        return None
    root = execution_root(execution_id)
    return root if root.is_dir() else None


def _post_kind(manifest: dict) -> str:
    carrier = str(manifest.get("carrier") or manifest.get("contentType") or "article")
    if carrier == "image":
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
    expected: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("ref") or "").strip()
        if not ref:
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


def _source_fact(payload: dict, field: str):
    value = payload.get(field)
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
            for field in _IMAGE_SOURCE_FIELDS
        }
        vertical = str(manifest.get("vertical") or "").strip()
        if not vertical:
            issues.append(f"{rel}: image post missing vertical policy owner")
            return issues
        require_rights_proof = rights_proof_required(vertical)
        required_source_fields = ["sourceCollectionId", "creator", "collectionPageUrl"]
        if require_rights_proof:
            required_source_fields.append("license")
        for field in required_source_fields:
            value = source_facts[field]
            if value is None:
                issues.append(f"{rel}: image source contract missing {field}")
        if (
            require_rights_proof
            and source_facts["termsUrl"] is None
            and source_facts["authorizationProof"] is None
        ):
            issues.append(
                f"{rel}: image source contract missing license proof "
                "(termsUrl or authorizationProof)"
            )
        if not require_rights_proof and str(
            manifest.get("rightsAuditStatus") or ""
        ) not in {"verified", "unverified"}:
            issues.append(f"{rel}: image source contract missing rightsAuditStatus")
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
        for name in ("attestation.json", "evidence_index.json"):
            if not (leaf / name).is_file():
                issues.append(f"{rel}: compact release evidence missing {name}")
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
        assets_by_id = {
            str(asset.get("assetId") or "").strip(): asset
            for asset in assets
            if isinstance(asset, dict) and str(asset.get("assetId") or "").strip()
        }
        for asset in video_assets:
            asset_id = str(asset.get("assetId") or asset.get("fileName") or "<unknown>").strip()
            if not str(asset.get("objectKey") or "").strip():
                issues.append(f"{rel}: video asset {asset_id} missing CAS objectKey")
            poster_id = str(asset.get("posterAssetId") or "").strip()
            poster = assets_by_id.get(poster_id)
            if (
                not poster_id
                or not isinstance(poster, dict)
                or str(poster.get("kind") or "").strip() != "image"
                or str(poster.get("role") or "").strip() != "cover"
            ):
                issues.append(
                    f"{rel}: video asset {asset_id} posterAssetId must resolve to an image cover asset"
                )
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
        for field in ("cdnUrl", "thumbnailUrl", "coverUrl", "videoUrl"):
            if str(asset.get(field) or "").strip():
                issues.append(f"{rel}: canonical asset must not contain environment URL field {field}")
        caption = asset.get("caption", "")
        if is_image and (not isinstance(caption, str) or len(caption) > 300):
            issues.append(f"{rel}: image asset caption must be a string with at most 300 characters")
        file_name = str(asset.get("fileName") or "")
        relative_file = Path(file_name)
        if relative_file.is_absolute() or ".." in relative_file.parts:
            issues.append(f"{rel}: unsafe asset file path: {file_name or '<empty>'}")
            continue
        direct = leaf / relative_file
        nested = leaf / "assets" / relative_file
        if not file_name or (not direct.is_file() and not nested.is_file()):
            issues.append(f"{rel}: asset file missing: {file_name or '<empty>'}")
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
            for evidence_name in ("attestation.json", "evidence_index.json"):
                if not (leaf / evidence_name).is_file():
                    issues.append(
                        f"{leaf.relative_to(root)}: compact release evidence missing {evidence_name}"
                    )
            attestation = _payload(leaf / "attestation.json")
            if str(attestation.get("decision") or "") not in ("", "approved"):
                issues.append(f"{leaf.relative_to(root)}: attestation decision is not approved")
            if base_name == "posts":
                issues.extend(_post_contract_issues(leaf, root, manifest_payload))
    return issues


def _quota_issues(root: Path) -> list[str]:
    manifest = _payload(root / "release_manifest.json")
    execution_id = str(manifest.get("executionId") or "")
    if not execution_id:
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
        if missing:
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
        from content.execution import store

        spec = store.load_spec(execution_id)
    except Exception:  # noqa: BLE001
        return entity_scope_issues
    return entity_scope_issues


def _release_is_homepage_only(root: Path) -> bool:
    """homepage-only release：task 只有主页配额，无 article/image/route 篇目。"""
    manifest = _payload(root / "release_manifest.json")
    execution_id = str(manifest.get("executionId") or "").strip()
    if not execution_id:
        return False
    try:
        from content.execution import store
        from core.execution_branch import is_homepage_only_spec

        return is_homepage_only_spec(store.load_spec(execution_id))
    except Exception:  # noqa: BLE001
        return False


def gate_publish(release_id: str) -> list[str]:
    """Validate the only supported immutable release contract."""
    root = release_root(release_id)
    if not root.exists():
        return [f"Release directory not found: {root}"]
    if not payload_file(root, "desired_state.json").is_file():
        return ["immutable release desired_state.json missing; assembled release is retired"]
    return release_integrity_issues(release_id)
