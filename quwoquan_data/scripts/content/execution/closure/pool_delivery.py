"""Immutable reviewed-object intents for canonical pool delivery."""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json
from core.paths import PUBLISH_ROOT
from core.schema import assert_valid
from core.source_attribution import canonical_source_attribution
from core.tree_integrity import tree_integrity_stats
from governance.creators.assignment import (
    CREATOR_ASSIGNMENT_FIELDS,
    creator_assignment_issues,
    creator_from_payload,
    resolve_registry_creator_assignment,
)

from content.execution.closure.pool_delivery_identity import (
    load_post_identity_reservation as _load_reservation,
)
from content.execution.closure.pool_delivery_identity import (
    load_reserved_post_identity,
)
from content.execution.closure.pool_delivery_identity import (
    reserve_post_identity as _reserve_post_identity,
)
from content.execution.identity import validate_execution_id
from content.execution.workspace import execution_root
from content.release.canonical.object_transaction_lock import (
    canonical_publish_serialized,
)
from content.release.canonical.pool_source_attribution import (
    source_attribution_complete,
)

POOL_DELIVERY_INTENT_DIR = "_shared/pool_delivery_intents"
_SCHEMA = "quwoquan_data.pool_delivery_intent"
_CARRIERS = frozenset({"homepage", "article", "image", "video"})
_CREATOR_BINDING_FIELDS = (*CREATOR_ASSIGNMENT_FIELDS, "creatorProfileVersion")


from content.execution.closure.pool_delivery_paths import (
    _digest,
    _file_digest,
    _safe_object_dir,
)


def _approved_review(object_dir: Path) -> tuple[str, str]:
    path = object_dir / "5.review/attestation.json"
    payload = read_json(path)
    if not isinstance(payload, Mapping) or payload.get("decision") != "approved":
        raise ValueError("pool delivery requires an approved review attestation")
    for key in ("deterministicGate", "independentReviewer", "mediaRefReview"):
        binding = payload.get(key)
        if not isinstance(binding, Mapping) or binding.get("status") != "passed":
            raise ValueError(f"pool delivery review binding is not passed: {key}")
    return path.relative_to(object_dir).as_posix(), _file_digest(path)


def _identity_documents(
    *,
    carrier: str,
    object_ref: str,
    object_dir: Path,
    reserved_identity: Mapping[str, Any] | None,
) -> tuple[str, str | None, int, str | None, Mapping[str, Any], Mapping[str, Any]]:
    manifest = read_json(object_dir / "manifest.json")
    if not isinstance(manifest, Mapping):
        raise TypeError("pool delivery manifest must be an object")
    if carrier == "homepage":
        entity = read_json(object_dir / "_entity.json")
        if not isinstance(entity, Mapping):
            raise TypeError("pool delivery homepage entity must be an object")
        expected_ref = str(entity.get("entityRef") or "").strip()
        if expected_ref != object_ref:
            raise ValueError("pool delivery homepage objectRef drift")
        return object_ref, None, 1, None, entity, manifest
    if str(manifest.get("contentType") or "").strip() != carrier:
        raise ValueError("pool delivery post carrier drift")
    if not isinstance(reserved_identity, Mapping):
        raise ValueError("pool delivery post identity reservation is missing")
    content_id = str(reserved_identity.get("contentId") or "").strip()
    version = reserved_identity.get("version")
    if not content_id or isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError("pool delivery post contentId/version is invalid")
    reservation_id = str(reserved_identity.get("reservationId") or "").strip()
    if not reservation_id.startswith("sha256:"):
        raise ValueError("pool delivery post identity reservation is invalid")
    if reserved_identity.get("sourceManifestSha256") != _file_digest(
        object_dir / "manifest.json"
    ):
        raise ValueError(
            "DATA.POOL.IDEMPOTENCY_CONFLICT: "
            "pool delivery post identity reservation input drift"
        )
    return content_id, content_id, version, reservation_id, manifest, manifest


def _content_creator_signals(identity: Mapping[str, Any]) -> tuple[str | None, str | None, list[str]]:
    vertical = str(identity.get("vertical") or "").strip() or None
    region = str(
        identity.get("regionRef")
        or identity.get("coverageRegion")
        or identity.get("region")
        or ""
    ).strip() or None
    tags = [
        str(value).strip()
        for value in (identity.get("tagRefs") or [])
        if str(value).strip()
    ]
    return vertical, region, tags


