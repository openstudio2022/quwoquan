#!/usr/bin/env python3
"""Candidate-bound repair contract for legacy active-release Content outbox payloads."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any


SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
POST_ID_PATTERN = re.compile(r"data_post_[0-9a-f]{64}")
POST_REF_PATTERN = re.compile(r"(?:article|image|video)/[^/].+")
REPAIR_EVENT_PATTERN = re.compile(
    r"DataReleaseOutboxEventRepair\|eventId=([^|]+)"
    r"\|beforeSha256=(sha256:[0-9a-f]{64})"
    r"\|afterSha256=(sha256:[0-9a-f]{64})"
)


class ActiveContentReleaseOutboxRepairError(ValueError):
    """The repair identity or bounded result is unsafe."""


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _load_regular_json(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    resolved = path.expanduser().resolve()
    try:
        metadata = resolved.lstat()
    except OSError as exc:
        raise ActiveContentReleaseOutboxRepairError(
            f"{label} is unavailable: {resolved}"
        ) from exc
    if resolved.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise ActiveContentReleaseOutboxRepairError(
            f"{label} must be a regular file: {resolved}"
        )
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ActiveContentReleaseOutboxRepairError(
            f"{label} is unreadable: {resolved}"
        ) from exc
    if not isinstance(payload, dict):
        raise ActiveContentReleaseOutboxRepairError(f"{label} must be an object")
    return payload, sha256_file(resolved)


def _load_regular_bytes(path: Path, *, label: str) -> tuple[bytes, str]:
    resolved = path.expanduser().resolve()
    try:
        metadata = resolved.lstat()
    except OSError as exc:
        raise ActiveContentReleaseOutboxRepairError(
            f"{label} is unavailable: {resolved}"
        ) from exc
    if resolved.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise ActiveContentReleaseOutboxRepairError(
            f"{label} must be a regular file: {resolved}"
        )
    try:
        content = resolved.read_bytes()
    except OSError as exc:
        raise ActiveContentReleaseOutboxRepairError(
            f"{label} is unreadable: {resolved}"
        ) from exc
    return content, "sha256:" + hashlib.sha256(content).hexdigest()


def materialize_candidate_runtime_inputs(
    candidate_root: Path,
    output_root: Path,
    *,
    environment: str,
) -> dict[str, Any]:
    """Bind repair-only Compose inputs to one exact immutable candidate."""

    root = candidate_root.expanduser().resolve()
    packages = root / "packages"
    shared = packages / "runtime-shared"
    manifest, manifest_digest = _load_regular_json(
        shared / "manifest.json",
        label="candidate runtime shared manifest",
    )
    files = (manifest.get("provenance") or {}).get("files")
    expected_shared = {
        "Caddyfile",
        "livekit.yaml",
        "module_catalog.yaml",
        "object-storage-lifecycle.json",
        "retention_policy.yaml",
    }
    if (
        manifest.get("schema") != "qwq.runtime_shared_package"
        or manifest.get("environment") != environment
        or not isinstance(files, Mapping)
        or set(files) != expected_shared
    ):
        raise ActiveContentReleaseOutboxRepairError(
            "candidate runtime shared manifest identity mismatch"
        )
    shared_content: dict[str, bytes] = {}
    shared_digests: dict[str, str] = {}
    for name in sorted(expected_shared):
        descriptor = files.get(name)
        content, digest = _load_regular_bytes(
            shared / name,
            label=f"candidate runtime shared file {name}",
        )
        if not isinstance(descriptor, Mapping) or descriptor.get("sha256") != digest:
            raise ActiveContentReleaseOutboxRepairError(
                f"candidate runtime shared file digest mismatch: {name}"
            )
        shared_content[name] = content
        shared_digests[name] = digest

    service_configs: dict[str, bytes] = {}
    service_config_digests: dict[str, str] = {}
    service_config_versions: dict[str, str] = {}
    service_provenance_digests: dict[str, str] = {}
    services_root = packages / "services"
    for service in sorted(services_root.iterdir(), key=lambda item: item.name):
        if not service.is_dir() or service.is_symlink():
            continue
        service_name = service.name
        config_content, config_digest = _load_regular_bytes(
            service / "config/config.yaml",
            label=f"candidate {service_name} configuration",
        )
        provenance, provenance_digest = _load_regular_json(
            service / "provenance.json",
            label=f"candidate {service_name} provenance",
        )
        config_version = str(provenance.get("configVersion") or "").strip()
        if (
            provenance.get("service") != service_name
            or provenance.get("environment") != environment
            or SHA256_PATTERN.fullmatch(config_version) is None
            or not isinstance(provenance.get("digests"), Mapping)
            or provenance["digests"].get("config") != config_digest
        ):
            raise ActiveContentReleaseOutboxRepairError(
                f"candidate {service_name} config digest mismatch"
            )
        service_configs[service_name] = config_content
        service_config_digests[service_name] = config_digest
        service_config_versions[service_name] = config_version
        service_provenance_digests[service_name] = provenance_digest
    if "content-service" not in service_configs:
        raise ActiveContentReleaseOutboxRepairError(
            "candidate Content configuration is unavailable"
        )

    policy = shared / "runtime-topology/policies/recommendation_policy.yaml"
    _, policy_digest = _load_regular_bytes(
        policy,
        label="candidate Content recommendation policy",
    )
    legal = packages / "legal-static/current/public"
    try:
        legal_metadata = legal.lstat()
    except OSError as exc:
        raise ActiveContentReleaseOutboxRepairError(
            "candidate legal static root is unavailable"
        ) from exc
    if legal.is_symlink() or not stat.S_ISDIR(legal_metadata.st_mode):
        raise ActiveContentReleaseOutboxRepairError(
            "candidate legal static root is unsafe"
        )

    runtime_input = output_root.expanduser().resolve() / "runtime-input"
    config_root = runtime_input / "config-root"
    reliabletask_root = (
        config_root / "quwoquan_service/runtime/reliabletask/resources"
    )
    portal_root = runtime_input / "inactive-portal"
    for directory in (config_root, reliabletask_root, portal_root):
        directory.mkdir(parents=True, exist_ok=False)
    materialized = {
        **{
            config_root / f"{service_name}.yaml": config_content
            for service_name, config_content in service_configs.items()
        },
        reliabletask_root / "module_catalog.yaml": shared_content[
            "module_catalog.yaml"
        ],
        reliabletask_root / "retention_policy.yaml": shared_content[
            "retention_policy.yaml"
        ],
    }
    for path, content in materialized.items():
        path.write_bytes(content)

    environment_values = {
        "LOCAL_GAMMA_RUNTIME_SHARED_ROOT": str(shared),
        "LOCAL_GAMMA_CADDYFILE": str(shared / "Caddyfile"),
        "LOCAL_GAMMA_LIVEKIT_CONFIG_FILE": str(shared / "livekit.yaml"),
        "LOCAL_GAMMA_OBJECT_STORAGE_LIFECYCLE_FILE": str(
            shared / "object-storage-lifecycle.json"
        ),
        "LOCAL_GAMMA_LEGAL_STATIC_ROOT": str(legal),
        "LOCAL_GAMMA_PORTAL_ROOT": str(portal_root),
        "LOCAL_GAMMA_CONFIG_ROOT": str(config_root),
        "QWQ_COMPOSE_CONFIG_ROOT": str(config_root),
        "QWQ_COMPOSE_REC_POLICY_SOURCE": str(policy),
    }
    for service_name, config_version in service_config_versions.items():
        key = service_name.upper().replace("-", "_")
        environment_values[f"QWQ_COMPOSE_{key}_CONFIG_VERSION"] = config_version

    return {
        "environment": environment_values,
        "evidence": {
            "runtimeSharedManifestDigest": manifest_digest,
            "runtimeSharedDigests": shared_digests,
            "contentProvenanceDigest": service_provenance_digests["content-service"],
            "configDigest": service_config_digests["content-service"],
            "configVersion": service_config_versions["content-service"],
            "serviceConfigDigests": service_config_digests,
            "serviceConfigVersions": service_config_versions,
            "serviceProvenanceDigests": service_provenance_digests,
            "recommendationPolicyDigest": policy_digest,
            "materializedConfigDigest": "sha256:"
            + hashlib.sha256(
                (config_root / "content-service.yaml").read_bytes()
            ).hexdigest(),
        },
    }


def _validated_post_bindings(value: Any) -> tuple[list[dict[str, Any]], str]:
    if not isinstance(value, list):
        raise ActiveContentReleaseOutboxRepairError(
            "Content import report postBindings must be an array"
        )
    expected_binding_keys = {
        "postRef",
        "postId",
        "contentId",
        "contentVersion",
        "usageScope",
        "contentType",
        "authorId",
    }
    seen_refs: set[str] = set()
    seen_ids: set[str] = set()
    seen_content_ids: set[str] = set()
    normalized_bindings: list[dict[str, Any]] = []
    for index, binding in enumerate(value):
        if not isinstance(binding, dict) or set(binding) != expected_binding_keys:
            raise ActiveContentReleaseOutboxRepairError(
                f"Content import postBindings[{index}] shape is invalid"
            )
        post_ref = str(binding.get("postRef") or "").strip()
        post_id = str(binding.get("postId") or "").strip()
        content_id = str(binding.get("contentId") or "").strip()
        author_id = str(binding.get("authorId") or "").strip()
        content_version = binding.get("contentVersion")
        usage_scope = binding.get("usageScope")
        content_type = binding.get("contentType")
        if (
            POST_REF_PATTERN.fullmatch(post_ref) is None
            or POST_ID_PATTERN.fullmatch(post_id) is None
            or not content_id
            or not author_id
            or isinstance(content_version, bool)
            or not isinstance(content_version, int)
            or content_version < 1
            or usage_scope not in {"research", "commercial"}
            or content_type not in {"article", "image", "video"}
            or post_ref in seen_refs
            or post_id in seen_ids
            or content_id in seen_content_ids
        ):
            raise ActiveContentReleaseOutboxRepairError(
                f"Content import postBindings[{index}] identity is invalid"
            )
        seen_refs.add(post_ref)
        seen_ids.add(post_id)
        seen_content_ids.add(content_id)
        normalized_bindings.append(dict(binding))
    digest = "sha256:" + hashlib.sha256(
        json.dumps(
            normalized_bindings,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return normalized_bindings, digest


def validate_source_import_report(
    path: Path,
    *,
    environment: str,
) -> dict[str, Any]:
    report, digest = _load_regular_json(path, label="Content import report")
    required = {
        "schema": "quwoquan.content_import_report",
        "status": "active",
        "environment": environment,
        "sourceOwner": "qwq_data",
        "mode": "sync",
        "deletePolicy": "tombstone",
    }
    for field, expected in required.items():
        if report.get(field) != expected:
            raise ActiveContentReleaseOutboxRepairError(
                f"Content import report {field} mismatch"
            )
    release_id = str(report.get("releaseId") or "").strip()
    manifest_digest = str(report.get("manifestDigest") or "").strip()
    counts = report.get("counts")
    if (
        not release_id
        or SHA256_PATTERN.fullmatch(manifest_digest) is None
        or not isinstance(counts, dict)
        or isinstance(counts.get("postsLoaded"), bool)
        or not isinstance(counts.get("postsLoaded"), int)
        or isinstance(counts.get("postsUpserted"), bool)
        or not isinstance(counts.get("postsUpserted"), int)
        or isinstance(counts.get("postsRemoved"), bool)
        or not isinstance(counts.get("postsRemoved"), int)
        or int(counts["postsRemoved"]) <= 0
        or isinstance(counts.get("outboxEventsAppended"), bool)
        or not isinstance(counts.get("outboxEventsAppended"), int)
        or int(counts.get("outboxEventsAppended") or -1) <= 0
    ):
        raise ActiveContentReleaseOutboxRepairError(
            "Content import report has no bounded legacy deletion closure"
        )
    normalized_bindings, bindings_digest = _validated_post_bindings(
        report.get("postBindings")
    )
    posts_loaded = int(counts["postsLoaded"])
    posts_upserted = int(counts["postsUpserted"])
    posts_removed = int(counts["postsRemoved"])
    if (
        posts_loaded != len(normalized_bindings)
        or posts_upserted != posts_loaded
        or int(counts["outboxEventsAppended"]) != posts_loaded + posts_removed
    ):
        raise ActiveContentReleaseOutboxRepairError(
            "Content import report Post/outbox binding counts drift"
        )
    return {
        "path": str(path.expanduser().resolve()),
        "digest": digest,
        "releaseId": release_id,
        "manifestDigest": manifest_digest,
        "legacyDeletionCount": int(counts["postsRemoved"]),
        "postBindingCount": len(normalized_bindings),
        "postBindingsDigest": bindings_digest,
    }


def validate_candidate_release_binding(
    snapshot: Mapping[str, Any],
    source_import: Mapping[str, Any],
) -> dict[str, Any]:
    manifest = snapshot.get("manifest")
    if not isinstance(manifest, Mapping):
        raise ActiveContentReleaseOutboxRepairError(
            "active candidate manifest is missing"
        )
    release = manifest.get("release")
    candidate = release.get("candidate") if isinstance(release, Mapping) else None
    if not isinstance(candidate, Mapping):
        raise ActiveContentReleaseOutboxRepairError(
            "active candidate release binding is missing"
        )
    release_id = str(candidate.get("releaseId") or "").strip()
    release_digest = str(candidate.get("releaseDigest") or "").strip()
    if (
        release_id != source_import.get("releaseId")
        or release_digest != source_import.get("manifestDigest")
    ):
        raise ActiveContentReleaseOutboxRepairError(
            "active candidate release differs from Content import report"
        )
    attestation_ref = Path(str(candidate.get("attestationRef") or ""))
    attestation, attestation_digest = _load_regular_json(
        attestation_ref,
        label="candidate release attestation",
    )
    expected_attestation_digest = str(candidate.get("attestationDigest") or "")
    if (
        attestation_digest != expected_attestation_digest
        or attestation.get("releaseId") != release_id
        or attestation.get("payloadSha256") != release_digest
        or attestation.get("sourceOwner") != "qwq_data"
    ):
        raise ActiveContentReleaseOutboxRepairError(
            "candidate release attestation identity mismatch"
        )
    release_root = attestation_ref.expanduser().resolve().parents[1]
    if not (release_root / "payload/desired_state.json").is_file():
        raise ActiveContentReleaseOutboxRepairError(
            "candidate immutable release root is incomplete"
        )
    return {
        "releaseId": release_id,
        "manifestDigest": release_digest,
        "attestationRef": str(attestation_ref.expanduser().resolve()),
        "attestationDigest": attestation_digest,
        "releaseRoot": str(release_root),
    }


def validate_creator_receipt(
    source_import_path: Path,
    *,
    environment: str,
    release_id: str,
) -> dict[str, str]:
    path = source_import_path.expanduser().resolve().parent / "creator-import.json"
    receipt, digest = _load_regular_json(path, label="creator import receipt")
    if (
        receipt.get("schema") != "quwoquan.user_creator_import_report"
        or receipt.get("status") != "active"
        or receipt.get("environment") != environment
        or receipt.get("releaseId") != release_id
        or receipt.get("sourceOwner") != "qwq_data"
    ):
        raise ActiveContentReleaseOutboxRepairError(
            "creator import receipt identity mismatch"
        )
    return {"path": str(path), "digest": digest}


def topology_compose_files(
    candidate_root: Path,
    candidate_manifest: Mapping[str, Any],
) -> list[Path]:
    root = candidate_root.expanduser().resolve()
    topology_root = root / "packages/runtime-shared/runtime-topology"
    manifest, _ = _load_regular_json(
        topology_root / "manifest.json",
        label="candidate runtime topology manifest",
    )
    entries = manifest.get("compose")
    if not isinstance(entries, list):
        raise ActiveContentReleaseOutboxRepairError(
            "candidate runtime topology entries are invalid"
        )
    selected: dict[tuple[str, str], Path] = {}
    control_plane: Path | None = None
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        role = str(entry.get("role") or "")
        layer = str(entry.get("layer") or "")
        service = str(entry.get("service") or "")
        if not (
            (role == "ops-base" and layer == "base" and service == "")
            or (role == "service" and layer == "base" and service)
            or (
                role == "service"
                and service == "content-service"
                and layer == "environment"
            )
            or (
                role == "control-plane"
                and layer == "base"
                and service == ""
            )
        ):
            continue
        relative = str(entry.get("ref") or "")
        path = (root / relative).resolve()
        digest = str(entry.get("digest") or "")
        if (
            not path.is_relative_to(root)
            or path.is_symlink()
            or not path.is_file()
            or sha256_file(path) != digest
        ):
            raise ActiveContentReleaseOutboxRepairError(
                "candidate repair Compose artifact is unsafe"
            )
        if role == "control-plane":
            if control_plane is not None:
                raise ActiveContentReleaseOutboxRepairError(
                    "candidate repair control-plane Compose binding is ambiguous"
                )
            control_plane = path
            continue
        selected[(service, layer)] = path
    required = {
        ("", "base"),
        ("content-service", "base"),
        ("content-service", "environment"),
    }
    if not required.issubset(selected) or control_plane is None:
        raise ActiveContentReleaseOutboxRepairError(
            "candidate repair Compose closure is incomplete"
        )
    observability = candidate_manifest.get("observabilityLogSink")
    if not isinstance(observability, Mapping):
        raise ActiveContentReleaseOutboxRepairError(
            "candidate observability Compose binding is missing"
        )
    observability_ref = str(observability.get("composeRef") or "")
    observability_digest = str(observability.get("composeDigest") or "")
    observability_path = (root / observability_ref).resolve()
    if (
        not observability_ref
        or not observability_path.is_relative_to(root)
        or observability_path.is_symlink()
        or not observability_path.is_file()
        or sha256_file(observability_path) != observability_digest
    ):
        raise ActiveContentReleaseOutboxRepairError(
            "candidate observability Compose artifact is unsafe"
        )
    return [
        selected[("", "base")],
        *[
            selected[key]
            for key in sorted(selected)
            if key[0] and key[1] == "base"
        ],
        selected[("content-service", "environment")],
        control_plane,
        observability_path,
    ]


def validate_repair_report(
    path: Path,
    *,
    environment: str,
    release_id: str,
    manifest_digest: str,
    expected_repair_count: int,
    expected_post_binding_count: int,
    expected_post_bindings_digest: str,
) -> dict[str, Any]:
    if (
        expected_repair_count < 0
        or expected_post_binding_count < 1
        or SHA256_PATTERN.fullmatch(expected_post_bindings_digest) is None
    ):
        raise ActiveContentReleaseOutboxRepairError(
            "expected repair/Post binding identity is invalid"
        )
    report, digest = _load_regular_json(path, label="Content repair report")
    for field, expected in {
        "schema": "quwoquan.content_import_report",
        "status": "active",
        "environment": environment,
        "releaseId": release_id,
        "manifestDigest": manifest_digest,
        "sourceOwner": "qwq_data",
        "mode": "sync",
        "deletePolicy": "tombstone",
    }.items():
        if report.get(field) != expected:
            raise ActiveContentReleaseOutboxRepairError(
                f"Content repair report {field} mismatch"
            )
    counts = report.get("counts")
    post_bindings, post_bindings_digest = _validated_post_bindings(
        report.get("postBindings")
    )
    if (
        not isinstance(counts, Mapping)
        or counts.get("postsLoaded") != expected_post_binding_count
        or counts.get("postsUpserted") != expected_post_binding_count
        or counts.get("postsRemoved") != 0
        or counts.get("outboxEventsReady") != expected_repair_count
        or counts.get("outboxEventsAppended") != 0
        or len(post_bindings) != expected_post_binding_count
        or post_bindings_digest != expected_post_bindings_digest
    ):
        raise ActiveContentReleaseOutboxRepairError(
            "Content repair report Post/outbox closure drift"
        )
    events = report.get("auditEvents")
    if not isinstance(events, list) or any(not isinstance(item, str) for item in events):
        raise ActiveContentReleaseOutboxRepairError(
            "Content repair audit events are invalid"
        )
    if events[:2] != ["DataReleasePrepared", "DataReleaseReplayValidated"]:
        raise ActiveContentReleaseOutboxRepairError(
            "Content repair report claimed activation or lost replay identity"
        )
    count_events = [item for item in events if item.startswith("DataReleaseOutboxRepair|")]
    expected_count_event = f"DataReleaseOutboxRepair|count={expected_repair_count}"
    repairs = [
        match.groups()
        for item in events
        if (match := REPAIR_EVENT_PATTERN.fullmatch(item)) is not None
    ]
    if count_events != [expected_count_event] or len(repairs) != expected_repair_count:
        raise ActiveContentReleaseOutboxRepairError(
            "Content repair audit count mismatch"
        )
    if len({event_id for event_id, _, _ in repairs}) != len(repairs):
        raise ActiveContentReleaseOutboxRepairError(
            "Content repair audit contains duplicate event identities"
        )
    return {
        "path": str(path.expanduser().resolve()),
        "digest": digest,
        "repairCount": len(repairs),
        "repairs": [
            {
                "eventId": event_id,
                "beforeSha256": before,
                "afterSha256": after,
            }
            for event_id, before, after in repairs
        ],
    }
