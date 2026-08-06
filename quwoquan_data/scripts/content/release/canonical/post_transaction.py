"""Build and promote approved post objects through the canonical transaction."""
from __future__ import annotations

import hashlib
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.asset_review_adoption import (
    adopt_independent_asset_review,
)
from content.release.canonical.creator_projection import project_creator_object
from content.release.canonical.image_identity import canonical_asset_manifest_row
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
from content.release.canonical.post_transaction_sources import (
    asset_source_use_mode as _asset_source_use_mode,
)
from content.release.canonical.post_transaction_sources import (
    https_source as _https,
)
from content.release.canonical.post_transaction_sources import (
    source_catalog as _source_catalog,
)
from core.control_types import SourcePolicyRevision
from core.paths import now_iso
from core.source_digest import SourceDigest, SourceDigestError
from governance.coverage.license import (
    RightsAuditStatus,
    parse_rights_audit_status,
    rights_proof_required,
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
    from core.image_decode import probe_image_path

    probe = probe_image_path(path)
    if not probe.succeeded:
        raise ObjectTransactionError(f"post image asset 不可解析：{path}: {probe.failure.value}")
    resolved_mime = probe.mime_type or mime
    if probe.width < 1 or probe.height < 1 or not resolved_mime.startswith("image/"):
        raise ObjectTransactionError(f"post image asset 缺有效尺寸或 MIME：{path}")
    return probe.width, probe.height, resolved_mime


def _source_assets(execution_root: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
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
                source_ref = source_path.relative_to(execution_root).as_posix()
                if source_ref in rows:
                    raise ObjectTransactionError(f"sourceAssetRef 重复：{source_ref}")
                rows[source_ref] = raw
    return rows


def _asset_sources(
    raw: Mapping[str, Any], source_assets: Mapping[str, dict[str, Any]]
) -> tuple[dict[str, Any], ...]:
    refs = [str(raw.get("sourceAssetRef") or "").strip()]
    refs.extend(str(item).strip() for item in raw.get("sourceAssetRefs") or [])
    refs = [ref for ref in refs if ref]
    if not refs:
        raise ObjectTransactionError("post asset 缺 sourceAssetRef 或 sourceAssetRefs")
    missing = [ref for ref in refs if ref not in source_assets]
    if missing:
        raise ObjectTransactionError(
            "post asset sourceAssetRef 未指向来源资产：" + ", ".join(missing)
        )
    return tuple(source_assets[ref] for ref in refs)


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
        source_catalog = _source_catalog(execution_root, source, source_manifest)
        _write_json(object_root / "source_catalog.json", source_catalog)

        source_assets = _source_assets(execution_root)
        cas_rows: list[dict[str, Any]] = []
        asset_refs: list[dict[str, Any]] = []
        rights_rows: list[dict[str, Any]] = []
        canonical_assets: list[dict[str, Any]] = []
        vertical = str(source_manifest.get("vertical") or "").strip()
        if not vertical:
            raise ObjectTransactionError("post manifest 缺 vertical policy owner")
        require_rights_proof = rights_proof_required(vertical)
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
            asset_id = str(raw.get("assetId") or f"asset-{index + 1}").strip()
            independent_review = adopt_independent_asset_review(
                raw_asset=raw,
                related_sources=related_sources,
                asset_kind="video" if mime.startswith("video/") else "image",
                asset_id=asset_id,
                content_sha256=digest,
                object_ref=object_ref,
                execution_root=execution_root,
                execution_manifest=manifest,
                object_root=object_root,
                source_digest=source_digest.digest,
            )
            source_url = _https(
                raw.get("authorizationProof"),
                raw.get("collectionPageUrl"),
                raw.get("sourceUrl"),
                primary_source.get("authorizationProof"),
                primary_source.get("collectionPageUrl"),
                primary_source.get("url"),
                *(source_manifest.get("sourceUrls") or []),
            )
            authorization_proof = _https(
                raw.get("authorizationProof"),
                primary_source.get("authorizationProof"),
            )
            license_url = _https(raw.get("termsUrl"), primary_source.get("termsUrl"))
            author = str(
                raw.get("creator")
                or raw.get("credit")
                or primary_source.get("creator")
                or primary_source.get("credit")
                or ""
            ).strip()
            license_name = str(
                raw.get("license") or primary_source.get("license") or ""
            ).strip()
            fetched_at = str(
                primary_source.get("fetchedAt")
                or source_manifest.get("createdAt")
                or manifest.get("createdAt")
                or ""
            ).strip()
            source_use_mode = _asset_source_use_mode(
                execution_root,
                raw,
            )
            try:
                rights_audit_status = parse_rights_audit_status(
                    raw,
                    primary_source,
                )
            except ValueError as exc:
                raise ObjectTransactionError(
                    f"post asset 缺有效 rightsAuditStatus：{asset_id}"
                ) from exc
            rights_audit_issues = [
                str(issue).strip()
                for issue in (raw.get("rightsAuditIssues") or [])
                if str(issue).strip()
            ]
            if require_rights_proof and rights_audit_issues:
                raise ObjectTransactionError(
                    f"post asset 权利审计仍有未关闭问题：{asset_id}"
                )
            if require_rights_proof and not all(
                (
                    source_url,
                    authorization_proof,
                    license_url,
                    author,
                    license_name,
                    fetched_at,
                )
            ):
                raise ObjectTransactionError(f"post asset 权利字段不完整：{asset_id}")
            if require_rights_proof and rights_audit_status is not RightsAuditStatus.VERIFIED:
                raise ObjectTransactionError(f"post asset 权利状态未经核实：{asset_id}")
            if not require_rights_proof and not all((source_url, fetched_at)):
                raise ObjectTransactionError(f"post asset 权利审计字段不完整：{asset_id}")
            effective_license_name = license_name or "unknown"
            if (
                rights_audit_status is not RightsAuditStatus.VERIFIED
                and not rights_audit_issues
            ):
                raise ObjectTransactionError(
                    f"post asset 非 verified 权利状态缺审计问题：{asset_id}"
                )
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
            usage_scope = str(
                raw.get("usageScope") or primary_source.get("usageScope") or ""
            ).strip()
            model_release_status = str(
                raw.get("modelReleaseStatus")
                or primary_source.get("modelReleaseStatus")
                or ""
            ).strip()
            if usage_scope not in {
                "internal_reference",
                "app_publish",
                "editorial",
            }:
                raise ObjectTransactionError(
                    f"post asset 缺 canonical usageScope：{asset_id}"
                )
            if model_release_status not in {
                "not_required",
                "obtained",
                "editorial_only",
                "verified",
                "unverified",
            }:
                raise ObjectTransactionError(
                    f"post asset 缺 canonical modelReleaseStatus：{asset_id}"
                )
            rights_row = {
                    "assetId": asset_id,
                    "sourceKind": str(primary_source.get("platform") or "source_catalog"),
                    "sourceUseMode": source_use_mode,
                    "canonicalFilePage": source_url,
                    "snapshotUrl": source_url,
                    "pageRevision": _digest_file(snapshot_path),
                    "originalAssetUrl": _https(primary_source.get("url"), source_url),
                    "author": author,
                    "source": _https(raw.get("collectionPageUrl"), primary_source.get("collectionPageUrl"), source_url),
                    "licenseName": effective_license_name,
                    "licenseShortName": effective_license_name,
                    "licenseUrl": license_url,
                    "usageScope": usage_scope,
                    "attribution": (
                        f"{raw.get('caption') or asset_id!s}，"
                        + (
                            f"作者：{author}，许可：{effective_license_name}"
                            if rights_audit_status is RightsAuditStatus.VERIFIED
                            else "来源已记录，作者与许可尚未核实"
                        )
                    ),
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
                    "authorizationProof": authorization_proof,
                    "rightsAuditStatus": rights_audit_status.value,
                    "rightsAuditIssues": rights_audit_issues,
                    "modelReleaseStatus": model_release_status,
                }
            if independent_review is not None:
                rights_row.update(
                    acquisitionReceiptRef=independent_review[
                        "acquisitionReceiptRef"
                    ],
                    independentAssetReview=independent_review,
                )
            rights_rows.append(rights_row)
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
            canonical_assets.append(
                canonical_asset_manifest_row(
                    raw,
                    asset_source=asset_source,
                    mime_type=mime,
                    object_key=object_key,
                )
            )
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
            "sourceTaskId": execution_id,
            "publishedAt": str(source_manifest.get("publishedAt") or "").strip()
            or now_iso(),
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