def _complete_creator_binding(assignment: Mapping[str, Any]) -> dict[str, Any]:
    creator = creator_from_payload(assignment)
    version = str(
        assignment.get("creatorProfileVersion")
        or creator.get("creatorProfileDigest")
        or ""
    ).strip()
    binding = {
        field: version if field == "creatorProfileVersion" else creator.get(field)
        for field in _CREATOR_BINDING_FIELDS
    }
    missing = [field for field, value in binding.items() if value in (None, "", {})]
    if missing:
        raise ValueError(
            "pool delivery creator binding is incomplete: " + ",".join(missing)
        )
    if binding["creatorProfileVersion"] != binding["creatorProfileDigest"]:
        raise ValueError(
            "pool delivery creatorProfileVersion must equal creatorProfileDigest"
        )
    return binding


def _creator_binding_for_delivery(
    identity: Mapping[str, Any],
    *,
    execution_id: str,
    object_ref: str,
    carrier: str,
) -> tuple[str, dict[str, Any]]:
    vertical, region, tag_refs = _content_creator_signals(identity)
    issues = creator_assignment_issues(
        identity,
        carrier=None if carrier == "homepage" else carrier or None,
        prefix="poolDelivery.creatorAssignment",
        content_vertical=vertical,
        content_region=region,
        content_tag_refs=tag_refs,
    )
    if not issues:
        return "manifest_exact", _complete_creator_binding(identity)
    if carrier == "homepage" or any(".semanticFit:" not in issue for issue in issues):
        raise ValueError("; ".join(issues))
    assignment = resolve_registry_creator_assignment(
        {},
        carrier=carrier,
        region=region,
        vertical=vertical,
        tag_refs=tag_refs,
        seed=f"{execution_id}|{object_ref}|{carrier}|pool-delivery",
        preferred_archetype="",
        selection_mode="best",
    )
    if not assignment:
        raise ValueError(
            "poolDelivery.creatorAssignment.semanticFit: no registered strong-match creator"
        )
    recovered_issues = creator_assignment_issues(
        assignment,
        carrier=carrier,
        prefix="poolDelivery.creatorAssignment",
        content_vertical=vertical,
        content_region=region,
        content_tag_refs=tag_refs,
    )
    if recovered_issues:
        raise ValueError("; ".join(recovered_issues))
    return "semantic_fit_recovery", _complete_creator_binding(assignment)


def creator_binding_from_pool_delivery_intent(
    identity: Mapping[str, Any],
    intent: Mapping[str, Any],
    *,
    carrier: str,
) -> dict[str, Any]:
    """Validate and return the frozen registry-backed creator delivery binding."""

    binding = intent.get("creatorBinding")
    if not isinstance(binding, Mapping) or _digest(binding) != intent.get(
        "creatorBindingDigest"
    ):
        raise ValueError("pool delivery creator binding digest mismatch")
    mode = str(intent.get("creatorBindingMode") or "")
    vertical, region, tag_refs = _content_creator_signals(identity)
    source_issues = creator_assignment_issues(
        identity,
        carrier=None if carrier == "homepage" else carrier or None,
        prefix="poolDelivery.creatorAssignment",
        content_vertical=vertical,
        content_region=region,
        content_tag_refs=tag_refs,
    )
    if mode == "manifest_exact":
        if source_issues or _complete_creator_binding(identity) != dict(binding):
            raise ValueError("pool delivery manifest-exact creator binding drift")
    elif mode == "semantic_fit_recovery":
        if carrier == "homepage" or not source_issues or any(
            ".semanticFit:" not in issue for issue in source_issues
        ):
            raise ValueError(
                "pool delivery semantic creator recovery requires semanticFit-only source drift"
            )
    else:
        raise ValueError("pool delivery creator binding mode is invalid")
    binding_issues = creator_assignment_issues(
        binding,
        carrier=None if carrier == "homepage" else carrier or None,
        prefix="poolDelivery.creatorBinding",
        content_vertical=vertical,
        content_region=region,
        content_tag_refs=tag_refs,
    )
    if binding_issues:
        raise ValueError("; ".join(binding_issues))
    return _complete_creator_binding(binding)


