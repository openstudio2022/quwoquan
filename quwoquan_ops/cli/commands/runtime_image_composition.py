"""stackctl 运行时镜像组装域: 镜像构建 spec、缺失镜像补建、package-bound
本地镜像组合加载，以及 packaged/release/teardown 三种镜像 refs 绑定。

从 stackctl.py 逐字迁出（改写规则与 down_domain 相同）:
`_sha256_file` / `_sha256_tree` / `_packaged_service_source_image_ref` /
`_bind_gamma_build_service_image_refs` / `_runtime_image_build_spec` /
`_build_missing_runtime_images` / `_provider_runtime_build_specs` /
`_build_provider_runtime_images` / `_load_package_bound_local_image_composition`。

镜像 refs 绑定族从 `gamma_release_binding` 逐字迁入，因为它们与本模块的
composition 加载是同一个责任——把一份已验证的镜像身份投影进 Compose
environment；`gamma_release_binding` 保留的是 Provider/对象存储/release
evidence 这一族环境绑定。

测试经 ``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号，
因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问（含本模块符号互调），
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import concurrent
import concurrent.futures
import hashlib
import json
import re
import subprocess

from collections.abc import Sequence
from pathlib import Path
from typing import Any
from typing import Mapping


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _sha256_tree(directory: Path) -> str:
    """生成目录的路径敏感内容摘要，作为静态包可复算的供应链证据。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        digest.update(path.relative_to(directory).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(_stackctl._sha256_file(path).encode("ascii"))
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def _packaged_service_source_image_ref(env_name: str, service: str) -> str:
    import quwoquan_ops.cli.stackctl as _stackctl

    return _stackctl.packaged_runtime_source_image_ref(env_name, service)


def candidate_service_config_versions(target: str = "gamma-local") -> dict[str, str]:
    """服务 CONFIG_VERSION 的唯一真相源：active candidate 内各服务 provenance。

    compose 模板对每个服务强制声明 `QWQ_COMPOSE_<SERVICE>_CONFIG_VERSION`；
    该值只能来自 candidate 包，不接受手写。candidate 缺席时返回空集，
    up 保持不注入由 compose fail-closed。
    """
    from quwoquan_ops.cli.lib.output_paths import active_candidate_manifest_path

    versions: dict[str, str] = {}
    try:
        pointer = active_candidate_manifest_path(target)
        if not pointer.is_file():
            return versions
        candidate_dir = Path(
            json.loads(pointer.read_text(encoding="utf-8")).get("candidateDir", "")
        )
        services_root = candidate_dir / "packages" / "services"
        if not services_root.is_dir():
            return versions
        for provenance_path in sorted(services_root.glob("*/provenance.json")):
            payload = json.loads(provenance_path.read_text(encoding="utf-8"))
            service = str(payload.get("service", "")).strip()
            version = str(payload.get("configVersion", "")).strip()
            if service and version:
                versions[service] = version
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return versions


def compose_config_version_environment_key(service: str) -> str:
    return "QWQ_COMPOSE_" + service.upper().replace("-", "_") + "_CONFIG_VERSION"


def packaged_service_build_image_ref(
    env_name: str,
    service: str,
    *,
    binding_manifest_digest: str,
    candidate_digest: str = "",
) -> str:
    """Derive the one build tag a packaged first-party image carries.

    The tag folds in the Provider binding manifest digest because the image
    compiles that single-environment binding into its binary: rebinding must
    mint a new image identity rather than reuse the source-digest tag. ``up``
    reads the packaged manifest back through this same derivation, so producer
    and consumer cannot drift into two tag vocabularies.
    """
    import quwoquan_ops.cli.stackctl as _stackctl

    if re.fullmatch(r"sha256:[0-9a-f]{64}", binding_manifest_digest) is None:
        raise ValueError("runtime image Provider binding manifest digest is unavailable")
    if service == _stackctl.SERVICE_CORE_WORKLOAD and candidate_digest:
        if re.fullmatch(r"sha256:[0-9a-f]{64}", candidate_digest) is None:
            raise ValueError("service-core candidate digest is invalid")
        base_ref = (
            "localhost/quwoquan_service_core:"
            + candidate_digest.removeprefix("sha256:")
        )
    else:
        base_ref = _stackctl._packaged_service_source_image_ref(env_name, service)
    repository, _, base_tag = base_ref.rpartition(":")
    build_tag = hashlib.sha256(
        (service + "\x00" + base_tag + "\x00" + binding_manifest_digest).encode("utf-8")
    ).hexdigest()
    return repository + ":" + build_tag


def _bind_gamma_build_service_image_refs(
    env_name: str,
    environment: dict[str, str],
    *,
    candidate_digest: str = "",
) -> dict[str, Any]:
    """Bind deterministic build tags only while materializing a candidate."""
    import quwoquan_ops.cli.stackctl as _stackctl


    binding_manifest_digest = str(
        environment.get("QWQ_PROVIDER_BINDING_MANIFEST_DIGEST") or ""
    ).strip()
    refs: dict[str, str] = {}
    for service, local_key in _stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS:
        ref = packaged_service_build_image_ref(
            env_name,
            service,
            binding_manifest_digest=binding_manifest_digest,
            candidate_digest=candidate_digest,
        )
        refs[service] = ref
        environment[local_key] = ref
        environment[_stackctl.compose_image_environment_key(service)] = ref
    composition_version = _stackctl.immutable_image_digest(refs)
    environment["LOCAL_GAMMA_IMAGE_VERSION"] = composition_version
    environment["QWQ_COMPOSE_IMAGE_VERSION"] = composition_version
    environment["QWQ_COMPOSE_IMAGE_TAG"] = composition_version.removeprefix("sha256:")
    # compose 模板对每个服务强制声明配置版本；唯一真相源是 active candidate 包
    # 内各服务 provenance.configVersion，缺席时保持不注入由 compose fail-closed。
    for service, version in candidate_service_config_versions().items():
        environment[compose_config_version_environment_key(service)] = version
    composition: dict[str, Any] = {
        "imageVersion": composition_version,
        "images": {
            service: {"ref": ref}
            for service, ref in sorted(refs.items())
        },
    }
    _stackctl._bind_gamma_packaged_configuration_digest(env_name, environment, composition)
    return composition


def _runtime_image_build_spec(
    service: str,
    *,
    source_root: Path,
    environment: Mapping[str, str],
) -> tuple[Path, Path, dict[str, str]]:
    import quwoquan_ops.cli.stackctl as _stackctl

    # 环境身份不进 build args：镜像字节环境无关（DEC-005 信任域裁决），
    # artifact-identity.json 由部署面在 up/package 时生成并挂载。
    artifact_args: dict[str, str] = {}
    overlay_context = str(
        environment.get("QWQ_PROVIDER_BINDING_OVERLAY_CONTEXT") or ""
    ).strip()
    binding_manifest_digest = str(
        environment.get("QWQ_PROVIDER_BINDING_MANIFEST_DIGEST") or ""
    ).strip()
    if service != "recommendation-service":
        if not overlay_context or not Path(overlay_context).is_dir():
            raise ValueError("runtime image Provider binding overlay is unavailable")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", binding_manifest_digest) is None:
            raise ValueError("runtime image Provider binding manifest digest is unavailable")
        artifact_args["QWQ_PROVIDER_BINDING_OVERLAY_CONTEXT"] = overlay_context
        artifact_args["QWQ_PROVIDER_BINDING_MANIFEST_DIGEST"] = binding_manifest_digest
    if service == _stackctl.SERVICE_CORE_WORKLOAD:
        context = (source_root / "quwoquan_service").resolve()
        dockerfile = (context / "cmd/service-core/Dockerfile").resolve()
        core_args: dict[str, str] = {}
        for arg_name, environment_key in (
            ("GO_BASE_IMAGE", "QWQ_COMPOSE_GO_BASE_IMAGE"),
            ("ALPINE_BASE_IMAGE", "QWQ_COMPOSE_ALPINE_BASE_IMAGE"),
        ):
            arg_value = str(environment.get(environment_key) or "").strip()
            if not arg_value:
                raise ValueError(
                    f"runtime image build arg is unresolved: {service}:{arg_name}"
                )
            core_args[arg_name] = arg_value
        core_args.update(artifact_args)
        return context, dockerfile, core_args
    if service == "platform-ops-service":
        compose_path = (
            source_root
            / "quwoquan_service"
            / "control-plane"
            / "platform-ops"
            / "deploy/compose.yaml"
        )
    else:
        compose_path = (
            source_root
            / "quwoquan_service"
            / "services"
            / service
            / "deploy/compose.yaml"
        )
    compose = _stackctl.load_json_yaml(compose_path)
    services = compose.get("services") if isinstance(compose, Mapping) else None
    definition = services.get(service) if isinstance(services, Mapping) else None
    build = definition.get("build") if isinstance(definition, Mapping) else None
    if not isinstance(build, Mapping):
        raise ValueError(f"runtime image owner has no build definition: {service}")
    compose_project_directory = (
        source_root / "quwoquan_ops" / "environments" / "compose"
    )
    context = (
        compose_project_directory / str(build.get("context") or "")
    ).resolve()
    dockerfile = (context / str(build.get("dockerfile") or "Dockerfile")).resolve()
    if (
        not context.is_relative_to(source_root.resolve())
        or not context.is_dir()
        or not dockerfile.is_relative_to(context)
        or not dockerfile.is_file()
    ):
        raise ValueError(f"runtime image build input is unsafe: {service}")
    raw_args = build.get("args") or {}
    if not isinstance(raw_args, Mapping):
        raise ValueError(f"runtime image build args are invalid: {service}")
    build_args: dict[str, str] = {}
    for raw_name, raw_value in raw_args.items():
        name = str(raw_name or "").strip()
        value = str(raw_value or "").strip()
        reference = re.fullmatch(
            r"\$\{([A-Z][A-Z0-9_]*)(?::([-?])([^}]*))?\}",
            value,
        )
        if reference is not None:
            resolved = str(environment.get(reference.group(1)) or "")
            if not resolved and reference.group(2) == "-":
                # 只有 `:-` 形式的默认值可以回填;`:?` 的文本是错误信息,不是值。
                resolved = str(reference.group(3) or "")
            value = resolved
        if not name or not value or "${" in value:
            raise ValueError(f"runtime image build arg is unresolved: {service}:{name}")
        build_args[name] = value
    build_args.update(artifact_args)
    return context, dockerfile, build_args


def _build_missing_runtime_images(
    services: Sequence[str],
    *,
    source_root: Path,
    environment: Mapping[str, str],
    refs: Mapping[str, Mapping[str, str]],
) -> list[subprocess.CompletedProcess[str]]:
    import quwoquan_ops.cli.stackctl as _stackctl

    results: list[subprocess.CompletedProcess[str]] = []
    for service in services:
        descriptor = refs.get(service)
        if not isinstance(descriptor, Mapping):
            raise ValueError(f"runtime image ref is missing: {service}")
        context, dockerfile, build_args = _stackctl._runtime_image_build_spec(
            service,
            source_root=source_root,
            environment=environment,
        )
        command = [
            "docker",
            "build",
            "--tag",
            str(descriptor["ref"]),
            "--file",
            str(dockerfile),
        ]
        overlay_context = build_args.pop(
            "QWQ_PROVIDER_BINDING_OVERLAY_CONTEXT",
            "",
        )
        if overlay_context:
            command.extend(
                [
                    "--build-context",
                    f"qwq_provider_bindings={overlay_context}",
                ]
            )
        for name, value in sorted(build_args.items()):
            command.extend(["--build-arg", f"{name}={value}"])
        command.append(str(context))
        result = _stackctl.run(command, cwd=source_root, env=dict(environment))
        results.append(result)
        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip()
                or result.stdout.strip()
                or f"package-bound OCI build failed: {service}"
            )
    return results


