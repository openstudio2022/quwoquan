"""候选绑定的单环境 Go source overlay 物化与回读校验。"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

import quwoquan_ops.cli.lib.deployment_candidate_manifest as _pkg

from quwoquan_ops.cli.lib.external_provider_governance_lib.single_environment import (
    SINGLE_ENVIRONMENT_MANIFEST_SCHEMA,
    compile_single_environment_bindings,
)

from .candidate_fs import (
    _UnsafeCandidatePath,
    _read_candidate_bytes,
    _read_candidate_object,
    _validate_candidate_artifact_ref,
)
from .candidate_staging import (
    _atomic_write_candidate_file,
    _begin_candidate_directory_materialization,
    _discard_candidate_staging_directory,
    _publish_candidate_staging_directory,
)
from .constants import _DIGEST


PROVIDER_BINDING_OVERLAY_SCHEMA = "stackctl-compiled-provider-binding-overlay"
_ARTIFACT_RELATIVE = Path("packages/runtime-shared/compiled-provider-bindings")
_SOURCE_OUTPUT_PREFIX = "quwoquan_service/"
_SAFE_SOURCE_PART = re.compile(r"[A-Za-z0-9._-]+")
_BINDING_MANIFEST_FIELDS = frozenset(
    {
        "schema",
        "environment",
        "target",
        "bindingDigest",
        "readinessDigest",
        "descriptorDigest",
        "goSourceDigest",
        "descriptorCount",
        "manifestDigest",
    }
)


def materialize_provider_binding_overlay(
    env_name: str,
    target_name: str,
    *,
    source_root: Path,
) -> dict[str, Any]:
    """Compile once from the immutable capsule and atomically publish build inputs."""

    source_root = Path(source_root).resolve()
    compiled = compile_single_environment_bindings(
        environment=env_name,
        target=target_name,
        source_root=source_root,
    )
    binding_manifest = _validate_binding_manifest(
        compiled.get("manifest"),
        expected_environment=env_name,
        expected_target=target_name,
    )
    raw_sources = compiled.get("goSources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError("compiled Provider binding Go sources are missing")

    staged_files: dict[str, bytes] = {}
    sources: list[dict[str, str]] = []
    replacements: dict[str, str] = {}
    seen_outputs: set[str] = set()
    for index, raw_source in enumerate(raw_sources):
        if not isinstance(raw_source, Mapping) or set(raw_source) != {
            "rootId",
            "owner",
            "outputPath",
            "sourceDigest",
            "source",
        }:
            raise ValueError("compiled Provider binding Go source fields mismatch")
        root_id = str(raw_source.get("rootId") or "").strip()
        owner = str(raw_source.get("owner") or "").strip()
        output_path = _normalized_output_path(raw_source.get("outputPath"))
        source_digest = str(raw_source.get("sourceDigest") or "").strip()
        source = raw_source.get("source")
        if (
            not root_id
            or not owner
            or not isinstance(source, str)
            or not source
            or _DIGEST.fullmatch(source_digest) is None
        ):
            raise ValueError("compiled Provider binding Go source is incomplete")
        encoded = source.encode("utf-8")
        if _sha256_bytes(encoded) != source_digest:
            raise ValueError(f"compiled Provider binding Go source digest mismatch: {root_id}")
        if output_path in seen_outputs:
            raise ValueError(f"duplicate Provider binding Go output path: {output_path}")
        seen_outputs.add(output_path)
        source_name = _source_artifact_name(
            index=index,
            owner=owner,
            root_id=root_id,
        )
        source_relative = Path(source_name)
        source_ref = (_ARTIFACT_RELATIVE / source_relative).as_posix()
        staged_files[source_relative.as_posix()] = encoded
        replacements[output_path.removeprefix(_SOURCE_OUTPUT_PREFIX)] = (
            "/run/qwq-provider-bindings/" + source_relative.as_posix()
        )
        sources.append(
            {
                "rootId": root_id,
                "owner": owner,
                "outputPath": output_path,
                "sourceRef": source_ref,
                "sourceDigest": source_digest,
            }
        )

    if len(sources) != binding_manifest["descriptorCount"]:
        raise ValueError("compiled Provider binding descriptor/source closure mismatch")
    overlay_bytes = (
        json.dumps(
            {"Replace": replacements},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    staged_files["go.overlay.json"] = overlay_bytes
    payload = {
        "schema": PROVIDER_BINDING_OVERLAY_SCHEMA,
        "environment": env_name,
        "target": target_name,
        "bindingManifestDigest": binding_manifest["manifestDigest"],
        "bindingManifest": binding_manifest,
        "overlayRef": (_ARTIFACT_RELATIVE / "go.overlay.json").as_posix(),
        "overlayDigest": _sha256_bytes(overlay_bytes),
        "sources": sources,
    }
    staged_files["manifest.json"] = (
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")

    shared_root = _pkg.runtime_shared_deployment_package_dir(
        env_name,
        target=target_name,
    )
    candidate_root = shared_root.parent.parent
    (
        artifact_relative,
        parent_descriptor,
        parent_identities,
        temporary,
        staging_identity,
    ) = _begin_candidate_directory_materialization(
        candidate_root,
        _ARTIFACT_RELATIVE,
        label="Provider binding overlay",
    )
    staging_exists = True
    try:
        for relative, encoded in sorted(staged_files.items()):
            _atomic_write_candidate_file(
                candidate_root,
                artifact_relative.parent / temporary / relative,
                encoded,
                label=f"Provider binding overlay {relative}",
            )
        _publish_candidate_staging_directory(
            candidate_root,
            artifact_relative,
            parent_descriptor,
            parent_identities,
            temporary,
            staging_identity,
            label="Provider binding overlay",
        )
        staging_exists = False
    finally:
        if staging_exists:
            _discard_candidate_staging_directory(
                parent_descriptor,
                temporary,
                expected_identity=staging_identity,
            )
        os.close(parent_descriptor)
    return validate_provider_binding_overlay(
        payload,
        expected_environment=env_name,
        expected_target=target_name,
        candidate_root=candidate_root,
    )


def load_provider_binding_overlay(
    env_name: str,
    target_name: str,
    candidate_root: Path,
) -> dict[str, Any]:
    """Load exact overlay bytes from one old or current candidate without codegen."""

    payload = _read_candidate_object(
        candidate_root,
        _ARTIFACT_RELATIVE / "manifest.json",
        label="Provider binding overlay manifest",
    )
    return validate_provider_binding_overlay(
        payload,
        expected_environment=env_name,
        expected_target=target_name,
        candidate_root=candidate_root,
    )


def validate_provider_binding_overlay(
    payload: object,
    *,
    expected_environment: str,
    expected_target: str,
    candidate_root: Path,
) -> dict[str, Any]:
    required = {
        "schema",
        "environment",
        "target",
        "bindingManifestDigest",
        "bindingManifest",
        "overlayRef",
        "overlayDigest",
        "sources",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise ValueError("Provider binding overlay manifest fields mismatch")
    if payload.get("schema") != PROVIDER_BINDING_OVERLAY_SCHEMA:
        raise ValueError("Provider binding overlay schema mismatch")
    if (
        payload.get("environment") != expected_environment
        or payload.get("target") != expected_target
    ):
        raise ValueError("Provider binding overlay target identity mismatch")
    binding_manifest = _validate_binding_manifest(
        payload.get("bindingManifest"),
        expected_environment=expected_environment,
        expected_target=expected_target,
    )
    if payload.get("bindingManifestDigest") != binding_manifest["manifestDigest"]:
        raise ValueError("Provider binding overlay manifest digest mismatch")
    overlay_ref = _validate_candidate_artifact_ref(
        payload.get("overlayRef"),
        prefix=_ARTIFACT_RELATIVE.as_posix() + "/",
        label="Provider binding Go overlay",
    )
    overlay_digest = str(payload.get("overlayDigest") or "")
    if _DIGEST.fullmatch(overlay_digest) is None:
        raise ValueError("Provider binding overlay digest is invalid")
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("Provider binding overlay sources are missing")

    expected_replacements: dict[str, str] = {}
    seen_outputs: set[str] = set()
    normalized_sources: list[tuple[str, str, str]] = []
    for descriptor in sources:
        if not isinstance(descriptor, dict) or set(descriptor) != {
            "rootId",
            "owner",
            "outputPath",
            "sourceRef",
            "sourceDigest",
        }:
            raise ValueError("Provider binding overlay source fields mismatch")
        root_id = str(descriptor.get("rootId") or "").strip()
        owner = str(descriptor.get("owner") or "").strip()
        output_path = _normalized_output_path(descriptor.get("outputPath"))
        source_ref = _validate_candidate_artifact_ref(
            descriptor.get("sourceRef"),
            prefix=_ARTIFACT_RELATIVE.as_posix() + "/",
            label=f"Provider binding Go source {root_id}",
        )
        source_digest = str(descriptor.get("sourceDigest") or "")
        if (
            not root_id
            or not owner
            or output_path in seen_outputs
            or _DIGEST.fullmatch(source_digest) is None
        ):
            raise ValueError("Provider binding overlay source identity is invalid")
        seen_outputs.add(output_path)
        backing_relative = PurePosixPath(source_ref).relative_to(_ARTIFACT_RELATIVE)
        expected_replacements[output_path.removeprefix(_SOURCE_OUTPUT_PREFIX)] = (
            "/run/qwq-provider-bindings/" + backing_relative.as_posix()
        )
        normalized_sources.append((root_id, source_ref, source_digest))
    if len(normalized_sources) != binding_manifest["descriptorCount"]:
        raise ValueError("Provider binding overlay source closure mismatch")

    try:
        overlay_bytes = _read_candidate_bytes(
            candidate_root,
            overlay_ref,
            label="Provider binding Go overlay",
        )
    except _UnsafeCandidatePath as exc:
        raise ValueError("Provider binding Go overlay is unsafe") from exc
    if _sha256_bytes(overlay_bytes) != overlay_digest:
        raise ValueError("Provider binding Go overlay drifted")
    try:
        overlay = json.loads(overlay_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Provider binding Go overlay is unreadable") from exc
    if overlay != {"Replace": expected_replacements}:
        raise ValueError("Provider binding Go overlay replacement closure mismatch")
    for root_id, source_ref, source_digest in normalized_sources:
        try:
            source_bytes = _read_candidate_bytes(
                candidate_root,
                source_ref,
                label=f"Provider binding Go source {root_id}",
            )
        except _UnsafeCandidatePath as exc:
            raise ValueError(f"Provider binding Go source is unsafe: {root_id}") from exc
        if _sha256_bytes(source_bytes) != source_digest:
            raise ValueError(f"Provider binding Go source drifted: {root_id}")
    return payload


def provider_binding_overlay_build_inputs(
    payload: Mapping[str, Any],
    *,
    candidate_root: Path,
    build_context: Path,
) -> tuple[Path, Path, str]:
    """Return Docker-visible overlay directory, file and manifest digest."""

    environment = str(payload.get("environment") or "")
    target = str(payload.get("target") or "")
    validated = validate_provider_binding_overlay(
        dict(payload),
        expected_environment=environment,
        expected_target=target,
        candidate_root=candidate_root,
    )
    context = Path(build_context).resolve()
    overlay_dir = (candidate_root / _ARTIFACT_RELATIVE).resolve()
    overlay_path = (candidate_root / str(validated["overlayRef"])).resolve()
    if overlay_dir.is_relative_to(context) or context.is_relative_to(overlay_dir):
        raise ValueError("Provider binding overlay must be external to the source context")
    return overlay_dir, overlay_path, str(validated["bindingManifestDigest"])


def _validate_binding_manifest(
    value: object,
    *,
    expected_environment: str,
    expected_target: str,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _BINDING_MANIFEST_FIELDS:
        raise ValueError("compiled Provider binding manifest fields mismatch")
    if value.get("schema") != SINGLE_ENVIRONMENT_MANIFEST_SCHEMA:
        raise ValueError("compiled Provider binding manifest schema mismatch")
    if (
        value.get("environment") != expected_environment
        or value.get("target") != expected_target
    ):
        raise ValueError("compiled Provider binding manifest target identity mismatch")
    descriptor_count = value.get("descriptorCount")
    if not isinstance(descriptor_count, int) or descriptor_count <= 0:
        raise ValueError("compiled Provider binding descriptor count is invalid")
    for field in (
        "bindingDigest",
        "readinessDigest",
        "descriptorDigest",
        "goSourceDigest",
        "manifestDigest",
    ):
        if _DIGEST.fullmatch(str(value.get(field) or "")) is None:
            raise ValueError(f"compiled Provider binding {field} is invalid")
    core = {key: value[key] for key in value if key != "manifestDigest"}
    if _sha256_json(core) != value["manifestDigest"]:
        raise ValueError("compiled Provider binding manifest digest mismatch")
    return dict(value)


def _normalized_output_path(value: object) -> str:
    normalized = str(value or "").strip()
    path = PurePosixPath(normalized)
    if (
        not normalized.startswith(_SOURCE_OUTPUT_PREFIX)
        or path.is_absolute()
        or ".." in path.parts
        or path.suffix != ".go"
    ):
        raise ValueError("compiled Provider binding output path is unsafe")
    return path.as_posix()


def _source_artifact_name(*, index: int, owner: str, root_id: str) -> str:
    owner_token = owner if _SAFE_SOURCE_PART.fullmatch(owner) is not None else "owner"
    root_token = re.sub(r"[^A-Za-z0-9._-]", "_", root_id)
    return f"{index:03d}-{owner_token}-{root_token}.g.go"


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return _sha256_bytes(encoded)