def build_pool_delivery_intent(
    execution_id: str,
    *,
    carrier: str,
    object_ref: str,
    content_object_dir: str,
    root: Path | None = None,
    reservation_root: Path | None = None,
) -> dict[str, Any]:
    """Build the sole immutable handoff from reviewed closure to pool delivery."""

    normalized_execution = validate_execution_id(execution_id)
    normalized_carrier = str(carrier or "").strip()
    normalized_ref = str(object_ref or "").strip()
    if normalized_carrier not in _CARRIERS or not normalized_ref:
        raise ValueError("pool delivery carrier/objectRef is invalid")
    execution_dir = (root or execution_root(normalized_execution)).resolve()
    relative, object_dir = _safe_object_dir(execution_dir, content_object_dir)
    review_ref, review_sha = _approved_review(object_dir)
    reserved_identity = (
        None
        if normalized_carrier == "homepage"
        else _load_reservation(
            normalized_execution,
            relative,
            reservation_root=reservation_root,
        )
    )
    (
        object_id,
        content_id,
        version,
        reservation_id,
        identity,
        manifest,
    ) = _identity_documents(
        carrier=normalized_carrier,
        object_ref=normalized_ref,
        object_dir=object_dir,
        reserved_identity=reserved_identity,
    )
    creator_binding_mode, creator_binding = _creator_binding_for_delivery(
        identity,
        execution_id=normalized_execution,
        object_ref=normalized_ref,
        carrier=normalized_carrier,
    )
    if normalized_carrier == "homepage":
        entity_ref = str(identity.get("entityRef") or "").strip()
        tag_refs = identity.get("tagRefs")
        if not entity_ref.startswith("/entity/") or (
            not isinstance(tag_refs, list)
            or not tag_refs
            or any(not isinstance(ref, str) or "/" not in ref for ref in tag_refs)
        ):
            raise ValueError("pool delivery homepage entity/tag binding is incomplete")
        entity_tag_binding = {
            "entityRef": entity_ref,
            "tagRefs": sorted(set(tag_refs)),
        }
        source_attribution = canonical_source_attribution(
            identity.get("sourceAttribution")
        )
        if (
            not source_attribution_complete(
                {"sourceAttribution": source_attribution}
            )
            or manifest.get("sourceAttribution") != source_attribution
        ):
            raise ValueError("pool delivery homepage sourceAttribution is incomplete")
    else:
        entity_refs = identity.get("entityRefs")
        normalized_entity_refs = identity.get("normalizedEntityRefs")
        tag_refs = identity.get("tagRefs")
        if (
            not isinstance(entity_refs, list)
            or not entity_refs
            or any(
                not isinstance(ref, str) or not ref.startswith("/entity/")
                for ref in entity_refs
            )
        ):
            raise ValueError("pool delivery entityRefs are not canonical")
        if (
            not isinstance(normalized_entity_refs, list)
            or not normalized_entity_refs
            or any(
                not isinstance(ref, str) or not ref.startswith("entity:")
                for ref in normalized_entity_refs
            )
        ):
            raise ValueError(
                "pool delivery normalized entityRefs are not canonical"
            )
        if (
            not isinstance(tag_refs, list)
            or not tag_refs
            or any(
                not isinstance(ref, str) or "/" not in ref
                for ref in tag_refs
            )
        ):
            raise ValueError("pool delivery tagRefs are not canonical")
        entity_tag_binding = {
            "entityRefs": sorted(set(entity_refs)),
            "normalizedEntityRefs": sorted(set(normalized_entity_refs)),
            "tagRefs": sorted(set(tag_refs)),
        }
        source_attribution = canonical_source_attribution(
            identity.get("sourceAttribution")
        )
        if not source_attribution_complete(
            {"sourceAttribution": source_attribution}
        ):
            raise ValueError("pool delivery sourceAttribution is incomplete")
    transaction_ref = (
        normalized_ref.removeprefix("/entity/")
        if normalized_carrier == "homepage"
        else relative.removeprefix("posts/")
    )
    transaction_id = (
        f"{normalized_execution}--"
        f"{'entity' if normalized_carrier == 'homepage' else 'post'}-"
        f"{hashlib.sha256(transaction_ref.encode('utf-8')).hexdigest()[:12]}"
    )
    stable: dict[str, Any] = {
        "schema": _SCHEMA,
        "executionId": normalized_execution,
        "carrier": normalized_carrier,
        "objectRef": normalized_ref,
        "contentObjectDir": relative,
        "objectId": object_id,
        "contentId": content_id,
        "version": version,
        "poolIdentityReservationId": reservation_id,
        "reviewEvidenceRef": f"{relative}/{review_ref}",
        "reviewEvidenceSha256": review_sha,
        "creatorBindingMode": creator_binding_mode,
        "creatorBinding": creator_binding,
        "creatorBindingDigest": _digest(creator_binding),
        "entityTagBindingDigest": _digest(entity_tag_binding),
        "sourceAttributionDigest": _digest(source_attribution),
        "mediaClosureDigest": _digest(manifest.get("assets") or []),
        "transactionId": transaction_id,
        "transactionInputDigest": str(
            tree_integrity_stats(object_dir)["merkleRoot"]
        ),
    }
    intent = {"intentId": _digest(stable), **stable}
    assert_valid(
        intent,
        "execution",
        "pool_delivery_intent",
        label=f"pool delivery intent:{normalized_execution}/{normalized_ref}",
    )
    return intent


def pool_delivery_intent_path(
    execution_id: str,
    *,
    carrier: str,
    object_ref: str,
    root: Path | None = None,
) -> Path:
    normalized = validate_execution_id(execution_id)
    key = hashlib.sha256(
        f"{normalized}|{carrier}|{object_ref}".encode("utf-8")
    ).hexdigest()
    return (root or execution_root(normalized)) / POOL_DELIVERY_INTENT_DIR / f"{key}.json"


