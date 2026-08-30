"""Create a fail-closed research-to-commercial object migration receipt."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from content.release.canonical.commercial_transition_evidence import (
    CommercialTransitionEvidenceError,
    document_digest,
    load_commercial_transition_evidence,
)
from content.release.canonical.object_source_identity import source_identity_set
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
)
from core.io import write_json
from core.paths import OUTPUT_ROOT, RELEASE_ROOT
from core.release_layout import payload_digest, payload_file
from core.schema import assert_valid
from core.source_digest import SourceDefinitionSnapshot, SourceDigestError


class CommercialTransitionError(RuntimeError):
    pass


def _safe_segment(value: str, *, label: str) -> str:
    normalized = str(value or "").strip()
    path = Path(normalized)
    if (
        not normalized
        or normalized in {".", ".."}
        or path.is_absolute()
        or len(path.parts) != 1
        or "/" in normalized
        or "\\" in normalized
    ):
        raise CommercialTransitionError(f"{label} must be one safe segment")
    return normalized


def _evidence_ref(path: Path, *, output_root: Path) -> str:
    try:
        return path.resolve().relative_to(output_root.resolve()).as_posix()
    except ValueError as exc:
        raise CommercialTransitionError(
            "cleanup evidence must be an audited file below QWQ_OUTPUT_ROOT"
        ) from exc


def _assets(admission: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = admission.get("assets")
    if not isinstance(rows, list):
        raise CommercialTransitionError("release asset admission lacks assets")
    result = {
        str(row.get("assetId") or ""): dict(row)
        for row in rows
        if isinstance(row, Mapping)
    }
    if "" in result or len(result) != len(rows):
        raise CommercialTransitionError("release asset admission IDs are invalid")
    return result


def _source_identity_evidence(
    header: Mapping[str, Any],
    *,
    prefix: str,
) -> dict[str, str]:
    source_documents = header.get("sourceDigests")
    if not isinstance(source_documents, list) or not source_documents:
        raise CommercialTransitionError(
            f"{prefix} release sourceDigests are invalid"
        )
    try:
        source_values = tuple(
            SourceDefinitionSnapshot.from_document(row).digest
            for row in source_documents
        )
    except SourceDigestError as exc:
        raise CommercialTransitionError(
            f"{prefix} release sourceDigests are invalid"
        ) from exc
    if source_values != tuple(sorted(set(source_values))):
        raise CommercialTransitionError(
            f"{prefix} release sourceDigests are invalid"
        )
    scalar = str(header.get("sourceDigest") or "").strip()
    identity_set = str(header.get("sourceIdentitySetDigest") or "").strip()
    source_identities = header.get("sourceIdentities")
    if scalar and (identity_set or source_identities is not None):
        raise CommercialTransitionError(
            f"{prefix} release mixes scalar and set source identity"
        )
    if scalar:
        if len(source_values) != 1 or scalar != source_values[0]:
            raise CommercialTransitionError(
                f"{prefix} release sourceDigest is invalid"
            )
        return {f"{prefix}SourceDigest": scalar}
    if (
        not identity_set.startswith("sha256:")
        or not isinstance(source_identities, list)
        or not source_identities
    ):
        raise CommercialTransitionError(
            f"{prefix} release source identity set is invalid"
        )
    expanded: list[dict[str, str]] = []
    for row in source_identities:
        execution_ids = row.get("executionIds") if isinstance(row, Mapping) else None
        if not isinstance(execution_ids, list) or not execution_ids:
            raise CommercialTransitionError(
                f"{prefix} release source identity set is invalid"
            )
        for execution_id in execution_ids:
            expanded.append(
                {
                    "executionId": str(execution_id or ""),
                    "sourceRevision": str(row.get("sourceRevision") or ""),
                    "sourceDigest": str(row.get("sourceDigest") or ""),
                    "entityCatalogDigest": str(
                        row.get("entityCatalogDigest") or ""
                    ),
                }
            )
    try:
        expected_rows, expected_digest = source_identity_set(expanded)
    except (ObjectTransactionError, TypeError, ValueError) as exc:
        raise CommercialTransitionError(
            f"{prefix} release source identity set is invalid"
        ) from exc
    if (
        source_identities != expected_rows
        or identity_set != expected_digest
        or set(source_values)
        != {str(row["sourceDigest"]) for row in expected_rows}
    ):
        raise CommercialTransitionError(
            f"{prefix} release source identity set is invalid"
        )
    return {f"{prefix}SourceIdentitySetDigest": identity_set}


def _desired_refs(release_root: Path, *, label: str) -> dict[str, set[str]]:
    desired = _read_json(payload_file(release_root, "desired_state.json"))
    rows = desired.get("desiredRefs")
    if not isinstance(rows, Mapping):
        raise CommercialTransitionError(f"{label} desiredRefs are missing")
    result: dict[str, set[str]] = {}
    for kind in ("creators", "entities", "posts", "tags"):
        values = rows.get(kind)
        if not isinstance(values, list) or any(
            not str(value or "").strip() for value in values
        ):
            raise CommercialTransitionError(
                f"{label} desiredRefs.{kind} is invalid"
            )
        normalized = {str(value).strip() for value in values}
        if len(normalized) != len(values):
            raise CommercialTransitionError(
                f"{label} desiredRefs.{kind} must be unique"
            )
        result[kind] = normalized
    return result


def _content_index(
    header: Mapping[str, Any],
    *,
    desired_posts: set[str],
    label: str,
) -> dict[str, str]:
    rows = header.get("contents")
    if not isinstance(rows, list):
        raise CommercialTransitionError(f"{label} contents are missing")
    by_ref: dict[str, str] = {}
    content_ids: set[str] = set()
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise CommercialTransitionError(f"{label} content entry is invalid")
        post_ref = str(raw.get("postRef") or "").strip()
        content_id = str(raw.get("contentId") or "").strip()
        if (
            not post_ref
            or not content_id
            or post_ref in by_ref
            or content_id in content_ids
        ):
            raise CommercialTransitionError(f"{label} content entry is invalid")
        by_ref[post_ref] = content_id
        content_ids.add(content_id)
    if set(by_ref) != desired_posts:
        raise CommercialTransitionError(
            f"{label} contents drift from desired posts"
        )
    return by_ref


def _stable_object_key(
    object_ref: str,
    *,
    content_by_post: Mapping[str, str],
    entity_refs: set[str],
    label: str,
) -> str:
    if object_ref.startswith("posts/"):
        post_ref = object_ref.removeprefix("posts/")
        content_id = content_by_post.get(post_ref)
        if content_id:
            return f"content:{content_id}"
    elif object_ref.startswith("entities/"):
        entity_ref = object_ref.removeprefix("entities/")
        if entity_ref in entity_refs:
            return f"entity:{entity_ref}"
    raise CommercialTransitionError(
        f"{label} asset objectRef is outside the immutable release: {object_ref}"
    )


def write_commercial_transition(
    *,
    research_release_id: str,
    commercial_release_id: str,
    transition_run_id: str,
    cleanup_evidence_path: Path,
    release_root: Path = RELEASE_ROOT,
    output_root: Path = OUTPUT_ROOT,
) -> tuple[dict[str, Any], Path]:
    research_release_id = _safe_segment(
        research_release_id, label="researchReleaseId"
    )
    commercial_release_id = _safe_segment(
        commercial_release_id, label="commercialReleaseId"
    )
    transition_run_id = _safe_segment(
        transition_run_id, label="transitionRunId"
    )
    if research_release_id == commercial_release_id:
        raise CommercialTransitionError(
            "commercial transition requires a new immutable release"
        )
    research_release = release_root / research_release_id
    commercial_release = release_root / commercial_release_id
    research_header = _read_json(payload_file(research_release, "release.json"))
    commercial_header = _read_json(payload_file(commercial_release, "release.json"))
    research = _read_json(payload_file(research_release, "asset_admission.json"))
    commercial = _read_json(payload_file(commercial_release, "asset_admission.json"))
    research_digest = payload_digest(research_release)
    commercial_digest = payload_digest(commercial_release)
    if research_digest == commercial_digest:
        raise CommercialTransitionError(
            "commercial transition requires a distinct immutable payload"
        )
    if (
        research.get("releaseClass") != "research"
        or research_header.get("releaseClass") != "research"
    ):
        raise CommercialTransitionError("source release is not research")
    if (
        commercial.get("releaseClass") != "commercial"
        or commercial_header.get("releaseClass") != "commercial"
        or commercial.get("productLifecycleState") != "commercial"
        or commercial.get("containsUnverifiedAssets") is not False
        or commercial.get("authorizationRequiredAssetIds") != []
    ):
        raise CommercialTransitionError(
            "target commercial release contains non-commercial assets"
        )
    research_pool_digest = str(research_header.get("poolDigest") or "").strip()
    commercial_pool_digest = str(commercial_header.get("poolDigest") or "").strip()
    if (
        not research_pool_digest.startswith("sha256:")
        or commercial_pool_digest != research_pool_digest
    ):
        raise CommercialTransitionError(
            "commercial transition releases must bind the same frozen poolDigest"
        )
    research_source_evidence = _source_identity_evidence(
        research_header,
        prefix="research",
    )
    commercial_source_evidence = _source_identity_evidence(
        commercial_header,
        prefix="commercial",
    )
    research_desired = _desired_refs(research_release, label="research release")
    commercial_desired = _desired_refs(
        commercial_release,
        label="commercial release",
    )
    research_content_by_post = _content_index(
        research_header,
        desired_posts=research_desired["posts"],
        label="research release",
    )
    commercial_content_by_post = _content_index(
        commercial_header,
        desired_posts=commercial_desired["posts"],
        label="commercial release",
    )
    if not set(commercial_content_by_post.values()).issubset(
        set(research_content_by_post.values())
    ) or not commercial_desired["entities"].issubset(
        research_desired["entities"]
    ):
        raise CommercialTransitionError(
            "commercial release is not an authorized object subset of research"
        )
    research_assets = _assets(research)
    commercial_assets = _assets(commercial)
    research_object_keys = {
        *(f"content:{content_id}" for content_id in research_content_by_post.values()),
        *(f"entity:{entity_ref}" for entity_ref in research_desired["entities"]),
    }
    commercial_by_object: dict[str, list[str]] = {}
    commercial_asset_keys: dict[str, str] = {}
    for asset_id, asset in commercial_assets.items():
        if asset.get("distributionDecision") != "commercial_allowed":
            raise CommercialTransitionError(
                f"commercial asset is not commercial_allowed: {asset_id}"
            )
        object_ref = str(asset.get("objectRef") or "")
        stable_key = _stable_object_key(
            object_ref,
            content_by_post=commercial_content_by_post,
            entity_refs=commercial_desired["entities"],
            label="commercial",
        )
        if stable_key not in research_object_keys:
            raise CommercialTransitionError(
                f"commercial asset is outside the authorized subset: {asset_id}"
            )
        commercial_by_object.setdefault(stable_key, []).append(asset_id)
        commercial_asset_keys[asset_id] = stable_key
    authorization_ids = research.get("authorizationRequiredAssetIds")
    if not isinstance(authorization_ids, list):
        raise CommercialTransitionError(
            "research authorizationRequiredAssetIds are missing"
        )
    migrations: list[dict[str, Any]] = []
    for asset_id in sorted(str(item) for item in authorization_ids):
        research_asset = research_assets.get(asset_id)
        if research_asset is None:
            raise CommercialTransitionError(
                f"research authorization asset is absent: {asset_id}"
            )
        object_ref = str(research_asset.get("objectRef") or "")
        stable_key = _stable_object_key(
            object_ref,
            content_by_post=research_content_by_post,
            entity_refs=research_desired["entities"],
            label="research",
        )
        if asset_id in commercial_assets:
            if commercial_asset_keys[asset_id] != stable_key:
                raise CommercialTransitionError(
                    f"commercial asset identity moved across objects: {asset_id}"
                )
            action = "verified_preserved"
            commercial_ids = [asset_id]
        else:
            commercial_ids = sorted(commercial_by_object.get(stable_key, []))
            action = "replaced" if commercial_ids else "removed"
        migrations.append(
            {
                "researchAssetId": asset_id,
                "objectRef": object_ref,
                "action": action,
                "commercialAssetIds": commercial_ids,
            }
        )
    try:
        verified_evidence = load_commercial_transition_evidence(
            cleanup_evidence_path,
            research_release_id=research_release_id,
            research_manifest_digest=research_digest,
            commercial_release_id=commercial_release_id,
            commercial_manifest_digest=commercial_digest,
            output_root=output_root,
        )
    except CommercialTransitionEvidenceError as exc:
        raise CommercialTransitionError(str(exc)) from exc
    environment_cleanup = [dict(row) for row in verified_evidence.environments]
    document: dict[str, Any] = {
        "schema": "quwoquan_data.commercial_transition",
        "transitionRunId": transition_run_id,
        "researchReleaseId": research_release_id,
        "researchManifestDigest": research_digest,
        "commercialReleaseId": commercial_release_id,
        "commercialManifestDigest": commercial_digest,
        "poolDigest": research_pool_digest,
        **research_source_evidence,
        **commercial_source_evidence,
        "objectMigrations": migrations,
        "environmentCleanup": sorted(
            environment_cleanup, key=lambda row: str(row["environment"])
        ),
        "unauthorizedReadbackCount": 0,
        "cleanupEvidenceRef": _evidence_ref(
            cleanup_evidence_path, output_root=output_root
        ),
        "cleanupEvidenceDigest": verified_evidence.evidence_digest,
        "passed": True,
        "recordedAt": datetime.now(timezone.utc).isoformat(),
    }
    document["receiptDigest"] = document_digest(
        document,
        excluded="receiptDigest",
    )
    assert_valid(
        document,
        "release",
        "commercial_transition",
        label="commercial transition",
    )
    path = (
        output_root
        / "data/commercial-transitions"
        / commercial_release_id
        / transition_run_id
        / "receipt.json"
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise CommercialTransitionError(
            f"append-only commercial transition already exists: {path.parent}"
        ) from exc
    write_json(path, document)
    return document, path


__all__ = ["CommercialTransitionError", "write_commercial_transition"]
