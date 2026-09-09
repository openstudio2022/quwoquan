"""Merkle 前置校验下的稳定单对象发布事务。"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.content_pool_record import (
    append_pool_record,
    build_canonical_pool_record,
    pool_usage_scope,
)
from content.release.canonical.entity_transaction_sources import (
    safe_asset_id as _safe_asset_id,
)
from content.release.canonical.entity_transaction_sources import (
    source_asset_for_manifest_asset as _source_asset_for_manifest_asset,
)
from content.release.canonical.entity_transaction_sources import (
    source_assets_by_ref as _source_assets_by_ref,
)
from content.release.canonical.entity_transaction_support import (
    _image_dimensions,
    _project_entity_creator_closure,
)
from content.release.canonical.object_source_identity import (
    freeze_execution_source_identity,
)
from content.release.canonical.object_transaction_contract import (
    CANONICAL_CONTENT_REVIEW_REF,
    LAYOUT_SCHEMA,
    PACKAGE_SCHEMA,
    REQUIRED_SOURCE_POLICY,
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
from content.release.canonical.pool_source_attribution import (
    source_attribution_complete,
)
from content.release.canonical.review_rights_binding import validate_review_authority
from content.release.canonical.canonical_inventory import allocate_package_path
from content.release.canonical.post_transaction_sources import project_object_sources
from core.paths import PUBLISH_ROOT
from core.publish_layout import logical_object_ref
from core.source_attribution import canonical_source_attribution
from governance.coverage.license import (
    RightsAuditStatus,
    parse_rights_audit_status,
)


def build_entity_object_transaction_package(
    *,
    execution_root: Path,
    object_ref: str,
    transaction_id: str,
    package_root: Path,
) -> dict[str, Any]:
    """Build one production transaction package from an approved execution entity.

    The execution work package remains the only process-evidence root.  This builder
    projects one approved entity into a content-addressed, rights-bound transaction
    input without copying runtime stages into canonical content.release.canonical.
    """
    manifest_path = execution_root / "execution_manifest.json"
    execution_manifest = _read_json(manifest_path)
    execution_id = _execution_id(str(execution_manifest.get("executionId") or ""))
    if execution_root.name != execution_id:
        raise ObjectTransactionError("execution root 与 executionId 不一致")
    canonical_target_ref = object_ref.removeprefix("/entity/").strip("/")
    source_identity = freeze_execution_source_identity(
        execution_root=execution_root,
        execution_manifest=execution_manifest,
        target_ref=f"entities/{canonical_target_ref}",
    )
    rel = _safe_rel(object_ref.removeprefix("/entity/"), label="objectRef")
    if len(rel.parts) < 3:
        raise ObjectTransactionError("entity objectRef 必须包含 domain/type/name")
    object_source = execution_root / "entities" / rel
    for required in ("_entity.json", "manifest.json", "page.md"):
        if not (object_source / required).is_file():
            raise ObjectTransactionError(
                f"execution entity 缺 {required}: {object_source}"
            )
    source_manifest = _read_json(object_source / "manifest.json")
    if any(field in source_manifest for field in ("assetRefsRef", "creatorRefsRef", "tagRefsRef")):
        raise ObjectTransactionError("entity manifest contains retired sidecar pointers")
    entity = _read_json(object_source / "_entity.json")
    try:
        source_attribution = canonical_source_attribution(
            entity.get("sourceAttribution")
        )
    except ValueError as exc:
        raise ObjectTransactionError(
            f"entity sourceAttribution invalid: {exc}"
        ) from exc
    if (
        not source_attribution_complete({"sourceAttribution": source_attribution})
        or source_manifest.get("sourceAttribution") != source_attribution
    ):
        raise ObjectTransactionError(
            "entity sourceAttribution is incomplete or drifts from manifest"
        )
    canonical_ref = logical_object_ref(entity, "entities")
    if not str(entity.get("entityId") or ""):
        raise ObjectTransactionError("DATA.POOL.IDENTITY_INVALID: entityId must be frozen by init")
    content_review_source = object_source / "5.review/content_review.json"
    source_assets = _source_assets_by_ref(execution_root)
    review_authority = validate_review_authority(
        review_root=content_review_source.parent,
        manifest=source_manifest,
        object_kind="entity",
        execution_id=execution_id,
        object_ref=f"entities/{canonical_target_ref}",
        source_assets=source_assets,
    )

    expected_transaction_id = canonical_transaction_id(
        execution_id=execution_id,
        object_kind="entities",
        object_ref=rel.as_posix(),
    )
    transaction_id = _safe_id(transaction_id, label="transactionId")
    if transaction_id != expected_transaction_id:
        raise ObjectTransactionError(
            "transactionId 必须由 executionId 与 objectRef 稳定派生："
            f"expected={expected_transaction_id}"
        )
    if package_root.exists():
        existing = _read_json(package_root / "object_transaction_package.json")
        if (
            existing.get("transactionId") == transaction_id
            and existing.get("executionId") == execution_id
        ):
            return existing
        raise ObjectTransactionError(f"对象事务包已存在且输入不一致：{package_root}")

    package_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{package_root.name}.", dir=package_root.parent)
    )
    try:
        object_root = staging / "object"
        object_root.mkdir(parents=True, exist_ok=True)
        shutil.copy2(object_source / "page.md", object_root / "page.md")
        shutil.copy2(
            content_review_source,
            object_root / CANONICAL_CONTENT_REVIEW_REF,
        )

        cas_rows: list[dict[str, Any]] = []
        rights_rows: list[dict[str, Any]] = []
        canonical_assets: list[dict[str, Any]] = []
        vertical = str(source_manifest.get("vertical") or "").strip()
        if not vertical:
            raise ObjectTransactionError("entity manifest 缺 vertical policy owner")
        for raw in source_manifest.get("assets") or []:
            if not isinstance(raw, dict):
                raise ObjectTransactionError("manifest.assets item 必须为 object")
            file_name = str(raw.get("fileName") or "").strip()
            asset_source = object_source / "assets" / file_name
            if not file_name or not asset_source.is_file():
                raise ObjectTransactionError(
                    f"manifest asset 不存在：{file_name or '<empty>'}"
                )
            digest = _digest_file(asset_source)
            hex_digest = digest.removeprefix("sha256:")
            suffix = asset_source.suffix.lower().lstrip(".") or "bin"
            object_key = f"media/objects/sha256/{hex_digest[:2]}/{hex_digest[2:4]}/{hex_digest}.{suffix}"
            media_ref = Path("media") / f"{len(canonical_assets) + 1:02d}.{suffix}"
            cas_ref = Path("object") / media_ref
            cas_target = staging / cas_ref
            cas_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(asset_source, cas_target)
            width, height, mime = _image_dimensions(asset_source)
            asset_id = str(raw.get("assetId") or "").strip()
            source_asset_ref, source_asset = _source_asset_for_manifest_asset(
                raw,
                source_assets,
            )
            source_asset_refs = list(dict.fromkeys([
                *(raw.get("sourceAssetRefs") or []), source_asset_ref,
            ]))
            if any(ref not in source_assets for ref in source_asset_refs):
                raise ObjectTransactionError(f"asset {asset_id} sourceAssetRefs 未指向来源资产")
            related_sources = [source_assets[ref] for ref in source_asset_refs]
            # 来源页优先于许可证页；authorizationProof 只在无任何来源字段时兜底。
            canonical_file_page = str(
                raw.get("collectionPageUrl")
                or source_asset.get("collectionPageUrl")
                or raw.get("sourceUrl")
                or source_asset.get("sourceUrl")
                or source_asset.get("url")
                or raw.get("authorizationProof")
                or source_asset.get("authorizationProof")
                or ""
            ).strip()
            authorization_proof = str(
                raw.get("authorizationProof")
                or source_asset.get("authorizationProof")
                or ""
            ).strip()
            license_url = str(
                raw.get("termsUrl") or source_asset.get("termsUrl") or ""
            ).strip()
            if license_url.startswith("http://"):
                license_url = "https://" + license_url.removeprefix("http://")
            if not canonical_file_page.startswith("https://"):
                raise ObjectTransactionError(f"asset {asset_id} 缺 HTTPS 来源证明")
            fetched_at = str(
                source_asset.get("fetchedAt")
                or (entity.get("primarySource") or {}).get("fetchedAt")
                or execution_manifest.get("createdAt")
                or ""
            )
            author = str(
                raw.get("credit")
                or source_asset.get("credit")
                or source_asset.get("creator")
                or ""
            ).strip()
            license_name = str(
                raw.get("license") or source_asset.get("license") or ""
            ).strip()
            try:
                rights_audit_status = parse_rights_audit_status(raw, source_asset)
            except ValueError as exc:
                raise ObjectTransactionError(
                    f"asset {asset_id} 缺有效 rightsAuditStatus"
                ) from exc
            if not fetched_at:
                raise ObjectTransactionError(f"asset {asset_id} 权利审计字段不完整")
            effective_license_name = license_name or "unknown"
            rights_audit_issues = [
                str(issue)
                for issue in (raw.get("rightsAuditIssues") or [])
                if str(issue).strip()
            ]
            if (
                rights_audit_status is not RightsAuditStatus.VERIFIED
                and not rights_audit_issues
            ):
                raise ObjectTransactionError(
                    f"asset {asset_id} 非 verified 权利状态缺审计问题"
                )
            attribution = f"{raw.get('caption') or asset_id!s}，" + (
                f"作者：{author}，许可：{effective_license_name}"
                if rights_audit_status is RightsAuditStatus.VERIFIED
                else "来源已记录，作者与许可尚未核实"
            )
            usage_scope = str(
                raw.get("usageScope") or source_asset.get("usageScope") or ""
            ).strip()
            model_release_status = str(
                raw.get("modelReleaseStatus")
                or source_asset.get("modelReleaseStatus")
                or ""
            ).strip()
            if usage_scope not in {
                "internal_reference",
                "app_publish",
                "editorial",
            }:
                raise ObjectTransactionError(
                    f"asset {asset_id} 缺 canonical usageScope"
                )
            if model_release_status not in {
                "not_required",
                "obtained",
                "editorial_only",
                "verified",
                "unverified",
            }:
                raise ObjectTransactionError(
                    f"asset {asset_id} 缺 canonical modelReleaseStatus"
                )
            distribution_decision = str(
                raw.get("distributionDecision")
                or source_asset.get("distributionDecision")
                or ""
            ).strip()
            if distribution_decision not in {
                "research_allowed",
                "commercial_allowed",
                "blocked",
            }:
                raise ObjectTransactionError(
                    f"asset {asset_id} 缺 canonical distributionDecision"
                )
            # 权利状态只作记录事实写入 rights.json：非 verified、有审计问题或缺 https 证明
            # 都不拒绝对象，公众可见性由下游运营运行时配置按这些事实决定。
            rights_row = {
                "assetId": asset_id,
                "sourceKind": str(
                    (entity.get("primarySource") or {}).get("sourceKind") or "wikipedia"
                ),
                "sourceUseMode": (
                    "licensed_adaptation"
                    if rights_audit_status is RightsAuditStatus.VERIFIED
                    else "rights_audit_only"
                ),
                "canonicalFilePage": canonical_file_page,
                "snapshotUrl": canonical_file_page,
                "originalAssetUrl": str(
                    raw.get("originalAssetUrl")
                    or source_asset.get("url")
                    or canonical_file_page
                ),
                "author": author,
                "source": str(
                    source_asset.get("collectionPageUrl") or canonical_file_page
                ),
                "licenseName": effective_license_name,
                "licenseShortName": effective_license_name,
                "licenseUrl": license_url,
                "usageScope": usage_scope,
                "attribution": attribution,
                "caption": str(raw.get("caption") or ""),
                "captionSource": "captured source asset metadata",
                "modifications": "homepage materialization resize/crop when applicable",
                "fetchedAt": fetched_at,
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
                **{
                    key: raw[key] if key in raw else source_asset[key]
                    for key in ("commercialAuthorizationStatus", "propertyReleaseStatus", "audioRightsStatus", "derivedModifications", "watermarkNote")
                    if key in raw or key in source_asset
                },
                # 水印判定来自看过像素的 AI 申报（经 ingest 转录到资产行）；缺席只能记 unknown。
                "watermarkStatus": str(raw.get("watermarkStatus") or "unknown"),
                "watermarkKind": str(raw.get("watermarkKind") or "unknown"),
                # 访问政策只转录不判否；缺席即缺席，不补 open。
                **({"accessPolicy": str(raw["accessPolicy"])} if raw.get("accessPolicy") else {}),
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
            receipt_refs = [str(row.get("acquisitionReceiptRef") or "").strip() for row in related_sources]
            if any(not ref for ref in receipt_refs):
                raise ObjectTransactionError(
                    f"asset {asset_id} lacks acquisitionReceiptRef"
                )
            asset_binding = {
                "assetId": asset_id,
                "objectKey": object_key,
                "sha256": digest,
                "bytes": asset_source.stat().st_size,
                "sourceAssetRefs": source_asset_refs,
                "acquisitionReceiptRefs": list(dict.fromkeys(receipt_refs)),
            }
            derivative_binding = source_asset.get("derivativeBinding")
            if isinstance(derivative_binding, Mapping):
                if (
                    derivative_binding.get("derivedSha256") != digest
                    or derivative_binding.get("derivedBytes") != asset_source.stat().st_size
                    or derivative_binding.get("derivedMimeType") != mime
                    or derivative_binding.get("derivedExtension") != asset_source.suffix.lower()
                ):
                    raise ObjectTransactionError(
                        f"asset {asset_id} source derivativeBinding 与发布字节不一致"
                    )
                asset_binding["derivativeBinding"] = dict(derivative_binding)
            canonical_assets.append({
                **{key: value for key, value in raw.items() if key != "sourceAssetRef"},
                **asset_binding,
                "path": media_ref.as_posix(),
                "fileName": media_ref.as_posix(),
                "mimeType": mime,
                "width": width,
                "height": height,
            })

        if not cas_rows and not (
            str(source_manifest.get("contentType") or "") in {"article", "homepage"}
            and str(source_manifest.get("publishMediaMode") or "") == "text_only"
        ):
            raise ObjectTransactionError("non-text-only entity transaction requires an authorized asset")
        tag_refs = sorted(
            {str(item) for item in entity.get("tagRefs") or [] if str(item)}
        )
        creator_refs, creator_objects = _project_entity_creator_closure(
            entity=entity,
            staging=staging,
        )
        if len(creator_refs) != 1:
            raise ObjectTransactionError("entity manifest 缺唯一 creatorProfileId")
        source_refs = project_object_sources(
            execution_root=execution_root, source_object=object_source, object_root=object_root,
            manifest=source_manifest, source_assets=source_assets,
            canonical_assets=canonical_assets, rights_rows=rights_rows,
        )
        entity_id = str(entity["entityId"])
        _write_json(
            object_root / "manifest.json",
            {
                **entity,
                "schema": "quwoquan_data.entity_object",
                "entityId": entity_id,
                "entityRef": str(entity.get("entityRef") or ""),
                "version": 1,
                "executionId": execution_id,
                "sourceIdentity": source_identity,
                "finalContentRef": "page.md",
                "sourceRefs": source_refs,
                "sourceAttribution": source_attribution,
                "creatorProfileId": creator_refs[0],
                "tagRefs": tag_refs,
                "assets": canonical_assets,
                "contentType": "homepage",
                "publishMediaMode": str(source_manifest.get("publishMediaMode") or "not_applicable"),
                "admission": {
                    "processResult": "completed",
                    "qualityResult": "passed",
                    "usageScope": pool_usage_scope(
                        {"sourceAttribution": source_attribution}, rights_rows,
                    ),
                    "rightsResult": "passed",
                    "rightsAuthorityRef": review_authority["ref"],
                    "rightsAuthorityDigest": review_authority["digest"],
                    "evidenceRef": CANONICAL_CONTENT_REVIEW_REF,
                    "evidenceDigest": _digest_file(content_review_source),
                },
                "status": "active",
            },
        )
        append_pool_record(
            object_root=object_root,
            record=build_canonical_pool_record(
                object_root=object_root,
                object_type="homepage",
                object_ref=canonical_ref,
            ),
        )
        closure = {
            "creatorRefs": creator_refs,
            "creatorObjects": creator_objects,
            "tagRefs": tag_refs,
            "sourceRefs": source_refs,
            "casRefs": cas_rows,
        }
        review = {"contentReviewRef": CANONICAL_CONTENT_REVIEW_REF}
        review_binding = _review_binding(object_root, {"review": review})
        closure_digest = _closure_digest(
            object_root=object_root,
            object_kind="entities",
            object_ref=canonical_ref,
            target_schema="quwoquan_data.entity_object",
            source_policy_revision=REQUIRED_SOURCE_POLICY,
            closure=closure,
            cas_rows=cas_rows,
            review=review_binding,
        )
        package = {
            "schema": PACKAGE_SCHEMA,
            "transactionId": transaction_id,
            "executionId": execution_id,
            "publishMediaMode": (
                "text_only"
                if str(source_manifest.get("publishMediaMode") or "") == "text_only"
                else "not_applicable"
            ),
            "sourcePolicyRevision": REQUIRED_SOURCE_POLICY,
            "target": {
                "layoutSchema": LAYOUT_SCHEMA,
                "objectKind": "entities",
                "objectRef": canonical_ref,
                "objectPath": allocate_package_path(PUBLISH_ROOT, _read_json(object_root / "manifest.json"), "entities", object_root),
                "objectSchema": "quwoquan_data.entity_object",
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


__all__ = [
    "_image_dimensions",
    "_project_entity_creator_closure",
    "_tree_digest",
    "build_entity_object_transaction_package",
]