@canonical_publish_serialized
def write_pool_delivery_intent(
    execution_id: str,
    *,
    carrier: str,
    object_ref: str,
    content_object_dir: str,
    root: Path | None = None,
    publish_root: Path | None = None,
    reservation_root: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    normalized_execution = validate_execution_id(execution_id)
    normalized_carrier = str(carrier or "").strip()
    if root is not None and (publish_root is None or reservation_root is None):
        raise ValueError(
            "isolated pool delivery requires explicit publish_root and reservation_root"
        )
    effective_publish_root = (publish_root or PUBLISH_ROOT).resolve()
    if normalized_carrier != "homepage":
        execution_dir = (root or execution_root(normalized_execution)).resolve()
        relative, object_dir = _safe_object_dir(execution_dir, content_object_dir)
        _reserve_post_identity(
            normalized_execution,
            carrier=normalized_carrier,
            object_ref=str(object_ref or "").strip(),
            content_object_dir=relative,
            object_dir=object_dir,
            publish_root=effective_publish_root,
            reservation_root=reservation_root,
        )
    intent = build_pool_delivery_intent(
        normalized_execution,
        carrier=carrier,
        object_ref=object_ref,
        content_object_dir=content_object_dir,
        root=root,
        reservation_root=reservation_root,
    )
    path = pool_delivery_intent_path(
        execution_id,
        carrier=carrier,
        object_ref=object_ref,
        root=root,
    )
    encoded = (
        json.dumps(intent, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        if path.read_bytes() != encoded:
            raise ValueError(
                "DATA.POOL.IDEMPOTENCY_CONFLICT: pool delivery intent digest drift"
            ) from exc
        return intent, path
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return intent, path


def validate_pool_delivery_intent_document(
    payload: object,
    *,
    root: Path,
) -> dict[str, Any]:
    """Validate one exact intent and its reviewed object without global scans."""

    if not isinstance(payload, Mapping):
        raise TypeError("pool delivery intent must be an object")
    assert_valid(
        dict(payload),
        "execution",
        "pool_delivery_intent",
        label="pool delivery intent document",
    )
    stable = {key: value for key, value in payload.items() if key != "intentId"}
    if _digest(stable) != payload.get("intentId"):
        raise ValueError("pool delivery intent content digest mismatch")
    _relative, object_dir = _safe_object_dir(root.resolve(), payload["contentObjectDir"])
    review_ref = Path(str(payload["reviewEvidenceRef"]))
    review_path = root.resolve() / review_ref
    review_has_symlink = any(
        (root.resolve() / Path(*review_ref.parts[:index])).is_symlink()
        for index in range(1, len(review_ref.parts) + 1)
    )
    if (
        review_ref.is_absolute()
        or ".." in review_ref.parts
        or review_has_symlink
        or not review_path.is_file()
        or _file_digest(review_path) != payload["reviewEvidenceSha256"]
        or tree_integrity_stats(object_dir)["merkleRoot"]
        != payload["transactionInputDigest"]
    ):
        raise ValueError("pool delivery intent input drift")
    identity = read_json(
        object_dir / ("_entity.json" if payload["carrier"] == "homepage" else "manifest.json")
    )
    if not isinstance(identity, Mapping):
        raise TypeError("pool delivery creator identity must be an object")
    creator_binding_from_pool_delivery_intent(
        identity,
        payload,
        carrier=str(payload["carrier"]),
    )
    return dict(payload)


def load_execution_pool_delivery_intents(
    execution_id: str,
) -> tuple[tuple[dict[str, Any], Path], ...]:
    """Load only one exact execution's immutable intents for operator recovery."""

    normalized = validate_execution_id(execution_id)
    root = execution_root(normalized).resolve()
    intent_root = root / POOL_DELIVERY_INTENT_DIR
    rows: list[tuple[dict[str, Any], Path]] = []
    for path in sorted(intent_root.glob("*.json")):
        if path.is_symlink():
            raise ValueError("pool delivery intent ref cannot be a symlink")
        payload = validate_pool_delivery_intent_document(read_json(path), root=root)
        if payload.get("executionId") != normalized:
            raise ValueError("pool delivery intent executionId drift")
        rows.append((payload, path))
    return tuple(rows)


__all__ = [
    "POOL_DELIVERY_INTENT_DIR",
    "build_pool_delivery_intent",
    "creator_binding_from_pool_delivery_intent",
    "load_execution_pool_delivery_intents",
    "load_reserved_post_identity",
    "pool_delivery_intent_path",
    "validate_pool_delivery_intent_document",
    "write_pool_delivery_intent",
]
