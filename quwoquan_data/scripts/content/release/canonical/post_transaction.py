"""Build and promote approved post objects through the canonical transaction."""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.content_pool_record import (
    append_pool_record,
    build_canonical_pool_record,
    build_content_pool_fields,
)
from content.release.canonical.creator_projection import project_creator_object
from content.release.canonical.image_identity import canonical_asset_manifest_row
from content.release.canonical.object_source_identity import (
    freeze_execution_source_identity,
)
from content.release.canonical.object_transaction_contract import (
    CANONICAL_CONTENT_REVIEW_REF,
    EXPECTED_OBJECT_SCHEMAS,
    LAYOUT_SCHEMA,
    PACKAGE_SCHEMA,
    ObjectTransactionError,
    _closure_digest,
    _digest_file,
    canonical_transaction_id,
    _execution_id,
    _read_json,
    _review_binding,
    _safe_id,
    _safe_rel,
    _tree_digest,
    _write_json,
)
from content.release.canonical.post_asset_identity import (
    freeze_canonical_video_poster_identities,
)
from content.release.canonical.review_rights_binding import validate_review_authority
from content.release.canonical.post_transaction_assets import (
    asset_sources as _asset_sources,
)
from content.release.canonical.post_transaction_assets import (
    source_assets as _source_assets,
)
from content.release.canonical.post_transaction_existing import (
    reuse_existing_post_package,
)
from content.release.canonical.post_transaction_media import (
    _copy_post_surface,
    _creator_ref,
    _final_content_ref,
    _media_dimensions,
    _post_asset_path,
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
from core.content_library import link_from_library
from core.control_types import SourcePolicyRevision
from core.paths import OUTPUT_ROOT, PUBLISH_ROOT, now_iso
from core.tree_integrity import tree_integrity_stats
from governance.coverage.license import (
    RightsAuditStatus,
    parse_rights_audit_status,
)


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
    canonical_target_ref = f"posts/{object_ref.removeprefix('posts/').strip('/')}"
    source_identity = freeze_execution_source_identity(
        execution_root=execution_root,
        execution_manifest=manifest,
        target_ref=canonical_target_ref,
    )
    canonical_ref = _safe_rel(
        object_ref.removeprefix("posts/"), label="objectRef"
    ).as_posix()
    source = execution_root / "posts" / canonical_ref
    source_manifest = _read_json(source / "manifest.json")
    # Pool delivery freezes the reviewed object with the repository-wide Merkle
    # contract.  The transaction must consume that exact digest instead of
    # deriving a second, transaction-private tree identity.
    input_payload_digest = str(tree_integrity_stats(source)["merkleRoot"])
    content_review_source = source / "5.review/content_review.json"
    source_assets = _source_assets(execution_root)
    review_authority = validate_review_authority(
        review_root=content_review_source.parent,
        manifest=source_manifest,
        object_kind="posts",
        execution_id=execution_id,
        object_ref=canonical_target_ref,
        source_assets=source_assets,
    )

    expected_transaction_id = canonical_transaction_id(
        execution_id=execution_id,
        object_kind="posts",
        object_ref=canonical_ref,
    )
    transaction_id = _safe_id(transaction_id, label="transactionId")
    if transaction_id != expected_transaction_id:
        raise ObjectTransactionError(
            f"post transactionId 必须稳定派生：expected={expected_transaction_id}"
        )
    creator_binding = {
        key: source_manifest[key]
        for key in (
            "authorId",
            "creatorProfileId",
            "creatorArchetype",
            "creatorProfileDigest",
            "creatorDisclosure",
            "experienceClaimMode",
            "authorQualitySignals",
            "creator",
        )
        if key in source_manifest
    }
    effective_source_manifest = {**source_manifest, **creator_binding}
    if package_root.exists():
        return reuse_existing_post_package(
            package_root=package_root,
            transaction_id=transaction_id,
            execution_id=execution_id,
            input_payload_digest=input_payload_digest,
            canonical_ref=canonical_ref,
            creator_binding=creator_binding,
            output_root=OUTPUT_ROOT,
        )

    package_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{package_root.name}.", dir=package_root.parent)
    )
    try:
        object_root = staging / "object"
        object_root.mkdir(parents=True)
        _copy_post_surface(source, object_root)
        shutil.copy2(
            content_review_source,
            object_root / CANONICAL_CONTENT_REVIEW_REF,
        )
        source_catalog = _source_catalog(execution_root, source, source_manifest)
        _write_json(object_root / "source_catalog.json", source_catalog)

        cas_rows: list[dict[str, Any]] = []
        asset_refs: list[dict[str, Any]] = []
        rights_rows: list[dict[str, Any]] = []
        canonical_assets: list[dict[str, Any]] = []
        vertical = str(effective_source_manifest.get("vertical") or "").strip()
        if not vertical:
            raise ObjectTransactionError("post manifest 缺 vertical policy owner")
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
            link_from_library(
                asset_source, cas_target, kind="media", expected_sha256=digest_hex
            )
            width, height, mime = _media_dimensions(asset_source, raw)
            related_sources = _asset_sources(raw, source_assets)
            primary_source = related_sources[0] if related_sources else {}
            asset_id = str(raw.get("assetId") or f"asset-{index + 1}").strip()
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
            if (
                rights_audit_status is RightsAuditStatus.VERIFIED
                and not authorization_proof
            ):
                raise ObjectTransactionError(
                    f"post asset verified rights lack authorizationProof：{asset_id}"
                )
            if not all((source_url, fetched_at)):
                raise ObjectTransactionError(
                    f"post asset 权利审计字段不完整：{asset_id}"
                )
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
            distribution_decision = str(
                raw.get("distributionDecision")
                or primary_source.get("distributionDecision")
                or ""
            ).strip()
            if distribution_decision not in {
                "research_allowed",
                "commercial_allowed",
            }:
                raise ObjectTransactionError(
                    f"post asset 缺 canonical distributionDecision：{asset_id}"
                )
            if distribution_decision == "commercial_allowed" and (
                rights_audit_status is not RightsAuditStatus.VERIFIED
                or rights_audit_issues
                or not authorization_proof.startswith("https://")
                or not license_url.startswith("https://")
                or not author
                or not license_name
            ):
                raise ObjectTransactionError(
                    f"asset {asset_id} commercial rights proof is incomplete"
                )
            if source_use_mode == "rights_audit_only":
                raise ObjectTransactionError(
                    f"post asset unresolved sourceUseMode is not publishable：{asset_id}"
                )
            if usage_scope == "internal_reference":
                raise ObjectTransactionError(
                    f"post asset internal_reference scope is not publishable：{asset_id}"
                )
            if (
                rights_audit_status is not RightsAuditStatus.VERIFIED
                or rights_audit_issues
                or not authorization_proof.startswith("https://")
                or not license_url.startswith("https://")
            ):
                raise ObjectTransactionError(
                    f"post asset unresolved rights are not publishable：{asset_id}"
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
                "source": _https(
                    raw.get("collectionPageUrl"),
                    primary_source.get("collectionPageUrl"),
                    source_url,
                ),
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
                "distributionDecision": distribution_decision,
                "rightsAuditStatus": rights_audit_status.value,
                "rightsAuditIssues": rights_audit_issues,
                "modelReleaseStatus": model_release_status,
            }
            rights_rows.append(rights_row)
            cas_rows.append(
                {
                    "sourceRef": cas_ref.as_posix(),
                    "objectKey": object_key,
                    "sha256": digest,
                    "bytes": asset_source.stat().st_size,
                }
            )
            source_asset_refs = sorted(
                {
                    str(raw.get("sourceAssetRef") or "").strip(),
                    *(
                        str(ref or "").strip()
                        for ref in raw.get("sourceAssetRefs") or []
                    ),
                }
                - {""}
            )
            related_receipt_refs = [
                str(source.get("acquisitionReceiptRef") or "").strip()
                for source in related_sources
            ]
            if any(not ref for ref in related_receipt_refs):
                raise ObjectTransactionError(
                    f"post asset source lacks acquisitionReceiptRef：{asset_id}"
                )
            acquisition_receipt_refs = sorted(set(related_receipt_refs))
            derivative_bindings = {
                json.dumps(source["derivativeBinding"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                for source in related_sources
                if isinstance(source.get("derivativeBinding"), Mapping)
            }
            if len(derivative_bindings) > 1:
                raise ObjectTransactionError(
                    f"post asset source derivativeBinding 不唯一：{asset_id}"
                )
            derivative_binding = (
                json.loads(next(iter(derivative_bindings)))
                if derivative_bindings
                else None
            )
            if derivative_binding is not None and (
                derivative_binding.get("derivedSha256") != digest
                or derivative_binding.get("derivedBytes") != asset_source.stat().st_size
                or derivative_binding.get("derivedMimeType") != mime
                or derivative_binding.get("derivedExtension") != asset_source.suffix.lower()
            ):
                raise ObjectTransactionError(
                    f"post asset source derivativeBinding 与发布字节不一致：{asset_id}"
                )
            asset_binding = {
                "assetId": asset_id,
                "objectKey": object_key,
                "sha256": digest,
                "bytes": asset_source.stat().st_size,
                "sourceAssetRefs": source_asset_refs,
                "acquisitionReceiptRefs": acquisition_receipt_refs,
            }
            if derivative_binding is not None:
                asset_binding["derivativeBinding"] = derivative_binding
            asset_refs.append(asset_binding)
            canonical_assets.append(
                canonical_asset_manifest_row(
                    raw,
                    asset_source=asset_source,
                    mime_type=mime,
                    object_key=object_key,
                )
            )
        freeze_canonical_video_poster_identities(canonical_assets)
        publish_media_mode = str(
            effective_source_manifest.get("publishMediaMode") or ""
        ).strip()
        if not cas_rows and publish_media_mode != "text_only":
            raise ObjectTransactionError(
                "post transaction requires at least one rights-bound asset"
            )
        final_content_ref = _final_content_ref(
            object_root,
            holds_media=bool(cas_rows),
        )

        creator_ref = _creator_ref(effective_source_manifest)
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
            {
                str(item).strip()
                for item in effective_source_manifest.get("tagRefs") or []
                if str(item).strip()
            }
        )
        _write_json(object_root / "creator.refs.json", {"creatorRefs": [creator_ref]})
        _write_json(object_root / "tag.refs.json", {"tagRefs": tag_refs})
        _write_json(object_root / "asset.refs.json", {"assets": asset_refs})
        _write_json(
            object_root / "rights.json",
            {
                "schema": "quwoquan_data.asset_rights_closure",
                "publishMediaMode": (
                    "text_only"
                    if publish_media_mode == "text_only"
                    else "embedded_media"
                ),
                "assets": rights_rows,
            },
        )
        pool_fields = build_content_pool_fields(
            source_manifest=effective_source_manifest,
            canonical_ref=canonical_ref,
            source_task_id=execution_id,
            content_review_path=content_review_source,
            rights_authority=review_authority,
            publish_root=PUBLISH_ROOT,
            rights_rows=rights_rows,
            reserved_identity={
                "contentId": source_manifest.get("contentId"),
                "version": source_manifest.get("version", 1),
            },
        )
        canonical_manifest = {
            **effective_source_manifest,
            **pool_fields,
            "schema": EXPECTED_OBJECT_SCHEMAS["posts"],
            "executionId": execution_id,
            "sourceTaskId": execution_id,
            "payloadDigest": input_payload_digest,
            "publishedAt": str(source_manifest.get("publishedAt") or "").strip()
            or now_iso(),
            "sourceIdentity": source_identity,
            "finalContentRef": final_content_ref,
            "sourceCatalogRef": "source_catalog.json",
            "rightsRef": "rights.json",
            "creatorRefsRef": "creator.refs.json",
            "tagRefsRef": "tag.refs.json",
            "assetRefsRef": "asset.refs.json",
            "assets": canonical_assets,
        }
        _write_json(object_root / "manifest.json", canonical_manifest)
        append_pool_record(
            object_root=object_root,
            record=build_canonical_pool_record(
                object_root=object_root,
                object_type="content",
                object_ref=canonical_ref,
            ),
        )
        closure = {
            "creatorRefs": [creator_ref],
            "creatorObjects": [creator_object],
            "tagRefs": tag_refs,
            "sourceCatalogRef": "source_catalog.json",
            "rightsRef": "rights.json",
            "casRefs": cas_rows,
        }
        review = {"contentReviewRef": CANONICAL_CONTENT_REVIEW_REF}
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
            "inputPayloadDigest": input_payload_digest,
            "publishMediaMode": (
                "text_only" if publish_media_mode == "text_only" else "embedded_media"
            ),
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
