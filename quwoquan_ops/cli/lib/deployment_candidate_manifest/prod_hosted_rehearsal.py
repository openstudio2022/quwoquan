"""prod-hosted exact dev candidate rehearsal material（不可提升的第二类 prevalidate 输入）。

规格：deliver-deploy-prod-pipeline REQ-003 / SIT-003、DEC-013；
zero-risk-production-readiness REQ-003 / GWT-005。

rehearsal 候选就是 integration 工作树用 canonical prod-hosted 打包入口生成的
runtime-full candidate，只是镜像来源不是 GHCR 工厂物料而是本机 build-once 的
``linux/amd64`` content digest。它只能进入 ``prevalidate`` deployment instance，
``releaseEligibility`` 恒为 ``GATE_BLOCK``；formal rollout、frozen diagnostic
snapshot、tag/admission/ledger 路径必须拒绝 ``materialSource=local-build`` 候选。
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.immutable_image_composition import (
    immutable_image_digest,
    runtime_image_owner_names,
)
from quwoquan_ops.cli.lib.service_core_composition import (
    SERVICE_CORE_MODULE_SET,
    SERVICE_CORE_WORKLOAD,
)

from .candidate_fs import (
    _read_candidate_object,
    _sha256_candidate_file,
    _sha256_json,
)
from .constants import ROOT

REHEARSAL_MATERIAL_SOURCE = "local-build"
REHEARSAL_PLATFORM = "linux/amd64"
REHEARSAL_TARGET_ARCH = "amd64"
REHEARSAL_PUBLIC_ENTRY = "host-shared-edge"
REHEARSAL_OCI_FIELDS = frozenset(
    {
        "schema",
        "environment",
        "target",
        "configurationDigest",
        "buildInputDigest",
        "imageDigest",
        "images",
        "materialSource",
        "platform",
        "nonPromotable",
        "legalStaticPlaceholder",
        "publicEntry",
    }
)
LOCAL_IMAGE_REF = re.compile(r"localhost/quwoquan_service_[a-z0-9_]+:[0-9a-f]{64}")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_GIT_SHA = re.compile(r"[0-9a-f]{40}")
DEV_REF = "refs/heads/dev1.0"


class RehearsalError(ValueError):
    """rehearsal 候选来源、架构或 digest 不成立时的 typed 阻断。"""


def is_rehearsal_oci_manifest(oci: object) -> bool:
    return isinstance(oci, Mapping) and oci.get("materialSource") == REHEARSAL_MATERIAL_SOURCE


def compose_service_image_owner(service: str) -> str:
    """compose 服务到运行时镜像 owner 的唯一映射：core module 共用 service-core。"""

    name = str(service).strip()
    if name in SERVICE_CORE_MODULE_SET:
        return SERVICE_CORE_WORKLOAD
    return name


def local_image_repository(owner: str) -> str:
    if owner == SERVICE_CORE_WORKLOAD:
        return "localhost/quwoquan_service_core"
    return "localhost/quwoquan_service_" + owner.replace("-", "_")


def rehearsal_build_input_digest(
    refs: Mapping[str, str],
    *,
    provider_runtime_digest: str,
    legal_static_placeholder: bool,
) -> str:
    payload = {
        "firstPartyImageVersion": immutable_image_digest(dict(refs)),
        "providerRuntimeDigest": provider_runtime_digest,
        "providerImageRefs": {},
        "materialSource": REHEARSAL_MATERIAL_SOURCE,
        "platform": REHEARSAL_PLATFORM,
        "legalStaticPlaceholder": bool(legal_static_placeholder),
    }
    encoded = json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def validate_rehearsal_oci_manifest(
    oci: object,
    *,
    expected_owners: Sequence[str] | None = None,
    expected_environment: str = "prod",
    expected_target: str = "prod-hosted",
) -> dict[str, str]:
    """校验 rehearsal oci-images.json 并返回 owner -> 本地镜像 ref。"""

    if not isinstance(oci, Mapping):
        raise RehearsalError("rehearsal OCI manifest must be an object")
    if set(oci) != REHEARSAL_OCI_FIELDS:
        raise RehearsalError("rehearsal OCI manifest fields mismatch")
    if oci.get("materialSource") != REHEARSAL_MATERIAL_SOURCE:
        raise RehearsalError("rehearsal OCI manifest materialSource mismatch")
    if oci.get("platform") != REHEARSAL_PLATFORM:
        raise RehearsalError("rehearsal OCI manifest platform must be linux/amd64")
    if oci.get("nonPromotable") is not True:
        raise RehearsalError("rehearsal OCI manifest must declare nonPromotable=true")
    if not isinstance(oci.get("legalStaticPlaceholder"), bool):
        raise RehearsalError("rehearsal OCI manifest legalStaticPlaceholder must be boolean")
    if oci.get("publicEntry") != REHEARSAL_PUBLIC_ENTRY:
        raise RehearsalError("rehearsal OCI manifest publicEntry must be host-shared-edge")
    if (
        oci.get("environment") != expected_environment
        or oci.get("target") != expected_target
    ):
        raise RehearsalError("rehearsal OCI manifest target identity mismatch")
    images = oci.get("images")
    owners = tuple(expected_owners or runtime_image_owner_names())
    if not isinstance(images, Mapping) or set(images) != set(owners):
        raise RehearsalError("rehearsal OCI manifest image owner closure mismatch")
    refs: dict[str, str] = {}
    for owner in sorted(owners):
        descriptor = images.get(owner)
        if not isinstance(descriptor, Mapping) or set(descriptor) != {"ref", "imageDigest"}:
            raise RehearsalError(f"rehearsal image descriptor is invalid: {owner}")
        ref = str(descriptor.get("ref") or "")
        digest = str(descriptor.get("imageDigest") or "")
        if (
            LOCAL_IMAGE_REF.fullmatch(ref) is None
            or not ref.startswith(local_image_repository(owner) + ":")
            or _DIGEST.fullmatch(digest) is None
        ):
            raise RehearsalError(f"rehearsal image ref is not a local build digest: {owner}")
        refs[owner] = ref
    for field in ("configurationDigest", "buildInputDigest", "imageDigest"):
        if _DIGEST.fullmatch(str(oci.get(field) or "")) is None:
            raise RehearsalError(f"rehearsal OCI manifest {field} is invalid")
    return refs


def _run_git(args: Sequence[str], *, repo_root: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RehearsalError(
            "git readback failed for rehearsal source gate: " + " ".join(args)
        )
    return result.stdout.strip()


def rehearsal_candidate_source_gate(
    candidate: Mapping[str, Any],
    *,
    repo_root: Path,
) -> dict[str, str]:
    """SIT-003 t1：候选 sourceRevision 必须同时等于 HEAD 与本地 dev1.0，且工作树干净。"""

    source_revision = str(candidate.get("sourceRevision") or "")
    if _GIT_SHA.fullmatch(source_revision) is None:
        raise RehearsalError("rehearsal candidate sourceRevision is invalid")
    dirty = _run_git(
        ["status", "--porcelain", "--untracked-files=normal"], repo_root=repo_root
    )
    if dirty:
        raise RehearsalError("rehearsal refuses an uncommitted worktree")
    head = _run_git(["rev-parse", "HEAD"], repo_root=repo_root)
    if head != source_revision:
        raise RehearsalError("rehearsal candidate sourceRevision does not match HEAD")
    dev_head = _run_git(["rev-parse", "--verify", "--quiet", DEV_REF], repo_root=repo_root)
    if dev_head != source_revision:
        raise RehearsalError(
            "rehearsal candidate must be the exact local dev1.0 head"
        )
    return {"head": head, "devHead": dev_head, "sourceRevision": source_revision}


def _docker_inspect(ref: str, template: str) -> str | None:
    result = subprocess.run(
        ["docker", "image", "inspect", "--format", template, ref],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def verify_local_rehearsal_images(
    oci: Mapping[str, Any],
    *,
    expected_owners: Sequence[str] | None = None,
) -> dict[str, str]:
    """SIT-003 t1/t2：本地镜像必须存在、为 amd64 且 content digest 与候选一致。"""

    refs = validate_rehearsal_oci_manifest(oci, expected_owners=expected_owners)
    images = oci["images"]
    verified: dict[str, str] = {}
    for owner, ref in sorted(refs.items()):
        arch = _docker_inspect(ref, "{{.Architecture}}")
        digest = _docker_inspect(ref, "{{.Id}}")
        expected = str(images[owner]["imageDigest"])
        if arch is None or digest is None:
            raise RehearsalError(f"rehearsal image is missing locally: {ref}")
        if arch != REHEARSAL_TARGET_ARCH:
            raise RehearsalError(
                f"rehearsal image is not {REHEARSAL_PLATFORM}: {owner}={arch}"
            )
        if digest != expected:
            raise RehearsalError(
                f"rehearsal image content digest drifted: {owner}: {digest} != {expected}"
            )
        verified[owner] = digest
    return verified


def rehearsal_configuration_digest(
    candidate_root: Path,
    *,
    expected_services: Sequence[str],
    expected_source_revision: str,
) -> str:
    """rehearsal 候选的配置身份：与正式路径同一 configVersion 摘要，但不要求 release evidence。"""

    configuration_versions: dict[str, str] = {}
    for service in sorted(expected_services):
        provenance = _read_candidate_object(
            candidate_root,
            f"packages/services/{service}/provenance.json",
            label=f"hosted service package provenance: {service}",
        )
        digests = provenance.get("digests")
        if (
            provenance.get("schema") != "qwq.service_package"
            or provenance.get("service") != service
            or provenance.get("environment") != "prod"
            or provenance.get("gitRevision") != expected_source_revision
            or not isinstance(digests, dict)
        ):
            raise ValueError(
                f"deployment candidate rehearsal package provenance mismatch: {service}"
            )
        config_version = str(provenance.get("configVersion") or "")
        actual_config_digest = _sha256_candidate_file(
            candidate_root,
            f"packages/services/{service}/config/config.yaml",
            label=f"hosted service runtime configuration: {service}",
        )
        if (
            _DIGEST.fullmatch(config_version) is None
            or str(digests.get("config") or "") != actual_config_digest
        ):
            raise ValueError(
                f"deployment candidate rehearsal configuration identity drifted: {service}"
            )
        configuration_versions[service] = config_version
    return _sha256_json(configuration_versions)


def materialize_prod_hosted_rehearsal_oci_manifest(
    env_name: str,
    target_name: str,
    *,
    report_dir: Path,
    provider_runtime: Mapping[str, Any],
    provider_binding_overlay: Mapping[str, Any],
    candidate_root: Path,
    package_snapshot: Mapping[str, object],
    legal_static_placeholder: bool,
    source_root: Path = ROOT,
) -> tuple[Path, dict[str, Any]]:
    """Build the exact dev candidate's linux/amd64 images once and seal them as rehearsal material.

    DEC-013：这是 prevalidate 的第二类不可提升输入；镜像 owner 集合与 prod 运行时
    一致，content digest 在本机构建后立即封进候选，任何 formal 路径都拒绝该候选。
    """

    from quwoquan_ops.cli import stackctl as _stackctl

    if env_name != "prod" or target_name != "prod-hosted":
        raise ValueError("rehearsal OCI manifest supports only prod/prod-hosted")
    unsealed_composition = provider_runtime.get("composition")
    if (
        not isinstance(unsealed_composition, Mapping)
        or provider_runtime.get("images") != {}
    ):
        raise ValueError("prod-hosted Provider runtime package is not unsealed")
    candidate_digest = str(package_snapshot.get("baselineId") or "")
    if _DIGEST.fullmatch(candidate_digest) is None:
        raise ValueError("rehearsal candidate digest is invalid")
    source_revision = str(package_snapshot.get("sourceRevision") or "")
    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, target_name)
    build_images = target.get("buildImages") if isinstance(target, Mapping) else None
    if not isinstance(build_images, Mapping):
        raise ValueError("prod-hosted target declares no buildImages for rehearsal builds")
    environment: dict[str, str] = {}
    for key, env_key in (
        ("goBaseImage", "QWQ_COMPOSE_GO_BASE_IMAGE"),
        ("alpineBaseImage", "QWQ_COMPOSE_ALPINE_BASE_IMAGE"),
        ("pythonBaseImage", "QWQ_COMPOSE_PYTHON_BASE_IMAGE"),
    ):
        value = str(build_images.get(key) or "").strip()
        if not value:
            raise ValueError(f"prod-hosted buildImages.{key} is required for rehearsal builds")
        environment[env_key] = value
    environment.update(
        {
            "QWQ_LOCAL_RELEASE_TARGET": target_name,
            "QWQ_RUN_ROOT": str(report_dir.resolve()),
            "QWQ_OBSERVABILITY_RUN_ROOT": str(
                _stackctl.env_observability_run_dir(env_name, report_dir.name).resolve()
            ),
            "QWQ_WORKLOAD": "full",
            "QWQ_RELEASE_CANDIDATE_DIGEST": candidate_digest,
            "QWQ_COMPOSE_ENV": env_name,
            # rehearsal 镜像只面向 x86_64 单机：docker build 统一按 linux/amd64 交叉构建。
            "DOCKER_DEFAULT_PLATFORM": REHEARSAL_PLATFORM,
        }
    )
    overlay_dir, _, binding_manifest_digest = (
        _stackctl.provider_binding_overlay_build_inputs(
            provider_binding_overlay,
            candidate_root=candidate_root,
            build_context=source_root,
        )
    )
    environment["QWQ_PROVIDER_BINDING_OVERLAY_CONTEXT"] = str(overlay_dir)
    environment["QWQ_PROVIDER_BINDING_MANIFEST_DIGEST"] = binding_manifest_digest
    composition = _stackctl._bind_gamma_build_service_image_refs(
        env_name,
        environment,
        candidate_digest=candidate_digest,
    )
    refs = {
        service: str(descriptor["ref"])
        for service, descriptor in sorted(composition["images"].items())
    }

    def inspect_images() -> tuple[dict[str, dict[str, str]], list[str]]:
        inspected: dict[str, dict[str, str]] = {}
        missing: list[str] = []
        for service, ref in sorted(refs.items()):
            inspect = _stackctl.run(
                ["docker", "image", "inspect", "--format", "{{.Id}} {{.Architecture}}", ref]
            )
            parts = inspect.stdout.strip().split()
            if inspect.returncode != 0 or len(parts) != 2:
                missing.append(service)
                continue
            image_digest, arch = parts
            if _DIGEST.fullmatch(image_digest) is None:
                missing.append(service)
                continue
            if arch != REHEARSAL_TARGET_ARCH:
                raise ValueError(
                    f"rehearsal image tag exists but is not {REHEARSAL_PLATFORM}: "
                    f"{service}={arch}"
                )
            inspected[service] = {"ref": ref, "imageDigest": image_digest}
        return inspected, missing

    images, missing_images = inspect_images()
    build_results: list[subprocess.CompletedProcess[str]] = []
    if missing_images:
        build_results = _stackctl._build_missing_runtime_images(
            missing_images,
            source_root=source_root,
            environment=environment,
            refs=composition["images"],
        )
        images, missing_images = inspect_images()
    if missing_images:
        details = [
            "rehearsal OCI digest is unavailable: " + ", ".join(missing_images)
        ]
        for build_result in build_results:
            for stream_value in (build_result.stdout, build_result.stderr):
                normalized = stream_value.strip()
                if normalized:
                    details.append("OCI build tail: " + normalized[-4000:])
        raise RuntimeError("\n".join(details))
    sealed_provider_runtime = _stackctl.seal_provider_runtime_package_images(
        env_name,
        target_name,
        candidate_root,
        {},
    )
    if sealed_provider_runtime.get("composition") != unsealed_composition:
        raise ValueError("prod-hosted Provider runtime composition drifted while sealing")
    configuration_digest = rehearsal_configuration_digest(
        candidate_root,
        expected_services=tuple(_stackctl.first_party_service_names(source_root)),
        expected_source_revision=source_revision,
    )
    manifest = {
        "schema": _stackctl.PACKAGE_OCI_IMAGES_SCHEMA,
        "environment": env_name,
        "target": target_name,
        "configurationDigest": configuration_digest,
        "buildInputDigest": rehearsal_build_input_digest(
            refs,
            provider_runtime_digest=str(
                unsealed_composition.get("runtimeCompositionDigest") or ""
            ),
            legal_static_placeholder=legal_static_placeholder,
        ),
        "imageDigest": _sha256_json(images),
        "images": images,
        "materialSource": REHEARSAL_MATERIAL_SOURCE,
        "platform": REHEARSAL_PLATFORM,
        "nonPromotable": True,
        "legalStaticPlaceholder": bool(legal_static_placeholder),
        "publicEntry": REHEARSAL_PUBLIC_ENTRY,
    }
    validate_rehearsal_oci_manifest(manifest)
    manifest_path = (
        _stackctl.runtime_shared_deployment_package_dir(env_name, target=target_name)
        / "oci-images.json"
    )
    _stackctl.write_json(manifest_path, manifest)
    return manifest_path, manifest


def validate_prod_hosted_rehearsal_oci_binding(
    candidate: Mapping[str, Any],
    oci: Mapping[str, Any],
    *,
    candidate_root: Path,
) -> None:
    """rehearsal 候选：本地 amd64 镜像 digest 闭包 + 非提升标记，零 release evidence。"""


    provider_runtime = candidate.get("providerRuntime")
    provider_images = (
        provider_runtime.get("images")
        if isinstance(provider_runtime, Mapping)
        else None
    )
    composition = (
        provider_runtime.get("composition")
        if isinstance(provider_runtime, Mapping)
        else None
    )
    if (
        not isinstance(provider_images, dict)
        or provider_images
        or not isinstance(composition, Mapping)
    ):
        raise ValueError("deployment candidate rehearsal Provider runtime closure is invalid")
    try:
        refs = validate_rehearsal_oci_manifest(oci)
    except RehearsalError as exc:
        raise ValueError(str(exc)) from exc
    fingerprint = _read_candidate_object(
        candidate_root,
        "packages/app/package-fingerprint.json",
        label="package fingerprint",
    )
    service_packages = fingerprint.get("servicePackages")
    if not isinstance(service_packages, list) or any(
        not isinstance(service, str) for service in service_packages
    ):
        raise ValueError("deployment candidate rehearsal service closure is invalid")
    expected_configuration = rehearsal_configuration_digest(
        candidate_root,
        expected_services=service_packages,
        expected_source_revision=str(candidate.get("sourceRevision") or ""),
    )
    if oci.get("configurationDigest") != expected_configuration:
        raise ValueError("deployment candidate rehearsal configuration identity drifted")
    expected_build_input = rehearsal_build_input_digest(
        refs,
        provider_runtime_digest=str(composition.get("runtimeCompositionDigest") or ""),
        legal_static_placeholder=bool(oci.get("legalStaticPlaceholder")),
    )
    if oci.get("buildInputDigest") != expected_build_input:
        raise ValueError("deployment candidate rehearsal buildInputDigest closure mismatch")
    if oci.get("imageDigest") != _sha256_json(oci.get("images")):
        raise ValueError("deployment candidate rehearsal imageDigest closure mismatch")


