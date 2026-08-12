"""Merkle 前置校验下的稳定单对象发布事务。"""

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
from content.release.canonical.content_pool_record import (
    append_pool_record,
    build_canonical_pool_record,
)
from content.release.canonical.creator_projection import project_creator_object
from content.release.canonical.entity_transaction_sources import (
    safe_asset_id as _safe_asset_id,
)
from content.release.canonical.entity_transaction_sources import (
    source_asset_for_manifest_asset as _source_asset_for_manifest_asset,
)
from content.release.canonical.entity_transaction_sources import (
    source_assets_by_ref as _source_assets_by_ref,
)
from content.release.canonical.object_source_identity import (
    freeze_execution_source_identity,
)
from content.release.canonical.object_transaction_contract import (
    LAYOUT_SCHEMA,
    PACKAGE_SCHEMA,
    REQUIRED_SOURCE_POLICY,
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
from content.release.canonical.pool_source_attribution import (
    source_attribution_complete,
)
from core.source_attribution import canonical_source_attribution
from core.source_digest import (
    ExecutionBundleIdentity,
    SourceDefinitionSnapshot,
    SourceDigestError,
)
from core.tree_integrity import tree_integrity_stats
from governance.coverage.license import (
    RightsAuditStatus,
    parse_rights_audit_status,
    rights_proof_required,
)


def _project_entity_creator_closure(
    *,
    entity: Mapping[str, Any],
    staging: Path,
) -> tuple[list[str], list[dict[str, object]]]:
    creator_ref = str(entity.get("creatorProfileId") or "").strip()
    if not creator_ref:
        return [], []
    creator_ref = _safe_id(creator_ref, label="creatorProfileId")
    creator_root = project_creator_object(
        creator_ref,
        staging / "creator_objects" / creator_ref,
    )
    return [creator_ref], [
        {
            "creatorRef": creator_ref,
            "packageRef": creator_root.relative_to(staging).as_posix(),
            "treeDigest": _tree_digest(creator_root),
        }
    ]


def _image_dimensions(path: Path) -> tuple[int, int, str]:
    from core.image_decode import probe_image_path

    probe = probe_image_path(path)
    if not probe.succeeded:
        raise ObjectTransactionError(f"发布图片不可解析：{path}: {probe.failure.value}")
    if (
        probe.width <= 0
        or probe.height <= 0
        or not probe.mime_type.startswith("image/")
    ):
        raise ObjectTransactionError(f"发布图片缺有效尺寸或 MIME：{path}")
    return probe.width, probe.height, probe.mime_type


def build_entity_object_transaction_package(
    *,
    execution_root: Path,
    object_ref: str,
    transaction_id: str,
    package_root: Path,
    pool_delivery_intent: Mapping[str, Any],
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
    try:
        source_digest = SourceDefinitionSnapshot.from_document(
            execution_manifest.get("sourceDigest")
        )
        execution_bundle = ExecutionBundleIdentity.from_document(
            execution_manifest.get("executionBundle")
        )
    except SourceDigestError as exc:
        raise ObjectTransactionError(
            f"{execution_id}: execution manifest lacks a valid frozen sourceDigest"
        ) from exc
    source_identity = freeze_execution_source_identity(
        execution_root=execution_root,
        execution_manifest=execution_manifest,
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
        not source_attribution_complete(
            {"sourceAttribution": source_attribution}
        )
        or source_manifest.get("sourceAttribution") != source_attribution
    ):
        raise ObjectTransactionError(
            "entity sourceAttribution is incomplete or drifts from manifest"
        )
    canonical_ref = rel.as_posix()
    if str(entity.get("entityRef") or "").removeprefix("/entity/") != canonical_ref:
        raise ObjectTransactionError("entityRef 与对象路径不一致")
    attestation_source = object_source / "5.review/attestation.json"
    evidence_index_source = object_source / "5.review/evidence_index.json"
    attestation = _read_json(attestation_source)
    if attestation.get("decision") != "approved":
        raise ObjectTransactionError("对象未 review-approved")
    for key in ("deterministicGate", "independentReviewer", "mediaRefReview"):
        if str((attestation.get(key) or {}).get("status") or "") != "passed":
            raise ObjectTransactionError(f"review 前置未通过：{key}")

    expected_transaction_id = (
        f"{execution_id}--entity-"
        f"{hashlib.sha256(canonical_ref.encode('utf-8')).hexdigest()[:12]}"
    )
    transaction_id = _safe_id(transaction_id, label="transactionId")
    if transaction_id != expected_transaction_id:
        raise ObjectTransactionError(
            "transactionId 必须由 executionId 与 objectRef 稳定派生："
            f"expected={expected_transaction_id}"
        )
    from content.execution.closure.pool_delivery import (
        validate_pool_delivery_intent_document,
    )

    try:
        delivery_intent = validate_pool_delivery_intent_document(
            pool_delivery_intent,
            root=execution_root,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise ObjectTransactionError(
            f"pool delivery intent validation failed: {exc}"
        ) from exc
    if (
        delivery_intent.get("executionId") != execution_id
        or delivery_intent.get("carrier") != "homepage"
        or delivery_intent.get("objectRef") != f"/entity/{canonical_ref}"
        or delivery_intent.get("contentObjectDir")
        != f"entities/{canonical_ref}"
        or delivery_intent.get("transactionId") != transaction_id
        or delivery_intent.get("contentId") is not None
        or delivery_intent.get("poolIdentityReservationId") is not None
        or delivery_intent.get("transactionInputDigest")
        != str(tree_integrity_stats(object_source)["merkleRoot"])
    ):
        raise ObjectTransactionError("pool delivery homepage transaction binding drift")
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
        (object_root / "rights_snapshots").mkdir(parents=True, exist_ok=True)
        shutil.copy2(object_source / "_entity.json", object_root / "_entity.json")
        shutil.copy2(object_source / "page.md", object_root / "page.md")
        source_catalog_ref = Path("source_catalog.json")
        source_catalog_source = object_source / "evidence/source_catalog.json"
        if not source_catalog_source.is_file():
            raise ObjectTransactionError("entity 缺 source catalog")
        shutil.copy2(source_catalog_source, object_root / source_catalog_ref)
        shutil.copy2(attestation_source, object_root / "attestation.json")
        shutil.copy2(evidence_index_source, object_root / "evidence_index.json")

        source_assets = _source_assets_by_ref(execution_root)

        cas_rows: list[dict[str, Any]] = []
        asset_refs: list[dict[str, Any]] = []
        rights_rows: list[dict[str, Any]] = []
        canonical_assets: list[dict[str, Any]] = []
        vertical = str(source_manifest.get("vertical") or "").strip()
        if not vertical:
            raise ObjectTransactionError("entity manifest 缺 vertical policy owner")
        require_rights_proof = rights_proof_required(vertical)
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
            cas_ref = Path("cas") / f"{hex_digest}.{suffix}"
            cas_target = staging / cas_ref
            cas_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(asset_source, cas_target)
            width, height, mime = _image_dimensions(asset_source)
            asset_id = str(raw.get("assetId") or "").strip()
            source_asset_ref, source_asset = _source_asset_for_manifest_asset(
                raw,
                source_assets,
            )
            independent_review = adopt_independent_asset_review(
                raw_asset=raw,
                related_sources=(source_asset,),
                asset_kind="image",
                asset_id=asset_id,
                content_sha256=digest,
                object_ref=object_ref,
                execution_root=execution_root,
                execution_manifest=execution_manifest,
                object_root=object_root,
                source_digest=source_digest.digest,
            )
            canonical_file_page = str(
                raw.get("authorizationProof")
                or source_asset.get("authorizationProof")
                or source_asset.get("collectionPageUrl")
                or source_asset.get("sourceUrl")
                or source_asset.get("url")
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
            if require_rights_proof and not license_url.startswith("https://"):
                raise ObjectTransactionError(f"asset {asset_id} 缺 HTTPS 权利证明")
            snapshot_payload = {
                "schema": "quwoquan_data.asset_rights_snapshot",
                "executionId": execution_id,
                "assetId": asset_id,
                "sourceAssetRef": source_asset_ref,
                "sourceAsset": source_asset,
                "manifestAsset": raw,
            }
            snapshot_ref = (
                Path("object/rights_snapshots") / f"{_safe_asset_id(asset_id)}.json"
            )
            _write_json(staging / snapshot_ref, snapshot_payload)
            snapshot_path = staging / snapshot_ref
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
            if require_rights_proof and (
                not author
                or not license_name
                or not fetched_at
                or not authorization_proof.startswith("https://")
            ):
                raise ObjectTransactionError(f"asset {asset_id} 权利字段不完整")
            if (
                require_rights_proof
                and rights_audit_status is not RightsAuditStatus.VERIFIED
            ):
                raise ObjectTransactionError(f"asset {asset_id} 权利状态未经核实")
            if not require_rights_proof and not fetched_at:
                raise ObjectTransactionError(f"asset {asset_id} 权利审计字段不完整")
            effective_license_name = license_name or "unknown"
            rights_audit_issues = [
                str(issue)
                for issue in (raw.get("rightsAuditIssues") or [])
                if str(issue).strip()
            ]
            if (
                not require_rights_proof
                and rights_audit_status is RightsAuditStatus.VERIFIED
                and not authorization_proof
            ):
                rights_audit_status = RightsAuditStatus.UNVERIFIED
                rights_audit_issues.append(
                    "authorizationProof: not independently verified for research distribution"
                )
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
            # Older physical Homepage capsules recorded the exact acquisition
            # and research distribution decision but omitted the equivalent
            # canonical usage vocabulary.  Recover only the narrower research
            # scope from those frozen facts.  This does not upgrade rights:
            # the original audit status/issues remain in the closure, and the
            # commercial lifecycle still requires explicit proof above.
            if (
                not usage_scope
                and not require_rights_proof
                and source_asset.get("acquisitionStatus") == "acquired"
                and source_asset.get("distributionDecision") == "research_allowed"
                and canonical_file_page.startswith("https://")
                and bool(author)
                and bool(license_name)
            ):
                usage_scope = "editorial"
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
            }:
                raise ObjectTransactionError(
                    f"asset {asset_id} 缺 canonical modelReleaseStatus"
                )
            rights_row = {
                    "assetId": asset_id,
                    "sourceKind": str(
                        (entity.get("primarySource") or {}).get("sourceKind")
                        or "wikipedia"
                    ),
                    "sourceUseMode": (
                        "licensed_adaptation"
                        if rights_audit_status is RightsAuditStatus.VERIFIED
                        else "rights_audit_only"
                    ),
                    "canonicalFilePage": canonical_file_page,
                    "snapshotUrl": canonical_file_page,
                    "pageRevision": _digest_file(snapshot_path),
                    "originalAssetUrl": str(
                        source_asset.get("url") or canonical_file_page
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
                {
                    **raw,
                    "objectKey": object_key,
                    "sha256": digest,
                    "bytes": asset_source.stat().st_size,
                }
            )

        if not cas_rows:
            raise ObjectTransactionError("entity 事务至少需要一个已授权发布资产")
        tag_refs = sorted(
            {str(item) for item in entity.get("tagRefs") or [] if str(item)}
        )
        creator_refs, creator_objects = _project_entity_creator_closure(
            entity=entity,
            staging=staging,
        )
        _write_json(object_root / "creator.refs.json", {"creatorRefs": creator_refs})
        _write_json(object_root / "tag.refs.json", {"tagRefs": tag_refs})
        _write_json(object_root / "asset.refs.json", {"assets": asset_refs})
        rights_ref = Path("rights.json")
        _write_json(
            object_root / rights_ref,
            {
                "schema": "quwoquan_data.asset_rights_closure",
                "publishMediaMode": "not_applicable",
                "assets": rights_rows,
            },
        )
        entity_id = "entity:" + ":".join(
            (
                rel.parts[1].strip().replace(" ", "_"),
                "/".join(rel.parts[2:]).strip().replace(" ", "_"),
            )
        )
        _write_json(
            object_root / "manifest.json",
            {
                "schema": "quwoquan_data.entity_object",
                "entityId": entity_id,
                "entityRef": str(entity.get("entityRef") or ""),
                "version": 1,
                "executionId": execution_id,
                "sourceDigest": source_digest.to_document(),
                "executionBundle": execution_bundle.to_document(),
                "sourceIdentity": source_identity,
                "finalContentRef": "page.md",
                "sourceCatalogRef": source_catalog_ref.as_posix(),
                "sourceAttribution": source_attribution,
                "rightsRef": rights_ref.as_posix(),
                "creatorRefsRef": "creator.refs.json",
                "tagRefsRef": "tag.refs.json",
                "assetRefsRef": "asset.refs.json",
                "assets": canonical_assets,
                "admission": {
                    "processResult": "completed",
                    "qualityResult": "passed",
                    "usageScope": "research",
                    "evidenceRef": "attestation.json",
                    "evidenceDigest": _digest_file(attestation_source),
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
            "sourceCatalogRef": source_catalog_ref.as_posix(),
            "rightsRef": rights_ref.as_posix(),
            "casRefs": cas_rows,
        }
        review = {
            "attestationRef": "attestation.json",
            "evidenceIndexRef": "evidence_index.json",
        }
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
            "publishMediaMode": "not_applicable",
            "sourcePolicyRevision": REQUIRED_SOURCE_POLICY,
            "target": {
                "layoutSchema": LAYOUT_SCHEMA,
                "objectKind": "entities",
                "objectRef": canonical_ref,
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
