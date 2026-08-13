"""Build and promote approved post objects through the canonical transaction."""
from __future__ import annotations

import hashlib
import json
import os
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
    build_content_pool_fields,
)
from content.release.canonical.creator_projection import project_creator_object
from content.release.canonical.image_identity import canonical_asset_manifest_row
from content.release.canonical.object_source_identity import (
    freeze_execution_source_identity,
)
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
from content.release.canonical.post_asset_identity import (
    freeze_canonical_video_poster_identities,
)
from content.release.canonical.post_transaction_assets import (
    asset_sources as _asset_sources,
)
from content.release.canonical.post_transaction_assets import (
    source_assets as _source_assets,
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
from core.paths import OUTPUT_ROOT, PUBLISH_ROOT, now_iso
from core.schema import assert_valid
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
    pool_delivery_intent: Mapping[str, Any],
) -> dict[str, Any]:
    manifest = _read_json(execution_root / "execution_manifest.json")
    execution_id = _execution_id(str(manifest.get("executionId") or ""))
    if execution_root.name != execution_id:
        raise ObjectTransactionError("execution root 与 executionId 不一致")
    try:
        source_digest = SourceDefinitionSnapshot.from_document(
            manifest.get("sourceDigest")
        )
        execution_bundle = ExecutionBundleIdentity.from_document(
            manifest.get("executionBundle")
        )
    except SourceDigestError as exc:
        raise ObjectTransactionError(
            f"{execution_id}: execution manifest lacks a valid frozen sourceDigest"
        ) from exc
    source_identity = freeze_execution_source_identity(
        execution_root=execution_root,
        execution_manifest=manifest,
    )
    canonical_ref = _safe_rel(object_ref.removeprefix("posts/"), label="objectRef").as_posix()
    source = execution_root / "posts" / canonical_ref
    source_manifest = _read_json(source / "manifest.json")
    # Pool delivery freezes the reviewed object with the repository-wide Merkle
    # contract.  The transaction must consume that exact digest instead of
    # deriving a second, transaction-private tree identity.
    input_payload_digest = str(tree_integrity_stats(source)["merkleRoot"])
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
    from content.execution.closure.pool_delivery import (
        creator_binding_from_pool_delivery_intent,
    )

    creator_binding = creator_binding_from_pool_delivery_intent(
        source_manifest,
        delivery_intent,
        carrier=str(source_manifest.get("contentType") or "").strip(),
    )
    effective_source_manifest = {**source_manifest, **creator_binding}
    expected_intent_bindings = {
        "executionId": execution_id,
        "contentObjectDir": f"posts/{canonical_ref}",
        "transactionId": transaction_id,
        "transactionInputDigest": input_payload_digest,
        "carrier": str(source_manifest.get("contentType") or "").strip(),
    }
    drifted_bindings = sorted(
        key
        for key, expected in expected_intent_bindings.items()
        if delivery_intent.get(key) != expected
    )
    reservation_id = str(
        delivery_intent.get("poolIdentityReservationId") or ""
    )
    if not reservation_id.startswith("sha256:"):
        drifted_bindings.append("poolIdentityReservationId")
    if drifted_bindings:
        raise ObjectTransactionError(
            "pool delivery intent transaction binding drift: "
            + ",".join(drifted_bindings)
        )
    if package_root.exists():
        existing = _read_json(package_root / "object_transaction_package.json")
        if (
            existing.get("transactionId") == transaction_id
            and existing.get("executionId") == execution_id
            and existing.get("inputPayloadDigest") == input_payload_digest
        ):
            rights_path = package_root / "object/rights.json"
            rights = _read_json(rights_path)
            package_mode = existing.get("publishMediaMode")
            rights_mode = rights.get("publishMediaMode")
            if package_mode is None or rights_mode is None:
                run_root = (
                    OUTPUT_ROOT
                    / "data/local/workspace/object-transactions"
                    / transaction_id
                )
                packaged_manifest = _read_json(package_root / "object/manifest.json")
                closure = existing.get("closure")
                if (
                    (run_root / "audit_report.json").exists()
                    or (run_root / "apply_report.json").exists()
                    or package_mode not in {None, "text_only"}
                    or rights_mode not in {None, "text_only"}
                    or existing.get("target", {}).get("objectKind") != "posts"
                    or existing.get("target", {}).get("objectRef") != canonical_ref
                    or not isinstance(closure, Mapping)
                    or closure.get("rightsRef") != "rights.json"
                    or closure.get("casRefs") != []
                    or packaged_manifest.get("publishMediaMode") != "text_only"
                    or packaged_manifest.get("assets") != []
                    or rights.get("assets") != []
                    or any(
                        packaged_manifest.get(key) != value
                        for key, value in creator_binding.items()
                    )
                ):
                    raise ObjectTransactionError(
                        "DATA.POOL.IDEMPOTENCY_CONFLICT: "
                        "pre-media-mode package contract drift"
                    )
            if rights_mode is None:
                rights = {**rights, "publishMediaMode": "text_only"}
                try:
                    assert_valid(
                        rights,
                        "release",
                        "asset_rights_closure",
                        label="object_transaction_asset_rights_closure",
                    )
                except (ValueError, FileNotFoundError) as exc:
                    raise ObjectTransactionError(str(exc)) from exc
                encoded = (
                    json.dumps(rights, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n"
                ).encode("utf-8")
                temporary = package_root / "object/.rights.json.upgrade"
                descriptor = os.open(
                    temporary,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
                try:
                    with os.fdopen(descriptor, "wb") as handle:
                        handle.write(encoded)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(temporary, rights_path)
                finally:
                    temporary.unlink(missing_ok=True)
            if package_mode is None or rights_mode is None:
                object_root = package_root / "object"
                closure = existing["closure"]
                pool_record_path = object_root / "_pool/versions/1.json"
                pool_record = _read_json(pool_record_path)
                if (
                    pool_record.get("objectId")
                    != packaged_manifest.get("contentId")
                    or pool_record.get("contentVersion")
                    != packaged_manifest.get("version")
                    or pool_record.get("recordSequence") != 1
                ):
                    raise ObjectTransactionError(
                        "DATA.POOL.IDEMPOTENCY_CONFLICT: "
                        "pre-media-mode pool record drift"
                    )
                refreshed_pool_record = build_canonical_pool_record(
                    object_root=object_root,
                    object_type="content",
                    object_ref=canonical_ref,
                )
                refreshed_pool_record["recordSequence"] = 1
                if any(
                    refreshed_pool_record.get(key) != value
                    for key, value in pool_record.items()
                    if key not in {"payloadDigest", "canonicalObjectDigest"}
                ):
                    raise ObjectTransactionError(
                        "DATA.POOL.IDEMPOTENCY_CONFLICT: "
                        "pre-media-mode pool record drift"
                    )
                _write_json(pool_record_path, refreshed_pool_record)
                review_binding = _review_binding(object_root, existing)
                existing = {
                    **existing,
                    "publishMediaMode": "text_only",
                    "objectClosureDigest": _closure_digest(
                        object_root=object_root,
                        object_kind="posts",
                        object_ref=canonical_ref,
                        target_schema=EXPECTED_OBJECT_SCHEMAS["posts"],
                        source_policy_revision=str(
                            existing.get("sourcePolicyRevision") or ""
                        ),
                        closure=closure,
                        cas_rows=[],
                        review=review_binding,
                    ),
                }
                try:
                    assert_valid(
                        existing,
                        "release",
                        "object_transaction_package",
                        label="object_transaction_package",
                    )
                except (ValueError, FileNotFoundError) as exc:
                    raise ObjectTransactionError(str(exc)) from exc
                encoded = (
                    json.dumps(existing, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n"
                ).encode("utf-8")
                package_path = package_root / "object_transaction_package.json"
                temporary = package_root / ".object_transaction_package.json.upgrade"
                descriptor = os.open(
                    temporary,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
                try:
                    with os.fdopen(descriptor, "wb") as handle:
                        handle.write(encoded)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(temporary, package_path)
                finally:
                    temporary.unlink(missing_ok=True)
            return existing
        raise ObjectTransactionError(
            "DATA.POOL.IDEMPOTENCY_CONFLICT: "
            f"sourceTaskId={execution_id} objectId={canonical_ref} payloadDigest drift"
        )

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
        vertical = str(effective_source_manifest.get("vertical") or "").strip()
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
                object_ref=str(source_manifest.get("topicId") or "").strip(),
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
            if (
                not require_rights_proof
                and source_use_mode == "rights_audit_only"
                and rights_audit_status is RightsAuditStatus.VERIFIED
                and not authorization_proof
            ):
                rights_audit_status = RightsAuditStatus.UNVERIFIED
                rights_audit_issues.append(
                    "authorizationProof: not independently verified for research distribution"
                )
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
            # Source units in the research lifecycle are deliberately ingested
            # as rights_audit_only/internal_reference.  A verified independent
            # asset review closes that audit for the immutable research object;
            # project the final rights truth instead of copying intermediate
            # admission vocabulary into the publish closure.
            if (
                rights_audit_status is RightsAuditStatus.VERIFIED
                and source_use_mode == "rights_audit_only"
            ):
                source_use_mode = "licensed_adaptation"
            if usage_scope == "internal_reference":
                usage_scope = "editorial"
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
        freeze_canonical_video_poster_identities(canonical_assets)
        publish_media_mode = str(effective_source_manifest.get("publishMediaMode") or "").strip()
        if not cas_rows and publish_media_mode != "text_only":
            raise ObjectTransactionError("post transaction requires at least one rights-bound asset")

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
            {str(item).strip() for item in effective_source_manifest.get("tagRefs") or [] if str(item).strip()}
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
            attestation_path=attestation_source,
            publish_root=PUBLISH_ROOT,
            rights_rows=rights_rows,
            reserved_identity=delivery_intent,
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
            "sourceDigest": source_digest.to_document(),
            "executionBundle": execution_bundle.to_document(),
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
            "inputPayloadDigest": input_payload_digest,
            "publishMediaMode": (
                "text_only"
                if publish_media_mode == "text_only"
                else "embedded_media"
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
