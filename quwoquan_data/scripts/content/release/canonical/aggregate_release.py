"""Build immutable releases from exact execution publish closures."""
from __future__ import annotations

import shutil
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.control_types import ContentType, EXECUTION_MILESTONES, RolloutMilestone
from core.media_asset_url import build_release_media_manifest, copy_release_media_objects
from core.release_layout import (
    attestation_root,
    object_closure_digest,
    payload_digest,
    payload_file,
    payload_root,
)
from core.schema import assert_valid
from core.source_digest import SourceDigest, SourceDigestError, current_source_digest
from core.tree_integrity import tree_integrity_stats
from governance.coverage.cold_start_supply import load_cold_start_supply_policy
from content.execution.identity import parse_execution_id
from content.release.canonical.object_transaction_audit import validate_canonical_publish
from content.release.canonical.release_attestation import ReleaseAttestation
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
from content.release.canonical.two_province_closure import expected_entity_refs
from content.release.environment.consistency import scan_release_contract
from content.release.model import ReleaseKind


OBJECT_KINDS = ("creators", "entities", "posts", "tags")
CONTENT_MILESTONES = (*EXECUTION_MILESTONES, RolloutMilestone.LAUNCH)


@dataclass(frozen=True, slots=True)
class ExecutionPublishClosure:
    execution_id: str
    entity_refs: tuple[str, ...]
    post_refs: tuple[str, ...]
    source_digest: SourceDigest


