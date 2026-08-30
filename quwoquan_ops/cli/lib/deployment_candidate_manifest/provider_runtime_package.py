"""Provider runtime package 的物化、封版与校验（逐字迁自原单文件）。

``compile_provider_runtime_composition`` 与 ``runtime_shared_deployment_package_dir``
经包属性（``_pkg.``）消费，保持测试对包属性 monkeypatch 的既有语义。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

import quwoquan_ops.cli.lib.deployment_candidate_manifest as _pkg

from quwoquan_ops.cli.lib.immutable_image_composition import (
    immutable_image_digest,
)
from quwoquan_ops.cli.lib.provider_runtime_composition import (
    validate_provider_runtime_composition,
)
from quwoquan_ops.cli.lib.service_core_composition import (
    project_compose_document,
)

from .candidate_fs import (
    _UnsafeCandidatePath,
    _read_candidate_bytes,
    _read_candidate_object,
    _sha256_file,
    _sha256_json,
    _validate_candidate_artifact_ref,
)
from .candidate_staging import (
    _atomic_write_candidate_file,
    _begin_candidate_directory_materialization,
    _discard_candidate_staging_directory,
    _publish_candidate_staging_directory,
)
from .constants import (
    _DIGEST,
    PROVIDER_RUNTIME_PACKAGE_SCHEMA,
    ROOT,
)
from .provider_binding_overlay import load_provider_binding_overlay


def materialize_provider_runtime_package(
    env_name: str,
    target_name: str,
    *,
    source_root: Path,
) -> dict[str, Any]:
    """Atomically seal Provider composition and Compose overlays before fingerprinting."""

    source_root = Path(source_root).resolve()
    composition = _pkg.compile_provider_runtime_composition(
        environment=env_name,
        target=target_name,
        source_root=source_root,
    )
    validate_provider_runtime_composition(
        composition,
        expected_environment=env_name,
        expected_target=target_name,
    )
    shared_root = _pkg.runtime_shared_deployment_package_dir(
        env_name,
        target=target_name,
    )
    candidate_root = shared_root.parent.parent
    artifact_relative = Path("packages/runtime-shared/provider-runtime")
    workload_artifacts: list[dict[str, str]] = []
    staged_files: dict[str, bytes] = {}
    for workload in composition["workloads"]:
        role = str(workload.get("role") or "")
        source_ref = str(workload.get("composeRef") or "")
        source_digest = str(workload.get("composeDigest") or "")
        if not source_ref or not source_digest:
            raise ValueError(
                f"package-bound Provider workload has no Compose artifact: {role}"
            )
        source_path = (source_root / source_ref).resolve()
        if not source_path.is_relative_to(source_root) or not source_path.is_file():
            raise ValueError(
                f"Provider workload Compose source is outside the repository: {role}"
            )
        if _sha256_file(source_path) != source_digest:
            raise ValueError(f"Provider workload Compose digest drifted: {role}")
        try:
            compose = yaml.safe_load(source_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise ValueError(
                f"Provider workload Compose is unreadable: {role}: {exc}"
            ) from exc
        services = compose.get("services") if isinstance(compose, dict) else None
        service = services.get(role) if isinstance(services, dict) else None
        if not isinstance(service, dict) or not service.get("image"):
            raise ValueError(f"Provider workload Compose has no owned image: {role}")
        service.pop("build", None)
        service["image"] = (
            "${"
            + provider_runtime_image_environment_key(role)
            + ":?package-bound Provider image is required}"
        )
        # substitute overlay 对核心服务(user/integration/assistant/content 等)的
        # environment/depends_on 片段必须与运行时形态一致地并入 service-core,
        # 否则 compose merge 会出现无 image 的裸服务定义。
        compose = project_compose_document(compose)
        name = f"{role}.compose.yaml"
        compose_bytes = yaml.safe_dump(
            compose,
            allow_unicode=True,
            sort_keys=False,
        ).encode("utf-8")
        staged_files[name] = compose_bytes
        workload_artifacts.append(
            {
                "role": role,
                "sourceComposeDigest": source_digest,
                "composeRef": (artifact_relative / name).as_posix(),
                "composeDigest": (
                    "sha256:" + hashlib.sha256(compose_bytes).hexdigest()
                ),
            }
        )

    composition_bytes = (
        json.dumps(composition, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    staged_files["composition.json"] = composition_bytes
    payload = {
        "schema": PROVIDER_RUNTIME_PACKAGE_SCHEMA,
        "composition": composition,
        "compositionRef": (artifact_relative / "composition.json").as_posix(),
        "compositionDigest": (
            "sha256:" + hashlib.sha256(composition_bytes).hexdigest()
        ),
        "workloads": workload_artifacts,
        "images": {},
    }
    staged_files["manifest.json"] = (
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    (
        artifact_relative,
        parent_descriptor,
        parent_identities,
        temporary,
        staging_identity,
    ) = _begin_candidate_directory_materialization(
        candidate_root,
        artifact_relative,
        label="Provider runtime package",
    )
    staging_exists = True
    try:
        for name, encoded in staged_files.items():
            _atomic_write_candidate_file(
                candidate_root,
                artifact_relative.parent / temporary / name,
                encoded,
                label=f"Provider runtime package {name}",
            )
        _publish_candidate_staging_directory(
            candidate_root,
            artifact_relative,
            parent_descriptor,
            parent_identities,
            temporary,
            staging_identity,
            label="Provider runtime package",
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
    return validate_packaged_provider_runtime(
        payload,
        expected_environment=env_name,
        expected_target=target_name,
        candidate_root=candidate_root,
        require_images=False,
    )


def provider_runtime_image_environment_key(role: str) -> str:
    normalized = str(role or "").strip()
    if re.fullmatch(r"[a-z][a-z0-9-]{0,62}", normalized) is None:
        raise ValueError("Provider runtime role is invalid")
    return (
        "QWQ_PROVIDER_RUNTIME_"
        + normalized.replace("-", "_").upper()
        + "_IMAGE"
    )


def seal_provider_runtime_package_images(
    env_name: str,
    target_name: str,
    candidate_root: Path,
    images: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """Finalize exact Provider image IDs before package fingerprinting."""

    package_ref = "packages/runtime-shared/provider-runtime/manifest.json"
    payload = _read_candidate_object(
        candidate_root,
        package_ref,
        label="Provider runtime package manifest",
    )
    validate_packaged_provider_runtime(
        payload,
        expected_environment=env_name,
        expected_target=target_name,
        candidate_root=candidate_root,
        require_images=False,
    )
    finalized = {**payload, "images": images}
    validate_packaged_provider_runtime(
        finalized,
        expected_environment=env_name,
        expected_target=target_name,
        candidate_root=candidate_root,
        require_images=True,
        verify_package_manifest=False,
    )
    _atomic_write_candidate_file(
        candidate_root,
        package_ref,
        (json.dumps(finalized, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        ),
        label="Provider runtime package manifest",
        expected_current=(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8"),
    )
    return validate_packaged_provider_runtime(
        finalized,
        expected_environment=env_name,
        expected_target=target_name,
        candidate_root=candidate_root,
        require_images=True,
    )


def load_provider_runtime_package(
    env_name: str,
    target_name: str,
    candidate_root: Path,
) -> dict[str, Any]:
    """Load and validate the already-fingerprinted Provider runtime package."""

    payload = _read_candidate_object(
        candidate_root,
        "packages/runtime-shared/provider-runtime/manifest.json",
        label="Provider runtime package manifest",
    )
    return validate_packaged_provider_runtime(
        payload,
        expected_environment=env_name,
        expected_target=target_name,
        candidate_root=candidate_root,
        require_images=True,
    )


def validate_packaged_provider_runtime(
    payload: object,
    *,
    expected_environment: str,
    expected_target: str,
    candidate_root: Path | None,
    require_images: bool = True,
    verify_package_manifest: bool = True,
    require_current_contracts: bool = True,
) -> dict[str, Any]:
    if candidate_root is None:
        raise ValueError(
            "packaged Provider runtime validation requires candidate_root"
        )
    if not isinstance(payload, dict) or set(payload) != {
        "schema",
        "composition",
        "compositionRef",
        "compositionDigest",
        "workloads",
        "images",
    }:
        raise ValueError("deployment candidate Provider runtime fields mismatch")
    if payload.get("schema") != PROVIDER_RUNTIME_PACKAGE_SCHEMA:
        raise ValueError("deployment candidate Provider runtime schema mismatch")
    composition = validate_provider_runtime_composition(
        payload.get("composition"),
        expected_environment=expected_environment,
        expected_target=expected_target,
        require_current_contracts=require_current_contracts,
    )
    composition_ref = _validate_candidate_artifact_ref(
        payload.get("compositionRef"),
        prefix="packages/runtime-shared/provider-runtime/",
        label="Provider runtime composition",
    )
    composition_digest = str(payload.get("compositionDigest") or "")
    if _DIGEST.fullmatch(composition_digest) is None:
        raise ValueError("deployment candidate Provider compositionDigest is invalid")

    workloads = payload.get("workloads")
    if not isinstance(workloads, list):
        raise TypeError("deployment candidate Provider workloads must be a list")
    expected_workloads = {
        str(workload["role"]): str(workload["composeDigest"])
        for workload in composition["workloads"]
    }
    seen_roles: set[str] = set()
    normalized_artifacts: list[tuple[str, str, str]] = []
    for artifact in workloads:
        if not isinstance(artifact, dict) or set(artifact) != {
            "role",
            "sourceComposeDigest",
            "composeRef",
            "composeDigest",
        }:
            raise ValueError(
                "deployment candidate Provider workload artifact fields mismatch"
            )
        role = str(artifact.get("role") or "")
        if not role or role in seen_roles or role not in expected_workloads:
            raise ValueError(
                "deployment candidate Provider workload artifact role mismatch"
            )
        seen_roles.add(role)
        compose_ref = _validate_candidate_artifact_ref(
            artifact.get("composeRef"),
            prefix="packages/runtime-shared/provider-runtime/",
            label=f"Provider workload {role}",
        )
        compose_digest = str(artifact.get("composeDigest") or "")
        source_compose_digest = str(artifact.get("sourceComposeDigest") or "")
        if (
            _DIGEST.fullmatch(compose_digest) is None
            or source_compose_digest != expected_workloads[role]
        ):
            raise ValueError(
                f"deployment candidate Provider workload digest mismatch: {role}"
            )
        normalized_artifacts.append((role, compose_ref, compose_digest))
    if seen_roles != set(expected_workloads):
        raise ValueError("deployment candidate Provider workload closure mismatch")

    images = payload.get("images")
    if not isinstance(images, dict):
        raise TypeError("deployment candidate Provider images must be an object")
    if require_images and set(images) != set(expected_workloads):
        raise ValueError("deployment candidate Provider image closure mismatch")
    if not require_images and images:
        raise ValueError("unsealed Provider runtime package cannot contain images")
    for role, descriptor in images.items():
        if not isinstance(descriptor, dict) or set(descriptor) != {
            "buildInputDigest",
            "ref",
            "imageDigest",
        }:
            raise ValueError("deployment candidate Provider image fields mismatch")
        build_input_digest = str(descriptor.get("buildInputDigest") or "")
        expected_ref = (
            f"quwoquan/provider-runtime-{role}:"
            f"{build_input_digest.removeprefix('sha256:')}"
        )
        if (
            role not in expected_workloads
            or _DIGEST.fullmatch(build_input_digest) is None
            or descriptor.get("ref") != expected_ref
            or _DIGEST.fullmatch(str(descriptor.get("imageDigest") or "")) is None
        ):
            raise ValueError("deployment candidate Provider image identity is invalid")

    if verify_package_manifest:
        try:
            packaged_manifest = _read_candidate_object(
                candidate_root,
                "packages/runtime-shared/provider-runtime/manifest.json",
                label="Provider runtime package manifest",
            )
        except _UnsafeCandidatePath as exc:
            raise ValueError(
                "deployment candidate Provider package manifest is unsafe"
            ) from exc
        if packaged_manifest != payload:
            raise ValueError(
                "deployment candidate Provider package manifest drifted"
            )
    try:
        composition_bytes = _read_candidate_bytes(
            candidate_root,
            composition_ref,
            label="packaged Provider runtime composition",
        )
    except _UnsafeCandidatePath as exc:
        raise ValueError(
            "packaged Provider runtime composition artifact is unsafe"
        ) from exc
    if (
        "sha256:" + hashlib.sha256(composition_bytes).hexdigest()
        != composition_digest
    ):
        raise ValueError("packaged Provider runtime composition artifact drifted")
    try:
        packaged_composition = json.loads(composition_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "packaged Provider runtime composition is unreadable"
        ) from exc
    if packaged_composition != composition:
        raise ValueError("packaged Provider runtime composition bytes mismatch")
    for role, compose_ref, compose_digest in normalized_artifacts:
        try:
            compose_bytes = _read_candidate_bytes(
                candidate_root,
                compose_ref,
                label=f"packaged Provider workload artifact: {role}",
            )
        except _UnsafeCandidatePath as exc:
            raise ValueError(
                f"packaged Provider workload artifact is unsafe: {role}"
            ) from exc
        if (
            "sha256:" + hashlib.sha256(compose_bytes).hexdigest()
            != compose_digest
        ):
            raise ValueError(f"packaged Provider workload artifact drifted: {role}")
        try:
            compose = yaml.safe_load(compose_bytes.decode("utf-8"))
        except (UnicodeError, yaml.YAMLError) as exc:
            raise ValueError(
                f"packaged Provider workload is unreadable: {role}: {exc}"
            ) from exc
        services = compose.get("services") if isinstance(compose, dict) else None
        service = services.get(role) if isinstance(services, dict) else None
        expected_image = (
            "${"
            + provider_runtime_image_environment_key(role)
            + ":?package-bound Provider image is required}"
        )
        if (
            not isinstance(service, dict)
            or service.get("image") != expected_image
            or "build" in service
        ):
            raise ValueError(
                f"packaged Provider workload image selector drifted: {role}"
            )
    return payload


def _validate_candidate_provider_oci_binding(
    candidate: Mapping[str, Any],
    *,
    candidate_root: Path,
) -> None:
    """Cross-bind Provider images to the one package-owned OCI manifest."""

    try:
        oci = _read_candidate_object(
            candidate_root,
            "packages/runtime-shared/oci-images.json",
            label="package OCI image manifest",
        )
    except _UnsafeCandidatePath as exc:
        raise ValueError("deployment candidate OCI image manifest is unsafe") from exc
    if set(oci) != {
        "schema",
        "environment",
        "target",
        "configurationDigest",
        "buildInputDigest",
        "imageDigest",
        "images",
    } or oci.get("schema") != "stackctl-package-oci-images":
        raise ValueError("package OCI image manifest fields mismatch")
    if (
        oci.get("environment") != candidate.get("environment")
        or oci.get("target") != candidate.get("target")
        or oci.get("buildInputDigest") != candidate.get("buildInputDigest")
        or oci.get("imageDigest") != candidate.get("imageDigest")
        or oci.get("configurationDigest") != candidate.get("configurationDigest")
    ):
        raise ValueError("deployment candidate OCI identity drifted")
    images = oci.get("images")
    provider_runtime = candidate.get("providerRuntime")
    provider_images = (
        provider_runtime.get("images")
        if isinstance(provider_runtime, Mapping)
        else None
    )
    if not isinstance(images, dict) or not isinstance(provider_images, dict):
        raise TypeError("deployment candidate OCI image closure is invalid")
    provider_roles = set(provider_images)
    first_party_roles = set(images) - provider_roles
    if not first_party_roles or provider_roles & first_party_roles:
        raise ValueError("deployment candidate OCI image role closure mismatch")
    if {role: images.get(role) for role in provider_roles} != provider_images:
        raise ValueError("deployment candidate Provider images differ from canonical OCI")
    if _sha256_json(images) != oci.get("imageDigest"):
        raise ValueError("deployment candidate OCI imageDigest mismatch")

    if provider_roles:
        first_party_refs: dict[str, str] = {}
        for role in sorted(first_party_roles):
            descriptor = images.get(role)
            if not isinstance(descriptor, Mapping) or set(descriptor) != {
                "ref",
                "imageDigest",
            }:
                raise ValueError(
                    f"deployment candidate first-party image is invalid: {role}"
                )
            first_party_refs[role] = str(descriptor["ref"])
        provider_refs = {
            role: {
                "buildInputDigest": descriptor["buildInputDigest"],
                "ref": descriptor["ref"],
            }
            for role, descriptor in sorted(provider_images.items())
        }
        # 首方镜像在构建期把单环境 Provider binding overlay 编译进二进制，
        # 所以 buildInputDigest 必须闭合到候选内那份 overlay 的 manifest digest：
        # 换绑定就换镜像身份，运行时无从再选。
        overlay = load_provider_binding_overlay(
            str(candidate.get("environment") or ""),
            str(candidate.get("target") or ""),
            candidate_root,
        )
        expected_build_input = _sha256_json(
            {
                "firstPartyImageVersion": immutable_image_digest(first_party_refs),
                "providerRuntimeDigest": provider_runtime["composition"][
                    "runtimeCompositionDigest"
                ],
                "providerBindingManifestDigest": overlay["bindingManifestDigest"],
                "providerImageRefs": provider_refs,
            }
        )
        if oci.get("buildInputDigest") != expected_build_input:
            raise ValueError(
                "deployment candidate Provider buildInputDigest closure mismatch"
            )
