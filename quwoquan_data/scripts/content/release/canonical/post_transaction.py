"""Build and promote approved post objects through the canonical transaction."""
from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping

from PIL import Image

from core.control_types import SourcePolicyRevision
from core.source_digest import SourceDigest, SourceDigestError
from content.release.canonical.creator_projection import project_creator_object
from content.release.canonical.object_transaction_contract import (
    EXPECTED_OBJECT_SCHEMAS,
    LAYOUT_SCHEMA,
    PACKAGE_SCHEMA,
    ObjectTransactionError,
    _closure_digest,
    _digest_file,
    _execution_id,
    _read_json,
    _review_binding,
    _safe_id,
    _safe_rel,
    _tree_digest,
    _write_json,
)


def _post_asset_path(post_root: Path, raw: Mapping[str, Any]) -> Path:
    file_name = str(raw.get("fileName") or "").strip()
    if not file_name:
        raise ObjectTransactionError("post manifest asset 缺 fileName")
    relative = _safe_rel(file_name, label="manifest.assets.fileName")
    direct = post_root / relative
    nested = post_root / "assets" / relative
    path = direct if direct.is_file() else nested
    if not path.is_file():
        raise ObjectTransactionError(f"post manifest asset 不存在：{file_name}")
    return path


def _media_dimensions(path: Path, raw: Mapping[str, Any]) -> tuple[int, int, str]:
    mime = str(raw.get("mimeType") or "").strip()
    if mime.startswith("video/"):
        width = int(raw.get("width") or 0)
        height = int(raw.get("height") or 0)
        if width < 1 or height < 1:
            raise ObjectTransactionError(f"video asset 缺有效尺寸：{path}")
        return width, height, mime
    try:
        with Image.open(path) as image:
            width, height = image.size
            resolved_mime = str(Image.MIME.get(image.format or "") or mime)
    except (OSError, ValueError) as exc:
        raise ObjectTransactionError(f"post image asset 不可解析：{path}: {exc}") from exc
    if width < 1 or height < 1 or not resolved_mime.startswith("image/"):
        raise ObjectTransactionError(f"post image asset 缺有效尺寸或 MIME：{path}")
    return width, height, resolved_mime