def _normalized_refs(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ObjectTransactionError(f"{label} must be an array")
    refs = tuple(
        sorted({_safe_rel(str(item), label=label).as_posix() for item in value})
    )
    if len(refs) != len(value):
        raise ObjectTransactionError(f"{label} contains duplicate refs")
    return refs


def _execution_publish_closure(
    root: Path,
    *,
    publish_root: Path,
) -> ExecutionPublishClosure:
    manifest = _read_json(root / "execution_manifest.json")
    execution_id = _execution_id(str(manifest.get("executionId") or ""))
    if root.name != execution_id:
        raise ObjectTransactionError("aggregate execution root identity mismatch")
    publish_ref = _read_json(root / "publish_ref.json")
    try:
        assert_valid(
            publish_ref,
            "execution",
            "publish_ref",
            label=f"publish_ref:{execution_id}",
        )
    except (FileNotFoundError, ValueError) as exc:
        raise ObjectTransactionError(str(exc)) from exc
    if publish_ref.get("executionId") != execution_id:
        raise ObjectTransactionError(f"{execution_id}: publish_ref identity mismatch")
    refs = publish_ref["publishedRefs"]
    entity_refs = _normalized_refs(
        refs["entities"], label=f"{execution_id}.publishedRefs.entities"
    )
    post_refs = _normalized_refs(
        refs["posts"], label=f"{execution_id}.publishedRefs.posts"
    )
    identity = parse_execution_id(execution_id)
    if identity.content_type is ContentType.HOMEPAGE and post_refs:
        raise ObjectTransactionError(f"{execution_id}: homepage execution published posts")
    if identity.content_type is not ContentType.HOMEPAGE and entity_refs:
        raise ObjectTransactionError(f"{execution_id}: post execution published entities")
    if identity.content_type is not ContentType.HOMEPAGE:
        actual_mix = _post_content_mix(publish_root, set(post_refs))
        if set(actual_mix) != {identity.content_type}:
            raise ObjectTransactionError(
                f"{execution_id}: published post contentType does not match execution identity"
            )
    if not entity_refs and not post_refs:
        raise ObjectTransactionError(f"{execution_id}: publish_ref has no canonical objects")
    try:
        source_digest = SourceDigest.from_document(manifest.get("sourceDigest"))
    except SourceDigestError as exc:
        raise ObjectTransactionError(f"{execution_id}: {exc}") from exc
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


def _post_content_mix(publish_root: Path, post_refs: set[str]) -> Counter[ContentType]:
    actual_mix: Counter[ContentType] = Counter()
    for ref in sorted(post_refs):
        manifest = _read_json(_object_root(publish_root, "posts", ref) / "manifest.json")
        try:
            actual_mix[ContentType(str(manifest.get("contentType") or ""))] += 1
        except ValueError as exc:
            raise ObjectTransactionError(f"post contentType invalid: {ref}") from exc
    return actual_mix


def _assert_launch_contract(
    publish_root: Path,
    *,
    entity_refs: set[str],
    post_refs: set[str],
) -> None:
    expected_entities = set().union(*expected_entity_refs().values())
    if entity_refs != expected_entities:
        raise ObjectTransactionError(
            "launch entity closure must exactly equal Zhejiang/Sichuan master coverage: "
            f"actual={len(entity_refs)} expected={len(expected_entities)}"
        )
    policy = load_cold_start_supply_policy()
    if len(post_refs) != policy.expected_post_count:
        raise ObjectTransactionError(
            "launch post closure does not match cold-start policy: "
            f"actual={len(post_refs)} expected={policy.expected_post_count}"
        )
    actual_mix = _post_content_mix(publish_root, post_refs)
    target_count = len(policy.targets)
    expected_mix = {
        ContentType.ARTICLE: target_count * policy.content_mix.article,
        ContentType.IMAGE: target_count * policy.content_mix.image,
        ContentType.VIDEO: target_count * policy.content_mix.video,
    }
    if dict(actual_mix) != expected_mix:
        raise ObjectTransactionError(
            f"launch post content mix mismatch: actual={dict(actual_mix)} expected={expected_mix}"
        )


def _assert_canary_supply_contract(
    publish_root: Path,
    *,
    entity_refs: set[str],
    post_refs: set[str],
) -> None:
    """canary release = 全部金丝雀主页 + 每个金丝雀实体 article/image/video 各一篇。"""
    from content.release.canonical.rollout_contract import load_rollout_contract

    contract = load_rollout_contract()
    expected_entities = {
        ref
        for province in contract.provinces
        for ref in province.canary_entity_refs
    }
    if entity_refs != expected_entities:
        raise ObjectTransactionError(
            "canary entity closure must exactly equal the rollout canary targets: "
            f"actual={sorted(entity_refs)} expected={sorted(expected_entities)}"
        )
    policy = load_cold_start_supply_policy()
    canary_target_count = sum(
        len(province.canary_targets) for province in contract.provinces
    )
    expected_total = canary_target_count * policy.content_mix.total_per_entity
    if len(post_refs) != expected_total:
        raise ObjectTransactionError(
            "canary post closure does not match the canary cold-start supply: "
            f"actual={len(post_refs)} expected={expected_total}"
        )
    actual_mix = _post_content_mix(publish_root, post_refs)
    expected_mix = {
        ContentType.ARTICLE: canary_target_count * policy.content_mix.article,
        ContentType.IMAGE: canary_target_count * policy.content_mix.image,
        ContentType.VIDEO: canary_target_count * policy.content_mix.video,
    }
    if dict(actual_mix) != expected_mix:
        raise ObjectTransactionError(
            f"canary post content mix mismatch: actual={dict(actual_mix)} expected={expected_mix}"
        )


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
    execution_roots: list[Path],
    rollout_milestone: str,
) -> dict[str, Any]:
    """Create one immutable release from exact execution publish refs."""
    release_id = _safe_id(release_id, label="releaseId")
    try:
        milestone = RolloutMilestone(str(rollout_milestone or "").strip())
    except ValueError as exc:
        raise ObjectTransactionError("rolloutMilestone is invalid") from exc
    if milestone not in CONTENT_MILESTONES:
        raise ObjectTransactionError("rolloutMilestone is not a content milestone")
    closures = tuple(
        _execution_publish_closure(root, publish_root=publish_root)
        for root in execution_roots
    )
    execution_ids = sorted({closure.execution_id for closure in closures})
    if len(execution_ids) != len(closures):
        raise ObjectTransactionError("aggregate execution roots are duplicated")
    source_digests = {closure.source_digest.digest for closure in closures}
    if len(source_digests) != 1:
        raise ObjectTransactionError("aggregate execution source digests drift")
    source_digest = closures[0].source_digest
    if source_digest != current_source_digest():
        raise ObjectTransactionError(
            "aggregate execution source digest does not match the frozen repository inputs"
        )
    entity_refs = {ref for closure in closures for ref in closure.entity_refs}
    post_refs = {ref for closure in closures for ref in closure.post_refs}
    if not entity_refs and not post_refs:
        raise ObjectTransactionError("aggregate release has no canonical object")
    if milestone is RolloutMilestone.LAUNCH:
        _assert_launch_contract(publish_root, entity_refs=entity_refs, post_refs=post_refs)
    elif milestone is RolloutMilestone.CANARY:
        _assert_canary_supply_contract(
            publish_root, entity_refs=entity_refs, post_refs=post_refs
        )

    canonical_closure = validate_canonical_publish(publish_root)
    if canonical_closure["status"] != "passed":
        raise ObjectTransactionError(
            "aggregate release canonical closure invalid: "
            + "; ".join(
                f"{item['code']}:{item['ref']}" for item in canonical_closure["issues"][:5]
            )
        )
    creator_refs, tag_refs = _reference_closure(
        publish_root,
        entity_refs=entity_refs,
        post_refs=post_refs,
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
        aggregate = _read_json(attestation_root(final_root) / "aggregate.json")
        selected_merkle = object_closure_digest(final_root)
        if (
            header.get("releaseId") == release_id
            and sorted(header.get("executionIds") or []) == execution_ids
            and _existing_refs(final_root) == desired
            and header.get("canonicalMerkle") == selected_merkle
            and header.get("releaseKind") == ReleaseKind.CONTENT
            and header.get("rolloutMilestone") == milestone.value
            and header.get("sourceDigest") == source_digest.to_document()
            and aggregate.get("sourceDigest") == source_digest.to_document()
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
                "rolloutMilestone": milestone.value,
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
        selected_merkle = object_closure_digest(staging, create=True)
        _write_json(
            payload / "release.json",
            {
                "schema": RELEASE_SCHEMA,
                "releaseId": release_id,
                "releaseKind": ReleaseKind.CONTENT,
                "canonicalMerkle": selected_merkle,
                "executionIds": execution_ids,
                "rolloutMilestone": milestone.value,
                "sourceDigest": source_digest.to_document(),
            },
        )
        _write_json(
            payload / "desired_state.json",
            {
                "schema": "quwoquan_data.release_desired_state",
                "releaseId": release_id,
                "desiredRefs": desired,
            },
        )
        _write_json(
            payload / "index/objects.json",
            {"schema": "quwoquan_data.release_object_index", **desired},
        )
        _write_json(
            payload / "sample_bundle.json",
            {"schema": "quwoquan_data.release_sample_bundle", **desired},
        )
        media_manifest = build_release_media_manifest(
            release_id=release_id,
            post_refs=desired["posts"],
            entity_refs=desired["entities"],
            publish_root=publish_root,
        )
        if media_manifest["issues"]:
            raise ObjectTransactionError(
                "aggregate release media closure invalid: "
                + "; ".join(str(issue) for issue in media_manifest["issues"][:5])
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
                + "; ".join(
                    f"{item['code']}:{item['ref']}"
                    for item in consistency["blockingIssues"][:5]
                )
            )
        aggregate_attestation = ReleaseAttestation(
            release_id=release_id,
            release_kind=ReleaseKind.CONTENT,
            execution_ids=tuple(execution_ids),
            rollout_milestone=milestone,
            entity_count=len(entity_refs),
            post_count=len(post_refs),
            creator_count=len(creator_refs),
            tag_count=len(tag_refs),
            canonical_merkle=selected_merkle,
            source_digest=source_digest,
            payload_sha256=payload_digest(staging),
            recorded_at=_now(),
        ).to_document()
        assert_valid(
            aggregate_attestation,
            "release",
            "aggregate_release_attestation",
            label=f"aggregate_release_attestation:{release_id}",
        )
        _write_json(attestation_root(staging) / "aggregate.json", aggregate_attestation)
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
            "rolloutMilestone": milestone.value,
            "idempotent": False,
        }
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