def _provider_runtime_build_specs(
    provider_runtime: Mapping[str, Any],
    environment: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Resolve package-time build inputs from the canonical Provider composition."""
    import quwoquan_ops.cli.stackctl as _stackctl


    composition = provider_runtime.get("composition")
    if not isinstance(composition, Mapping):
        raise TypeError("Provider runtime composition is invalid")
    environment_name = str(composition.get("environment") or "").strip()
    target_name = str(composition.get("target") or "").strip()
    validated = _stackctl.validate_provider_runtime_composition(
        dict(composition),
        expected_environment=environment_name,
        expected_target=target_name,
    )
    runtime_digest = str(validated["runtimeCompositionDigest"])
    specs: list[dict[str, Any]] = []
    for workload in validated["workloads"]:
        role = str(workload["role"])
        compose_path = (_stackctl.ROOT / str(workload["composeRef"])).resolve()
        if (
            not compose_path.is_relative_to(_stackctl.ROOT)
            or not compose_path.is_file()
            or _stackctl._sha256_file(compose_path) != workload["composeDigest"]
        ):
            raise ValueError(f"Provider build Compose source drifted: {role}")
        compose = _stackctl.load_json_yaml(compose_path)
        services = compose.get("services") if isinstance(compose, Mapping) else None
        service = services.get(role) if isinstance(services, Mapping) else None
        build = service.get("build") if isinstance(service, Mapping) else None
        if not isinstance(build, Mapping):
            raise ValueError(f"Provider workload has no package-time build: {role}")
        context_value = str(build.get("context") or "").strip()
        dockerfile_value = str(build.get("dockerfile") or "Dockerfile").strip()
        context_path = (compose_path.parent / context_value).resolve()
        dockerfile_path = (context_path / dockerfile_value).resolve()
        if (
            not context_value
            or not context_path.is_relative_to(_stackctl.ROOT)
            or not context_path.is_dir()
            or not dockerfile_path.is_relative_to(context_path)
            or not dockerfile_path.is_file()
        ):
            raise ValueError(f"Provider build context is unsafe: {role}")
        raw_args = build.get("args") or {}
        if not isinstance(raw_args, Mapping):
            raise TypeError(f"Provider build args are invalid: {role}")
        build_args: dict[str, str] = {}
        for name, raw_value in sorted(raw_args.items()):
            argument_name = str(name or "").strip()
            value = str(raw_value or "").strip()
            if re.fullmatch(r"[A-Z][A-Z0-9_]*", argument_name) is None:
                raise ValueError(f"Provider build argument name is invalid: {role}")
            reference = re.fullmatch(
                r"\$\{([A-Z][A-Z0-9_]*)(?::[-?][^}]*)?\}",
                value,
            )
            if reference is not None:
                source_key = reference.group(1)
                resolved = str(environment.get(source_key) or "").strip()
                if not resolved and source_key.startswith("QWQ_COMPOSE_"):
                    resolved = str(
                        environment.get(
                            "LOCAL_GAMMA_" + source_key.removeprefix("QWQ_COMPOSE_")
                        )
                        or ""
                    ).strip()
                if not resolved:
                    raise ValueError(
                        f"Provider build argument material is missing: {source_key}"
                    )
                value = resolved
            elif "${" in value:
                raise ValueError(f"Provider build argument expression is invalid: {role}")
            build_args[argument_name] = value
        context_digest = _stackctl._sha256_tree(context_path)
        dockerfile_digest = _stackctl._sha256_file(dockerfile_path)
        build_input_digest = "sha256:" + hashlib.sha256(
            json.dumps(
                {
                    "role": role,
                    "runtimeCompositionDigest": runtime_digest,
                    "contextDigest": context_digest,
                    "dockerfileRef": dockerfile_path.relative_to(context_path).as_posix(),
                    "dockerfileDigest": dockerfile_digest,
                    "buildArgs": build_args,
                },
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        specs.append(
            {
                "role": role,
                "buildInputDigest": build_input_digest,
                "ref": (
                    f"quwoquan/provider-runtime-{role}:"
                    f"{build_input_digest.removeprefix('sha256:')}"
                ),
                "context": context_path,
                "dockerfile": dockerfile_path,
                "buildArgs": build_args,
            }
        )
    return specs


def _build_provider_runtime_images(
    provider_runtime: Mapping[str, Any],
    environment: Mapping[str, str],
) -> dict[str, dict[str, str]]:
    """Build missing Provider images once and return exact local image IDs."""
    import quwoquan_ops.cli.stackctl as _stackctl


    specs = _stackctl._provider_runtime_build_specs(provider_runtime, environment)
    images: dict[str, dict[str, str]] = {}
    for spec in specs:
        role = str(spec["role"])
        image_ref = str(spec["ref"])
        inspect = _stackctl.run(
            ["docker", "image", "inspect", "--format", "{{.Id}}", image_ref]
        )
        image_digest = inspect.stdout.strip()
        if (
            inspect.returncode != 0
            or re.fullmatch(r"sha256:[0-9a-f]{64}", image_digest) is None
        ):
            command = [
                "docker",
                "build",
                "--tag",
                image_ref,
                "--file",
                str(spec["dockerfile"]),
            ]
            for name, value in sorted(spec["buildArgs"].items()):
                command.extend(["--build-arg", f"{name}={value}"])
            command.append(str(spec["context"]))
            result = _stackctl.run(command)
            if result.returncode != 0:
                raise RuntimeError(
                    result.stderr.strip()
                    or result.stdout.strip()
                    or f"Provider image build failed: {role}"
                )
            inspect = _stackctl.run(
                ["docker", "image", "inspect", "--format", "{{.Id}}", image_ref]
            )
            image_digest = inspect.stdout.strip()
        if (
            inspect.returncode != 0
            or re.fullmatch(r"sha256:[0-9a-f]{64}", image_digest) is None
        ):
            raise RuntimeError(f"Provider image digest is unavailable: {role}")
        images[role] = {
            "buildInputDigest": str(spec["buildInputDigest"]),
            "ref": image_ref,
            "imageDigest": image_digest,
        }
    return images


def _load_package_bound_local_image_composition(
    env_name: str,
    target_name: str,
    *,
    candidate_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Load exact image IDs from the activated or staging package manifest."""
    import quwoquan_ops.cli.stackctl as _stackctl


    if candidate_snapshot is None:
        active = _stackctl.active_deployment_candidate(target_name)
        if not isinstance(active, dict):
            raise ValueError("package OCI runtime has no active deployment candidate")
        baseline_id = str(active.get("baselineId") or "").strip()
        candidate_root = _stackctl.deployment_candidate_dir(target_name, baseline_id)
        candidate = _stackctl.load_candidate_manifest(
            env_name,
            target_name,
            baseline_id,
            require_full=True,
        )
    else:
        baseline_id, candidate_root, candidate = _stackctl._fixed_candidate_identity(
            candidate_snapshot,
            environment_name=env_name,
            target_name=target_name,
        )
    manifest_path = candidate_root / "packages/runtime-shared/oci-images.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError("active candidate OCI image manifest is missing or unsafe")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"package OCI image manifest is unreadable: {exc}") from exc
    required = {
        "schema",
        "environment",
        "target",
        "configurationDigest",
        "buildInputDigest",
        "imageDigest",
        "images",
    }
    if not isinstance(manifest, dict) or set(manifest) != required:
        raise ValueError("package OCI image manifest fields mismatch")
    if manifest.get("schema") != _stackctl.PACKAGE_OCI_IMAGES_SCHEMA:
        raise ValueError("package OCI image manifest schema mismatch")
    if manifest.get("environment") != env_name or manifest.get("target") != target_name:
        raise ValueError("package OCI image manifest target identity mismatch")
    for field in ("configurationDigest", "buildInputDigest", "imageDigest"):
        if re.fullmatch(r"sha256:[0-9a-f]{64}", str(manifest.get(field) or "")) is None:
            raise ValueError(f"package OCI image manifest {field} is invalid")
    provider_runtime = candidate.get("providerRuntime")
    if not isinstance(provider_runtime, Mapping):
        raise ValueError("active candidate Provider runtime is missing")
    provider_images = provider_runtime.get("images")
    if not isinstance(provider_images, Mapping):
        raise ValueError("active candidate Provider image closure is invalid")
    images = manifest.get("images")
    first_party_services = {
        service for service, _ in _stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS
    }
    expected_services = first_party_services | set(provider_images)
    if not isinstance(images, dict) or set(images) != expected_services:
        raise ValueError("package OCI image manifest service set mismatch")
    from quwoquan_ops.cli.lib.deployment_candidate_manifest.provider_binding_overlay import (
        load_provider_binding_overlay,
    )

    binding_manifest_digest = str(
        load_provider_binding_overlay(
            env_name, target_name, candidate_root
        ).get("bindingManifestDigest")
        or ""
    )
    first_party_runtime_refs: dict[str, str] = {}
    normalized_images: dict[str, dict[str, str]] = {}
    for service in sorted(expected_services):
        descriptor = images.get(service)
        expected_descriptor_fields = (
            {"ref", "imageDigest"}
            if service in first_party_services
            else {"buildInputDigest", "ref", "imageDigest"}
        )
        if (
            not isinstance(descriptor, dict)
            or set(descriptor) != expected_descriptor_fields
        ):
            raise ValueError(f"package OCI image descriptor fields mismatch: {service}")
        build_ref = str(descriptor.get("ref") or "")
        image_digest = str(descriptor.get("imageDigest") or "")
        if service in first_party_services:
            expected_build_ref = packaged_service_build_image_ref(
                env_name,
                service,
                binding_manifest_digest=binding_manifest_digest,
                candidate_digest=baseline_id,
            )
            if build_ref != expected_build_ref:
                raise ValueError(f"package OCI build ref mismatch: {service}")
            first_party_runtime_refs[service] = image_digest
        elif descriptor != provider_images.get(service):
            raise ValueError(f"package OCI Provider image identity mismatch: {service}")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", image_digest) is None:
            raise ValueError(f"package OCI image digest is invalid: {service}")
        normalized_images[service] = dict(descriptor)
    actual_set_digest = "sha256:" + hashlib.sha256(
        json.dumps(
            normalized_images,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    if actual_set_digest != manifest["imageDigest"]:
        raise ValueError("package OCI image set digest mismatch")
    configuration_digest = str(candidate.get("configurationDigest") or "").strip()
    if re.fullmatch(r"sha256:[0-9a-f]{64}", configuration_digest) is None:
        raise ValueError("package OCI candidate configuration digest is invalid")
    if configuration_digest != manifest["configurationDigest"]:
        raise ValueError("package OCI configuration digest mismatch")
    if (
        candidate.get("imageDigest") != manifest["imageDigest"]
        or candidate.get("buildInputDigest") != manifest["buildInputDigest"]
        or candidate.get("configurationDigest") != configuration_digest
    ):
        raise ValueError("package OCI runtime differs from the active candidate")
    startup_image_composition = _stackctl.image_composition_from_candidate_oci(
        manifest,
        expected_environment=env_name,
        expected_target=target_name,
    )
    return {
        "candidateId": str(candidate["baselineId"]),
        "imageVersion": _stackctl.immutable_image_digest(first_party_runtime_refs),
        "startupImageCompositionFile": str(manifest_path),
        "startupImageTransportTag": str(
            startup_image_composition["imageVersion"]
        ),
        "startupImageComposition": startup_image_composition,
        "configurationDigest": configuration_digest,
        "buildInputDigest": manifest["buildInputDigest"],
        "imageDigest": manifest["imageDigest"],
        "images": {
            service: {"ref": image_digest, "digest": image_digest}
            for service, image_digest in sorted(first_party_runtime_refs.items())
        },
    }


def _bind_gamma_packaged_service_image_refs(
    env_name: str,
    environment: dict[str, str],
    *,
    candidate_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind only exact OCI image IDs attested by the immutable package."""
    import quwoquan_ops.cli.stackctl as _stackctl


    target_name = str(environment.get("QWQ_LOCAL_RELEASE_TARGET") or "").strip()
    if not target_name:
        raise ValueError("package-bound runtime target is missing")
    composition = _stackctl._load_package_bound_local_image_composition(
        env_name,
        target_name,
        candidate_snapshot=candidate_snapshot,
    )
    _stackctl._apply_gamma_image_composition(composition, environment)
    startup_manifest = str(
        composition.get("startupImageCompositionFile") or ""
    ).strip()
    startup_transport_tag = str(
        composition.get("startupImageTransportTag") or ""
    ).strip()
    if (
        not startup_manifest
        or re.fullmatch(r"sha256:[0-9a-f]{64}", startup_transport_tag) is None
    ):
        raise ValueError("package OCI startup identity is incomplete")
    environment["QWQ_STARTUP_IMAGE_COMPOSITION_FILE"] = startup_manifest
    environment["QWQ_STARTUP_IMAGE_TRANSPORT_TAG"] = startup_transport_tag
    _stackctl._bind_artifact_identity_mount_material(environment)
    return composition


def _bind_gamma_packaged_configuration_digest(
    env_name: str,
    environment: dict[str, str],
    composition: dict[str, Any] | None = None,
) -> str:
    import quwoquan_ops.cli.stackctl as _stackctl

    target_name = str(environment.get("QWQ_LOCAL_RELEASE_TARGET") or "").strip()
    digest = _stackctl.packaged_configuration_digest(
        env_name,
        target=target_name,
    )
    environment["LOCAL_GAMMA_CONFIG_VERSION"] = digest
    if composition is not None:
        composition["configurationDigest"] = digest
    return digest


def _resolve_gamma_release_image_composition(
    manifest_path: Path,
    environment_name: str,
) -> dict[str, Any]:
    """Resolve one validated candidate manifest without mutating or pulling."""
    import quwoquan_ops.cli.stackctl as _stackctl


    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"formal release manifest is unreadable: {error}") from error
    if not isinstance(manifest, dict):
        raise ValueError("formal release manifest must be an object")
    _stackctl.finalize_mainline_release_artifact.validate_manifest(
        manifest,
        allowed_statuses={"candidate-ready", "deployable", "released"},
    )
    _stackctl.finalize_mainline_release_artifact.validate_manifest_files(
        manifest_path.parent,
        manifest,
    )
    if environment_name not in {"alpha", "beta", "gamma", "prod"}:
        raise ValueError("formal release environment is invalid")
    artifacts = manifest.get("environmentArtifacts")
    artifact = (
        artifacts.get(environment_name) if isinstance(artifacts, dict) else None
    )
    images = artifact.get("images") if isinstance(artifact, dict) else None
    if not isinstance(images, dict):
        raise ValueError(
            f"formal release manifest has no {environment_name} artifact images"
        )
    bound: dict[str, dict[str, str]] = {}
    for service, _ in _stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS:
        descriptor = images.get(service)
        if not isinstance(descriptor, dict):
            raise ValueError(f"formal release image is missing: {service}")
        digest = str(descriptor.get("digest") or "")
        ref = str(descriptor.get("ref") or "")
        repository = str(descriptor.get("repository") or "")
        if (
            re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
            or ref != f"{repository}@{digest}"
        ):
            raise ValueError(f"formal release image is not exact: {service}")
        bound[service] = {"ref": ref, "digest": digest}
    composition_version = _stackctl.immutable_image_digest(
        {service: descriptor["ref"] for service, descriptor in bound.items()}
    )
    return {
        "candidateId": str(manifest["candidateId"]),
        "artifactDigest": str(manifest["artifactDigest"]),
        "environmentArtifactDigest": str(artifact["environmentArtifactDigest"]),
        "contractGraphDigest": str(manifest["contractGraphDigest"]),
        "imageVersion": composition_version,
        "images": bound,
    }


def _apply_gamma_image_composition(
    composition: dict[str, Any],
    environment: dict[str, str],
) -> None:
    """Project one already-validated composition into both Compose aliases."""
    import quwoquan_ops.cli.stackctl as _stackctl


    configuration_digest = str(composition.get("configurationDigest") or "").strip()
    if re.fullmatch(r"sha256:[0-9a-f]{64}", configuration_digest) is None:
        raise ValueError("immutable runtime composition has no configuration digest")
    environment["LOCAL_GAMMA_CONFIG_VERSION"] = configuration_digest
    images = composition.get("images")
    if not isinstance(images, dict) or not images:
        raise ValueError("immutable image composition has no images")
    refs: dict[str, str] = {}
    for service, local_key in _stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS:
        descriptor = images.get(service)
        if not isinstance(descriptor, dict):
            raise ValueError(f"immutable image composition is missing: {service}")
        ref = str(descriptor.get("ref") or "")
        refs[service] = ref
        environment[local_key] = ref
        environment[_stackctl.compose_image_environment_key(service)] = ref
    actual_version = _stackctl.immutable_image_digest(refs)
    expected_version = str(composition.get("imageVersion") or "")
    if actual_version != expected_version:
        raise ValueError("immutable image composition version mismatch")
    environment["LOCAL_GAMMA_IMAGE_VERSION"] = actual_version
    environment["QWQ_COMPOSE_IMAGE_VERSION"] = actual_version
    environment["QWQ_COMPOSE_IMAGE_TAG"] = actual_version.removeprefix("sha256:")
    candidate_id = str(composition.get("candidateId") or "")
    artifact_digest = str(composition.get("artifactDigest") or "")
    if candidate_id:
        environment["QWQ_RELEASE_CANDIDATE_DIGEST"] = candidate_id
    if artifact_digest:
        environment["QWQ_RELEASE_ARTIFACT_DIGEST"] = artifact_digest


def _bind_gamma_release_image_refs(
    manifest_path: Path,
    environment: dict[str, str],
    *,
    release_input_classification: str,
    contract_graph_digest: str,
) -> dict[str, Any]:
    """Pull and bind exact candidate OCI refs for a formal local release."""
    import quwoquan_ops.cli.stackctl as _stackctl


    environment_name = str(environment.get("QWQ_LOCAL_RELEASE_ENV") or "")
    composition = _stackctl._resolve_gamma_release_image_composition(
        manifest_path,
        environment_name,
    )
    if release_input_classification != "commercial_inputs":
        raise ValueError("formal release requires commercial release inputs")
    if composition.get("contractGraphDigest") != contract_graph_digest:
        raise ValueError("formal release ContractGraph differs from the package")
    planned: list[tuple[str, str, str, str]] = []
    for service, environment_key in _stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS:
        descriptor = composition["images"][service]
        digest = descriptor["digest"]
        ref = descriptor["ref"]
        planned.append((service, environment_key, ref, digest))

    def pull_exact_image(
        item: tuple[str, str, str, str],
    ) -> tuple[tuple[str, str, str, str], subprocess.CompletedProcess[str]]:
        return item, _stackctl.run(["docker", "pull", "--platform", "linux/amd64", item[2]])

    failures: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(8, len(planned))
    ) as executor:
        futures = [executor.submit(pull_exact_image, item) for item in planned]
        for future in concurrent.futures.as_completed(futures):
            item, pull = future.result()
            if pull.returncode != 0:
                failures.append(
                    f"{item[0]}: "
                    + (pull.stderr.strip() or pull.stdout.strip() or "pull failed")
                )
    if failures:
        raise ValueError(
            "formal release exact OCI pull failed: " + "; ".join(sorted(failures))
        )

    _stackctl._bind_gamma_packaged_configuration_digest(
        str(environment.get("QWQ_LOCAL_RELEASE_ENV") or ""),
        environment,
        composition,
    )
    _stackctl._apply_gamma_image_composition(composition, environment)
    _stackctl._bind_artifact_identity_mount_material(environment)
    return composition


def _bind_gamma_release_teardown_image_refs(
    manifest_path: Path,
    environment: dict[str, str],
) -> dict[str, Any]:
    """Bind the exact candidate identity for teardown without pulling images."""
    import quwoquan_ops.cli.stackctl as _stackctl


    environment_name = str(environment.get("QWQ_LOCAL_RELEASE_ENV") or "")
    composition = _stackctl._resolve_gamma_release_image_composition(
        manifest_path,
        environment_name,
    )
    _stackctl._bind_gamma_packaged_configuration_digest(
        environment_name,
        environment,
        composition,
    )
    _stackctl._apply_gamma_image_composition(composition, environment)
    return composition


def _load_gamma_runtime_image_composition(
    target_name: str,
    *,
    include_stopped: bool = False,
) -> tuple[dict[str, Any], str] | None:
    """Read the canonical current runtime binding; absence permits package derivation.

    A stopped runtime has no current binding, so by default it reads as absent.
    Purging rebuildable state is the one caller that still needs the identity of
    the run that just went away: its Compose volumes outlive the containers, and
    the last attempt receipt is the only record of which project owns them.
    ``include_stopped`` makes that need explicit at the call site instead of
    letting a stopped runtime quietly pass as a running one.
    """
    import quwoquan_ops.cli.stackctl as _stackctl


    try:
        receipt = _stackctl.load_startup_attempt(target_name)
    except ValueError as exc:
        raise ValueError(f"runtime image composition receipt is unreadable: {exc}") from exc
    if receipt is None:
        return None
    bindable_states = {"prepared", "partial", "running"}
    if include_stopped:
        bindable_states.add("stopped")
    elif receipt.get("status") == "stopped":
        return None
    if receipt.get("status") not in bindable_states:
        raise ValueError("runtime startup attempt has no resources to tear down")
    expected_environment = target_name.removesuffix("-local")
    if receipt.get("target") != target_name:
        raise ValueError("runtime image composition receipt target mismatch")
    receipt_environment = str(receipt.get("env") or "").strip()
    if receipt_environment != expected_environment:
        raise ValueError("runtime image composition receipt environment mismatch")
    compose_project = str(receipt.get("composeProject") or "").strip()
    if not compose_project:
        raise ValueError("runtime image composition receipt has no Compose project")
    expected_project_prefix = f"quwoquan_{expected_environment}_release"
    if (
        re.fullmatch(
            re.escape(expected_project_prefix) + r"(?:_[a-zA-Z0-9_-]+)?",
            compose_project,
        )
        is None
    ):
        raise ValueError("runtime image composition receipt Compose project mismatch")
    composition = receipt.get("imageComposition")
    if not isinstance(composition, dict):
        raise ValueError("runtime image composition receipt has no image composition")
    images = composition.get("images")
    if not isinstance(images, dict):
        raise ValueError("runtime image composition receipt has invalid images")
    refs: dict[str, str] = {}
    for service, _ in _stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS:
        descriptor = images.get(service)
        if not isinstance(descriptor, dict):
            raise ValueError(f"runtime image composition is missing: {service}")
        refs[service] = str(descriptor.get("ref") or "")
    first_party_version = _stackctl.immutable_image_digest(refs)
    configuration_digest = str(receipt.get("configurationDigest") or "").strip()
    if re.fullmatch(r"sha256:[0-9a-f]{64}", configuration_digest) is None:
        raise ValueError("runtime image composition receipt has no configuration digest")
    teardown_composition = {
        "imageVersion": first_party_version,
        "images": {
            service: {"ref": image_digest, "digest": image_digest}
            for service, image_digest in sorted(refs.items())
        },
        "configurationDigest": configuration_digest,
    }
    return teardown_composition, compose_project