def _source_assets(execution_root: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    ambiguous_ids: set[str] = set()
    for index_path in sorted(execution_root.rglob("assets/index.json")):
        relative_index = index_path.relative_to(execution_root)
        if "sources" not in relative_index.parts:
            continue
        for raw in _read_json(index_path).get("assets") or []:
            if not isinstance(raw, dict):
                continue
            file_name = str(raw.get("fileName") or "").strip()
            if file_name:
                source_path = index_path.parent / _safe_rel(
                    file_name,
                    label=f"{relative_index}.assets.fileName",
                )
                rows[source_path.relative_to(execution_root).as_posix()] = raw
            source_asset_id = str(raw.get("sourceAssetId") or "").strip()
            if source_asset_id and source_asset_id not in ambiguous_ids:
                if source_asset_id in rows and rows[source_asset_id] != raw:
                    rows.pop(source_asset_id, None)
                    ambiguous_ids.add(source_asset_id)
                    continue
                rows[source_asset_id] = raw
    return rows


def _asset_sources(
    raw: Mapping[str, Any], source_assets: Mapping[str, dict[str, Any]]
) -> tuple[dict[str, Any], ...]:
    refs = [str(raw.get("sourceAssetId") or "").strip()]
    refs.extend(str(item).strip() for item in raw.get("sourceAssetRefs") or [])
    return tuple(source_assets[ref] for ref in refs if ref in source_assets)


def _https(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text.startswith("https://"):
            return text
    return ""


def _source_catalog(manifest: Mapping[str, Any]) -> dict[str, Any]:
    urls = tuple(
        dict.fromkeys(
            str(item).strip()
            for item in manifest.get("sourceUrls") or []
            if str(item).strip()
        )
    )
    if not urls:
        raise ObjectTransactionError("post source catalog has no sourceUrls")
    return {
        "schema": "quwoquan_data.source_catalog",
        "sources": [
            {"sourceUrl": url, "sourceUseMode": "licensed_adaptation"}
            for url in urls
        ],
    }


def _copy_post_surface(source: Path, target: Path) -> str:
    for name in ("article.md", "video.md", "provenance.json", "subtitles.vtt"):
        path = source / name
        if path.is_file():
            shutil.copy2(path, target / name)
    assets = source / "assets"
    if assets.is_dir():
        shutil.copytree(assets, target / "assets")
    if (target / "article.md").is_file():
        return "article.md"
    if (target / "assets/video.mp4").is_file():
        return "assets/video.mp4"
    candidates = sorted(path for path in (target / "assets").glob("*") if path.is_file())
    if candidates:
        return candidates[0].relative_to(target).as_posix()
    raise ObjectTransactionError("post object has no final publishable content")


def _creator_ref(manifest: Mapping[str, Any]) -> str:
    ref = str(manifest.get("creatorProfileId") or "").strip()
    if not ref:
        raise ObjectTransactionError("post manifest 缺 creatorProfileId")
    return _safe_id(ref, label="creatorProfileId")


def build_post_object_transaction_package(
    *,
    execution_root: Path,
    object_ref: str,
    transaction_id: str,
    package_root: Path,
) -> dict[str, Any]:
    manifest = _read_json(execution_root / "execution_manifest.json")
    execution_id = _execution_id(str(manifest.get("executionId") or ""))
    if execution_root.name != execution_id:
        raise ObjectTransactionError("execution root 与 executionId 不一致")
    try:
        source_digest = SourceDigest.from_document(manifest.get("sourceDigest"))
    except SourceDigestError as exc:
        raise ObjectTransactionError(
            f"{execution_id}: execution manifest lacks a valid frozen sourceDigest"
        ) from exc
    canonical_ref = _safe_rel(object_ref.removeprefix("posts/"), label="objectRef").as_posix()
    source = execution_root / "posts" / canonical_ref
    source_manifest = _read_json(source / "manifest.json")
    attestation_source = source / "5.review/attestation.json"
    evidence_source = source / "5.review/evidence_index.json"
    attestation = _read_json(attestation_source)
    if attestation.get("decision") != "approved":
        raise ObjectTransactionError("post 未 review-approved")
    for key in ("deterministicGate", "independentReviewer", "mediaRefReview"):
        if str((attestation.get(key) or {}).get("status") or "") != "passed":
            raise ObjectTransactionError(f"post review 前置未通过：{key}")

    expected_transaction_id = (
        f"{execution_id}--post-"
        f"{hashlib.sha256(canonical_ref.encode('utf-8')).hexdigest()[:12]}"
    )
    transaction_id = _safe_id(transaction_id, label="transactionId")
    if transaction_id != expected_transaction_id:
        raise ObjectTransactionError(
            f"post transactionId 必须稳定派生：expected={expected_transaction_id}"
        )
    if package_root.exists():
        existing = _read_json(package_root / "object_transaction_package.json")
        if (
            existing.get("transactionId") == transaction_id
            and existing.get("executionId") == execution_id
        ):
            return existing
        raise ObjectTransactionError(f"post 事务包已存在且输入不一致：{package_root}")

    package_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{package_root.name}.", dir=package_root.parent))
    try:
        object_root = staging / "object"
        object_root.mkdir(parents=True)
        final_content_ref = _copy_post_surface(source, object_root)
        shutil.copy2(attestation_source, object_root / "attestation.json")
        shutil.copy2(evidence_source, object_root / "evidence_index.json")
        _write_json(object_root / "source_catalog.json", _source_catalog(source_manifest))

        source_assets = _source_assets(execution_root)
        cas_rows: list[dict[str, Any]] = []
        asset_refs: list[dict[str, Any]] = []
        rights_rows: list[dict[str, Any]] = []
        canonical_assets: list[dict[str, Any]] = []
        for index, raw_value in enumerate(source_manifest.get("assets") or []):
            if not isinstance(raw_value, Mapping):
                raise ObjectTransactionError("post manifest.assets item 必须为 object")
            raw = dict(raw_value)
            asset_source = _post_asset_path(source, raw)
            digest = _digest_file(asset_source)
            digest_hex = digest.removeprefix("sha256:")
            suffix = asset_source.suffix.lower().lstrip(".") or "bin"
            object_key = (
                f"media/objects/sha256/{digest_hex[:2]}/{digest_hex[2:4]}/"
                f"{digest_hex}.{suffix}"
            )
            cas_ref = Path("cas") / f"{digest_hex}.{suffix}"
            cas_target = staging / cas_ref
            cas_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(asset_source, cas_target)
            width, height, mime = _media_dimensions(asset_source, raw)
            related_sources = _asset_sources(raw, source_assets)
            primary_source = related_sources[0] if related_sources else {}
            source_url = _https(
                primary_source.get("authorizationProof"),
                primary_source.get("collectionPageUrl"),
                primary_source.get("url"),
                raw.get("authorizationProof"),
                *(source_manifest.get("sourceUrls") or []),
            )
            license_url = _https(primary_source.get("termsUrl"), raw.get("termsUrl"))
            author = str(
                primary_source.get("creator")
                or primary_source.get("credit")
                or raw.get("creator")
                or raw.get("credit")
                or ""
            ).strip()
            license_name = str(
                primary_source.get("license") or raw.get("license") or ""
            ).strip()
            fetched_at = str(
                primary_source.get("fetchedAt") or manifest.get("createdAt") or ""
            ).strip()
            asset_id = str(raw.get("assetId") or f"asset-{index + 1}").strip()
            if not all((source_url, license_url, author, license_name, fetched_at)):
                raise ObjectTransactionError(f"post asset 权利字段不完整：{asset_id}")
            snapshot_payload = {
                "schema": "quwoquan_data.asset_rights_snapshot",
                "executionId": execution_id,
                "assetId": asset_id,
                "sourceAssets": list(related_sources),
                "manifestAsset": raw,
            }
            snapshot_ref = Path("object/rights_snapshots") / f"{digest_hex[:20]}.json"
            _write_json(staging / snapshot_ref, snapshot_payload)
            snapshot_path = staging / snapshot_ref
            rights_rows.append(
                {
                    "assetId": asset_id,
                    "sourceKind": str(primary_source.get("platform") or "source_catalog"),
                    "sourceUseMode": "licensed_adaptation",
                    "canonicalFilePage": source_url,
                    "snapshotUrl": source_url,
                    "pageRevision": _digest_file(snapshot_path),
                    "originalAssetUrl": _https(primary_source.get("url"), source_url),
                    "author": author,
                    "source": _https(primary_source.get("collectionPageUrl"), source_url),
                    "licenseName": license_name,
                    "licenseShortName": license_name,
                    "licenseUrl": license_url,
                    "usageScope": "app_publish",
                    "attribution": f"{str(raw.get('caption') or asset_id)}，作者：{author}，{license_name}",
                    "caption": str(raw.get("caption") or ""),
                    "captionSource": "captured source asset metadata",
                    "modifications": "post composition and delivery encoding when applicable",
                    "fetchedAt": fetched_at,
                    "snapshot": {
                        "ref": snapshot_ref.as_posix(),
                        "sha256": _digest_file(snapshot_path),
                        "bytes": snapshot_path.stat().st_size,
                    },
                    "asset": {
                        "ref": cas_ref.as_posix(),
                        "sha256": digest,
                        "bytes": asset_source.stat().st_size,
                        "mimeType": mime,
                        "width": width,
                        "height": height,
                    },
                    "authorizationProof": source_url,
                    "modelReleaseStatus": str(
                        primary_source.get("modelReleaseStatus") or "not_required"
                    ),
                }
            )
            cas_rows.append(
                {
                    "sourceRef": cas_ref.as_posix(),
                    "objectKey": object_key,
                    "sha256": digest,
                    "bytes": asset_source.stat().st_size,
                }
            )
            asset_refs.append(
                {
                    "assetId": asset_id,
                    "objectKey": object_key,
                    "sha256": digest,
                    "bytes": asset_source.stat().st_size,
                }
            )
            canonical_assets.append({**raw, "objectKey": object_key})
        publish_media_mode = str(source_manifest.get("publishMediaMode") or "").strip()
        if not cas_rows and publish_media_mode != "text_only":
            raise ObjectTransactionError("post transaction requires at least one rights-bound asset")

        creator_ref = _creator_ref(source_manifest)
        creator_root = project_creator_object(
            creator_ref,
            staging / "creator_objects" / creator_ref,
        )
        creator_object = {
            "creatorRef": creator_ref,
            "packageRef": creator_root.relative_to(staging).as_posix(),
            "treeDigest": _tree_digest(creator_root),
        }
        tag_refs = sorted(
            {str(item).strip() for item in source_manifest.get("tagRefs") or [] if str(item).strip()}
        )
        _write_json(object_root / "creator.refs.json", {"creatorRefs": [creator_ref]})
        _write_json(object_root / "tag.refs.json", {"tagRefs": tag_refs})
        _write_json(object_root / "asset.refs.json", {"assets": asset_refs})
        _write_json(
            object_root / "rights.json",
            {"schema": "quwoquan_data.asset_rights_closure", "assets": rights_rows},
        )
        canonical_manifest = {
            **source_manifest,
            "schema": EXPECTED_OBJECT_SCHEMAS["posts"],
            "executionId": execution_id,
            "sourceDigest": source_digest.to_document(),
            "finalContentRef": final_content_ref,
            "sourceCatalogRef": "source_catalog.json",
            "rightsRef": "rights.json",
            "creatorRefsRef": "creator.refs.json",
            "tagRefsRef": "tag.refs.json",
            "assetRefsRef": "asset.refs.json",
            "assets": canonical_assets,
        }
        _write_json(object_root / "manifest.json", canonical_manifest)
        closure = {
            "creatorRefs": [creator_ref],
            "creatorObjects": [creator_object],
            "tagRefs": tag_refs,
            "sourceCatalogRef": "source_catalog.json",
            "rightsRef": "rights.json",
            "casRefs": cas_rows,
        }
        review = {
            "attestationRef": "attestation.json",
            "evidenceIndexRef": "evidence_index.json",
        }
        review_binding = _review_binding(object_root, {"review": review})
        source_policy = SourcePolicyRevision.RIGHTS_CLEARED_CONTENT.value
        closure_digest = _closure_digest(
            object_root=object_root,
            object_kind="posts",
            object_ref=canonical_ref,
            target_schema=EXPECTED_OBJECT_SCHEMAS["posts"],
            source_policy_revision=source_policy,
            closure=closure,
            cas_rows=cas_rows,
            review=review_binding,
        )
        package = {
            "schema": PACKAGE_SCHEMA,
            "transactionId": transaction_id,
            "executionId": execution_id,
            "sourcePolicyRevision": source_policy,
            "target": {
                "layoutSchema": LAYOUT_SCHEMA,
                "objectKind": "posts",
                "objectRef": canonical_ref,
                "objectSchema": EXPECTED_OBJECT_SCHEMAS["posts"],
                "packageObjectRef": "object",
            },
            "closure": closure,
            "review": review,
            "objectClosureDigest": closure_digest,
        }
        _write_json(staging / "object_transaction_package.json", package)
        staging.replace(package_root)
        return package
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = ["build_post_object_transaction_package"]
