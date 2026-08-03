"""Build immutable releases from exact execution publish closures."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content.execution.identity import parse_execution_id
from content.release.canonical.object_transaction_audit import (
    validate_canonical_publish,
)
from content.release.canonical.object_transaction_contract import (
    RELEASE_SCHEMA,
    ObjectTransactionError,
    _copy_tree,
    _execution_id,
    _now,
    _read_json,
    _safe_id,
    _safe_rel,
    _write_json,
    assert_environment_neutral,
)
from content.release.canonical.creator_commercial_closure import (
    creator_commercial_closure_issues,
)
from content.release.canonical.release_attestation import ReleaseAttestation
from content.release.canonical.release_admission import (
    build_release_asset_admission,
)
from content.release.environment.consistency import scan_release_contract
from content.release.model import DataSourceOwner, ReleaseKind
from core.control_types import ContentType
from core.media_asset_url import (
    build_release_media_manifest,
    copy_release_media_objects,
)
from core.release_layout import (
    attestation_root,
    object_closure_digest,
    payload_digest,
    payload_file,
    payload_root,
)
from core.release_media_binding import bind_release_object_media_assets
from core.schema import assert_valid
from core.source_digest import SourceDigest, SourceDigestError
from governance.coverage.distribution import (
    ProductLifecycleState,
    load_content_distribution_policy,
)

OBJECT_KINDS = ("creators", "entities", "posts", "tags")


@dataclass(frozen=True, slots=True)
class ExecutionPublishClosure:
    execution_id: str
    entity_refs: tuple[str, ...]
    post_refs: tuple[str, ...]
    source_digest: SourceDigest


def _normalized_refs(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ObjectTransactionError(f"{label} must be an array")
    refs = tuple(sorted({_safe_rel(str(item), label=label).as_posix() for item in value}))
    if len(refs) != len(value):
        raise ObjectTransactionError(f"{label} contains duplicate refs")
    return refs


def _execution_publish_closure(
    execution_id: str,
    *,
    publish_root: Path,
) -> ExecutionPublishClosure:
    execution_id = _execution_id(execution_id)
    identity = parse_execution_id(execution_id)
    matched_refs: dict[str, list[str]] = {"entities": [], "posts": []}
    matched_digests: list[SourceDigest] = []
    for kind in ("entities", "posts"):
        objects_root = publish_root / kind
        if not objects_root.is_dir():
            continue
        for manifest_path in sorted(objects_root.rglob("manifest.json")):
            manifest = _read_json(manifest_path)
            if str(manifest.get("executionId") or "") != execution_id:
                continue
            ref = _safe_rel(
                manifest_path.parent.relative_to(objects_root).as_posix(),
                label=f"{kind}Ref",
            ).as_posix()
            try:
                source_digest = SourceDigest.from_document(manifest.get("sourceDigest"))
            except SourceDigestError as exc:
                raise ObjectTransactionError(
                    f"{execution_id}: canonical {kind}/{ref} lacks a valid frozen sourceDigest"
                ) from exc
            matched_refs[kind].append(ref)
            matched_digests.append(source_digest)
    entity_refs = tuple(sorted(matched_refs["entities"]))
    post_refs = tuple(sorted(matched_refs["posts"]))
    if identity.content_type is ContentType.HOMEPAGE and post_refs:
        raise ObjectTransactionError(f"{execution_id}: homepage execution has canonical posts")
    if identity.content_type is not ContentType.HOMEPAGE and entity_refs:
        raise ObjectTransactionError(f"{execution_id}: post execution has canonical entities")
    if identity.content_type is not ContentType.HOMEPAGE:
        for ref in post_refs:
            manifest = _read_json(_object_root(publish_root, "posts", ref) / "manifest.json")
            if str(manifest.get("contentType") or "") != identity.content_type.value:
                raise ObjectTransactionError(
                    f"{execution_id}: canonical post contentType does not match execution identity"
                )
    if not entity_refs and not post_refs:
        raise ObjectTransactionError(f"{execution_id}: canonical publish has no objects bound to this execution")
    source_digests = {item.digest for item in matched_digests}
    if len(source_digests) != 1:
        raise ObjectTransactionError(f"{execution_id}: canonical object source digests drift")
    source_digest = matched_digests[0]
    return ExecutionPublishClosure(execution_id, entity_refs, post_refs, source_digest)


def _object_root(publish_root: Path, kind: str, ref: str) -> Path:
    return publish_root / kind / _safe_rel(ref, label=f"{kind}Ref")


def _object_refs_document(
    publish_root: Path,
    *,
    kind: str,
    ref: str,
    filename: str,
    field: str,
) -> tuple[str, ...]:
    path = _object_root(publish_root, kind, ref) / filename
    if not path.is_file():
        raise ObjectTransactionError(f"canonical {kind}/{ref} missing {filename}")
    return _normalized_refs(
        _read_json(path).get(field),
        label=f"{kind}/{ref}/{filename}.{field}",
    )


def _reference_closure(
    publish_root: Path,
    *,
    entity_refs: set[str],
    post_refs: set[str],
) -> tuple[list[str], list[str]]:
    creator_refs: set[str] = set()
    tag_refs: set[str] = set()
    for kind, refs in (("entities", entity_refs), ("posts", post_refs)):
        for ref in sorted(refs):
            root = _object_root(publish_root, kind, ref)
            if not (root / "manifest.json").is_file():
                raise ObjectTransactionError(f"canonical {kind} object missing: {ref}")
            creator_refs.update(
                _object_refs_document(
                    publish_root,
                    kind=kind,
                    ref=ref,
                    filename="creator.refs.json",
                    field="creatorRefs",
                )
            )
            tag_refs.update(
                _object_refs_document(
                    publish_root,
                    kind=kind,
                    ref=ref,
                    filename="tag.refs.json",
                    field="tagRefs",
                )
            )
    for ref in sorted(creator_refs):
        header = _read_json(_object_root(publish_root, "creators", ref) / "_creator.json")
        if str(header.get("creatorId") or "") != ref:
            raise ObjectTransactionError(f"canonical creator identity mismatch: {ref}")
        tag_refs.update(
            _normalized_refs(
                header.get("tagRefs"),
                label=f"creators/{ref}/_creator.json.tagRefs",
            )
        )
    for ref in sorted(tag_refs):
        if not (_object_root(publish_root, "tags", ref) / "_definition.json").is_file():
            raise ObjectTransactionError(f"canonical tag snapshot missing: {ref}")
    return sorted(creator_refs), sorted(tag_refs)


def _existing_refs(release_root: Path) -> dict[str, list[str]]:
    desired = _read_json(payload_file(release_root, "desired_state.json"))
    refs = desired.get("desiredRefs")
    if not isinstance(refs, dict):
        raise ObjectTransactionError("existing release desiredRefs must be an object")
    return {kind: list(_normalized_refs(refs.get(kind), label=kind)) for kind in OBJECT_KINDS}


def build_aggregate_release(
    *,
    publish_root: Path,
    release_root: Path,
    release_id: str,
    execution_ids: list[str],
) -> dict[str, Any]:
    """Create one immutable release from canonical objects bound to execution IDs."""
    release_id = _safe_id(release_id, label="releaseId")
    closures = tuple(
        _execution_publish_closure(execution_id, publish_root=publish_root) for execution_id in execution_ids
    )
    execution_ids = sorted({closure.execution_id for closure in closures})
    if len(execution_ids) != len(closures):
        raise ObjectTransactionError("aggregate execution IDs are duplicated")
    source_digests = tuple(
        sorted(
            {closure.source_digest for closure in closures},
            key=lambda source_digest: source_digest.digest,
        )
    )
    source_digest_documents = [source_digest.to_document() for source_digest in source_digests]
    entity_refs = {ref for closure in closures for ref in closure.entity_refs}
    post_refs = {ref for closure in closures for ref in closure.post_refs}
    if not entity_refs and not post_refs:
        raise ObjectTransactionError("aggregate release has no canonical object")
    canonical_closure = validate_canonical_publish(publish_root)
    if canonical_closure["status"] != "passed":
        raise ObjectTransactionError(
            "aggregate release canonical closure invalid: "
            + "; ".join(f"{item['code']}:{item['ref']}" for item in canonical_closure["issues"][:5])
        )
    creator_refs, tag_refs = _reference_closure(
        publish_root,
        entity_refs=entity_refs,
        post_refs=post_refs,
    )
    distribution_policy = load_content_distribution_policy()
    creator_issues = creator_commercial_closure_issues(
        publish_root,
        creator_refs=creator_refs,
        require_commercial_rights=(
            distribution_policy.product_lifecycle_state
            is ProductLifecycleState.COMMERCIAL
        ),
    )
    if creator_issues:
        raise ObjectTransactionError(
            "aggregate release creator commercial closure invalid: "
            + "; ".join(
                f"{item['code']}:{item['ref']}" for item in creator_issues[:5]
            )
        )
    desired = {
        "creators": creator_refs,
        "entities": sorted(entity_refs),
        "posts": sorted(post_refs),
        "tags": tag_refs,
    }
    final_root = release_root / release_id
    if final_root.exists():
        header = _read_json(payload_file(final_root, "release.json"))
        aggregate = _read_json(attestation_root(final_root) / "release.json")
        selected_merkle = object_closure_digest(final_root)
        if (
            header.get("releaseId") == release_id
            and sorted(header.get("executionIds") or []) == execution_ids
            and _existing_refs(final_root) == desired
            and header.get("canonicalMerkle") == selected_merkle
            and header.get("releaseKind") == ReleaseKind.CONTENT
            and header.get("releaseClass") == distribution_policy.release_class.value
            and header.get("productLifecycleState")
            == distribution_policy.product_lifecycle_state.value
            and header.get("sourceOwner") == DataSourceOwner.QWQ_DATA
            and header.get("sourceDigests") == source_digest_documents
            and aggregate.get("sourceDigests") == source_digest_documents
            and aggregate.get("sourceOwner") == DataSourceOwner.QWQ_DATA
            and aggregate.get("payloadSha256") == payload_digest(final_root)
        ):
            return {
                "schema": "quwoquan_data.aggregate_release_result",
                "releaseId": release_id,
                "releaseRoot": str(final_root),
                "executionIds": execution_ids,
                "entityCount": len(entity_refs),
                "postCount": len(post_refs),
                "creatorCount": len(creator_refs),
                "canonicalMerkle": selected_merkle,
                "idempotent": True,
            }
        raise ObjectTransactionError(f"aggregate release create-once conflict: {final_root}")

    final_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{release_id}.", dir=final_root.parent))
    try:
        payload = payload_root(staging)
        for kind in OBJECT_KINDS:
            for ref in desired[kind]:
                _copy_tree(
                    _object_root(publish_root, kind, ref),
                    payload / "objects" / kind / ref,
                )
        media_manifest = build_release_media_manifest(
            release_id=release_id,
            post_refs=desired["posts"],
            entity_refs=desired["entities"],
            creator_refs=desired["creators"],
            publish_root=publish_root,
        )
        if media_manifest["issues"]:
            raise ObjectTransactionError(
                "aggregate release media closure invalid: "
                + "; ".join(str(issue) for issue in media_manifest["issues"][:5])
            )
        bind_release_object_media_assets(
            objects_root=payload / "objects",
            manifest=media_manifest,
        )
        asset_admission = build_release_asset_admission(
            release_id=release_id,
            objects_root=payload / "objects",
            desired=desired,
            policy=distribution_policy,
        )
        assert_valid(
            asset_admission,
            "release",
            "release_asset_admission",
            label=f"release_asset_admission:{release_id}",
        )
        _write_json(payload / "asset_admission.json", asset_admission)
        selected_merkle = object_closure_digest(staging, create=True)
        release_header = {
            "schema": RELEASE_SCHEMA,
            "releaseId": release_id,
            "sourceOwner": DataSourceOwner.QWQ_DATA,
            "releaseKind": ReleaseKind.CONTENT,
            "releaseClass": distribution_policy.release_class.value,
            "productLifecycleState": (
                distribution_policy.product_lifecycle_state.value
            ),
            "containsUnverifiedAssets": asset_admission[
                "containsUnverifiedAssets"
            ],
            "rightsStatusCounts": asset_admission["rightsStatusCounts"],
            "authorizationRequiredAssetIds": asset_admission[
                "authorizationRequiredAssetIds"
            ],
            "researchAcceptedCount": asset_admission["researchAcceptedCount"],
            "commercialAcceptedCount": asset_admission[
                "commercialAcceptedCount"
            ],
            "canonicalMerkle": selected_merkle,
            "executionIds": execution_ids,
            "sourceDigests": source_digest_documents,
        }
        desired_state = {
            "schema": "quwoquan_data.release_desired_state",
            "releaseId": release_id,
            "desiredRefs": desired,
        }
        assert_valid(
            release_header,
            "release",
            "release_header",
            label=f"release_header:{release_id}",
        )
        assert_valid(
            desired_state,
            "release",
            "release_desired_state",
            label=f"release_desired_state:{release_id}",
        )
        _write_json(payload / "release.json", release_header)
        _write_json(payload / "desired_state.json", desired_state)
        _write_json(
            payload / "index/objects.json",
            {"schema": "quwoquan_data.release_object_index", **desired},
        )
        _write_json(
            payload / "sample_bundle.json",
            {"schema": "quwoquan_data.release_sample_bundle", **desired},
        )
        copy_release_media_objects(
            manifest=media_manifest,
            source_root=publish_root,
            release_root=staging,
        )
        _write_json(payload / "media_manifest.json", media_manifest)
        consistency = scan_release_contract(
            {
                "schema": "quwoquan_data.release_desired_state",
                "releaseId": release_id,
                "desiredRefs": desired,
            },
            release_root=staging,
            phase="preflight",
        )
        if consistency["status"] != "passed":
            raise ObjectTransactionError(
                "aggregate release consistency invalid: "
                + "; ".join(f"{item['code']}:{item['ref']}" for item in consistency["blockingIssues"][:5])
            )
        release_attestation = ReleaseAttestation(
            release_id=release_id,
            source_owner=DataSourceOwner.QWQ_DATA,
            release_kind=ReleaseKind.CONTENT,
            release_class=distribution_policy.release_class,
            product_lifecycle_state=distribution_policy.product_lifecycle_state,
            contains_unverified_assets=bool(
                asset_admission["containsUnverifiedAssets"]
            ),
            rights_status_counts=dict(asset_admission["rightsStatusCounts"]),
            authorization_required_asset_ids=tuple(
                asset_admission["authorizationRequiredAssetIds"]
            ),
            research_accepted_count=int(asset_admission["researchAcceptedCount"]),
            commercial_accepted_count=int(asset_admission["commercialAcceptedCount"]),
            execution_ids=tuple(execution_ids),
            entity_count=len(entity_refs),
            post_count=len(post_refs),
            creator_count=len(creator_refs),
            tag_count=len(tag_refs),
            canonical_merkle=selected_merkle,
            source_digests=source_digests,
            payload_sha256=payload_digest(staging),
            recorded_at=_now(),
        ).to_document()
        assert_valid(
            release_attestation,
            "release",
            "release_attestation",
            label=f"release_attestation:{release_id}",
        )
        _write_json(attestation_root(staging) / "release.json", release_attestation)
        assert_environment_neutral(staging)
        staging.replace(final_root)
        return {
            "schema": "quwoquan_data.aggregate_release_result",
            "releaseId": release_id,
            "releaseRoot": str(final_root),
            "executionIds": execution_ids,
            "entityCount": len(entity_refs),
            "postCount": len(post_refs),
            "creatorCount": len(creator_refs),
            "canonicalMerkle": selected_merkle,
            "idempotent": False,
        }
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
