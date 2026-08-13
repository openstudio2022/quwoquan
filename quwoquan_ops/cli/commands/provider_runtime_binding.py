"""stackctl 外部 Provider runtime 与 observability log sink 候选绑定域。

从 stackctl.py 逐字迁出（改写规则与 down_domain 相同）:
`_external_provider_governance` / `_provider_config`（延迟 import 桥）、
`_candidate_provider_runtime` / `_active_provider_runtime`、
`_candidate_observability_log_sink` / `_active_observability_log_sink`、
`_fixed_candidate_identity` / `_candidate_bindings_from_snapshot`、
`_observability_log_sink_launch_environment` / `_provider_runtime_launch_environment`。

测试经 ``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号，
因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问（含本模块符号互调），
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import re

from pathlib import Path
from typing import Any
from typing import Mapping


def _external_provider_governance():
    from quwoquan_ops.cli.lib import external_provider_governance

    return external_provider_governance


def _provider_config():
    from quwoquan_ops.cli.lib import provider_config

    return provider_config


def _candidate_provider_runtime(
    environment_name: str,
    target_name: str,
    baseline_id: str,
    *,
    candidate_manifest: Mapping[str, Any] | None = None,
    candidate_root: Path | None = None,
) -> dict[str, Any]:
    """Load one Provider runtime from the exact immutable candidate identity."""
    import quwoquan_ops.cli.stackctl as _stackctl


    normalized_baseline = str(baseline_id or "").strip()
    if re.fullmatch(r"sha256:[0-9a-f]{64}", normalized_baseline) is None:
        raise ValueError("Provider candidate baseline identity is invalid")
    expected_candidate_root = _stackctl.deployment_candidate_dir(
        target_name,
        normalized_baseline,
    ).resolve()
    resolved_candidate_root = (
        Path(candidate_root).expanduser().resolve()
        if candidate_root is not None
        else expected_candidate_root
    )
    if resolved_candidate_root != expected_candidate_root:
        raise ValueError("Provider candidate root differs from its baseline identity")
    candidate = (
        dict(candidate_manifest)
        if candidate_manifest is not None
        else _stackctl.load_candidate_manifest(
            environment_name,
            target_name,
            normalized_baseline,
            require_full=True,
        )
    )
    if (
        candidate.get("environment") != environment_name
        or candidate.get("target") != target_name
        or candidate.get("baselineId") != normalized_baseline
    ):
        raise ValueError("Provider candidate manifest identity mismatch")
    provider_runtime = candidate.get("providerRuntime")
    if not isinstance(provider_runtime, dict):
        raise ValueError("active candidate Provider runtime is missing")
    composition = _stackctl.validate_provider_runtime_composition(
        provider_runtime.get("composition"),
        expected_environment=environment_name,
        expected_target=target_name,
    )
    artifacts = provider_runtime.get("workloads")
    if not isinstance(artifacts, list):
        raise TypeError("active candidate Provider workload artifacts are invalid")
    by_role: dict[str, Path] = {}
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            raise TypeError("active candidate Provider workload artifact is invalid")
        role = str(artifact.get("role") or "").strip()
        compose_ref = str(artifact.get("composeRef") or "").strip()
        compose_path = (resolved_candidate_root / compose_ref).resolve()
        if (
            not role
            or role in by_role
            or not compose_path.is_relative_to(resolved_candidate_root)
            or not compose_path.is_file()
            or compose_path.is_symlink()
        ):
            raise ValueError("active candidate Provider workload artifact is unsafe")
        by_role[role] = compose_path
    expected_roles = {
        str(workload.get("role") or "").strip()
        for workload in composition["workloads"]
    }
    if set(by_role) != expected_roles:
        raise ValueError("active candidate Provider workload closure mismatch")
    return {
        "baselineId": normalized_baseline,
        "candidateRoot": resolved_candidate_root,
        "providerRuntime": provider_runtime,
        "composition": composition,
        "composeByRole": by_role,
    }


def _active_provider_runtime(
    environment_name: str,
    target_name: str,
) -> dict[str, Any]:
    """Load one validated Provider runtime exclusively from the active candidate."""
    import quwoquan_ops.cli.stackctl as _stackctl


    active = _stackctl.active_deployment_candidate(target_name)
    if not isinstance(active, dict):
        raise ValueError(f"{target_name} has no active immutable candidate")
    baseline_id = str(active.get("baselineId") or "").strip()
    expected_candidate_root = _stackctl.deployment_candidate_dir(
        target_name,
        baseline_id,
    ).resolve()
    if str(active.get("candidateDir") or "") != str(expected_candidate_root):
        raise ValueError("active candidate path does not match its baseline identity")
    return _stackctl._candidate_provider_runtime(
        environment_name,
        target_name,
        baseline_id,
    )


def _candidate_observability_log_sink(
    environment_name: str,
    target_name: str,
    baseline_id: str,
    *,
    candidate_manifest: Mapping[str, Any] | None = None,
    candidate_root: Path | None = None,
) -> dict[str, Any]:
    """Load the ES contract sealed into one exact immutable candidate."""
    import quwoquan_ops.cli.stackctl as _stackctl


    normalized_baseline = str(baseline_id or "").strip()
    if re.fullmatch(r"sha256:[0-9a-f]{64}", normalized_baseline) is None:
        raise ValueError("observability candidate baseline identity is invalid")
    expected_candidate_root = _stackctl.deployment_candidate_dir(
        target_name,
        normalized_baseline,
    ).resolve()
    resolved_candidate_root = (
        Path(candidate_root).expanduser().resolve()
        if candidate_root is not None
        else expected_candidate_root
    )
    if resolved_candidate_root != expected_candidate_root:
        raise ValueError(
            "observability candidate root differs from its baseline identity"
        )
    candidate = (
        dict(candidate_manifest)
        if candidate_manifest is not None
        else _stackctl.load_candidate_manifest(
            environment_name,
            target_name,
            normalized_baseline,
            require_full=True,
        )
    )
    if (
        candidate.get("environment") != environment_name
        or candidate.get("target") != target_name
        or candidate.get("baselineId") != normalized_baseline
    ):
        raise ValueError("observability candidate manifest identity mismatch")
    composition = _stackctl.validate_observability_log_sink_package(
        candidate.get("observabilityLogSink"),
        expected_environment=environment_name,
        expected_target=target_name,
        candidate_root=resolved_candidate_root,
    )
    return {
        "baselineId": normalized_baseline,
        "candidateRoot": resolved_candidate_root,
        "composition": composition,
    }


def _active_observability_log_sink(
    environment_name: str,
    target_name: str,
) -> dict[str, Any]:
    """Load the one ES contract already sealed into the active candidate."""
    import quwoquan_ops.cli.stackctl as _stackctl


    active = _stackctl.active_deployment_candidate(target_name)
    if not isinstance(active, dict):
        raise ValueError(f"{target_name} has no active immutable candidate")
    baseline_id = str(active.get("baselineId") or "").strip()
    expected_candidate_root = _stackctl.deployment_candidate_dir(
        target_name,
        baseline_id,
    ).resolve()
    if str(active.get("candidateDir") or "") != str(expected_candidate_root):
        raise ValueError("active candidate path does not match its baseline identity")
    return _stackctl._candidate_observability_log_sink(
        environment_name,
        target_name,
        baseline_id,
    )


def _fixed_candidate_identity(
    candidate_snapshot: Mapping[str, Any],
    *,
    environment_name: str,
    target_name: str,
) -> tuple[str, Path, dict[str, Any]]:
    """Validate the in-memory candidate fixed at operation entry."""
    import quwoquan_ops.cli.stackctl as _stackctl


    required = {
        "schema",
        "candidateType",
        "target",
        "baselineId",
        "candidateDir",
        "manifest",
    }
    if not isinstance(candidate_snapshot, Mapping) or set(candidate_snapshot) != required:
        raise ValueError("fixed deployment candidate snapshot fields mismatch")
    baseline_id = str(candidate_snapshot.get("baselineId") or "").strip()
    if re.fullmatch(r"sha256:[0-9a-f]{64}", baseline_id) is None:
        raise ValueError("fixed deployment candidate baseline identity is invalid")
    candidate_root = Path(str(candidate_snapshot.get("candidateDir") or "")).resolve()
    expected_root = _stackctl.deployment_candidate_dir(target_name, baseline_id).resolve()
    manifest = candidate_snapshot.get("manifest")
    if (
        candidate_snapshot.get("target") != target_name
        or candidate_root != expected_root
        or not isinstance(manifest, dict)
        or manifest.get("environment") != environment_name
        or manifest.get("target") != target_name
        or manifest.get("baselineId") != baseline_id
    ):
        raise ValueError("fixed deployment candidate identity mismatch")
    return baseline_id, candidate_root, manifest


def _candidate_bindings_from_snapshot(
    candidate_snapshot: Mapping[str, Any],
    *,
    environment_name: str,
    target_name: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    import quwoquan_ops.cli.stackctl as _stackctl

    baseline_id, candidate_root, manifest = _stackctl._fixed_candidate_identity(
        candidate_snapshot,
        environment_name=environment_name,
        target_name=target_name,
    )
    provider = _stackctl._candidate_provider_runtime(
        environment_name,
        target_name,
        baseline_id,
        candidate_manifest=manifest,
        candidate_root=candidate_root,
    )
    observability = _stackctl._candidate_observability_log_sink(
        environment_name,
        target_name,
        baseline_id,
        candidate_manifest=manifest,
        candidate_root=candidate_root,
    )
    return provider, observability


def _observability_log_sink_launch_environment(
    composition: Mapping[str, Any],
    *,
    environment_name: str,
    target_name: str,
    candidate_root: Path,
    workload: str,
) -> dict[str, str]:
    """Project candidate-owned ES inputs without consulting the workspace."""
    import quwoquan_ops.cli.stackctl as _stackctl


    validated = _stackctl.validate_observability_log_sink_package(
        dict(composition),
        expected_environment=environment_name,
        expected_target=target_name,
        candidate_root=candidate_root,
    )
    projected = {
        "QWQ_OBSERVABILITY_LOG_SINK_COMPOSE_FILE": "",
        "QWQ_OBSERVABILITY_LOG_SINK_DIGEST": "",
    }
    if workload == "content-release":
        return projected
    if workload not in {"full", "content-commercial"}:
        raise ValueError(f"unsupported observability workload: {workload}")
    if validated["deploymentMode"] != "package-bound-local":
        raise ValueError("local runtime requires package-bound Elasticsearch")
    root = candidate_root.resolve()
    compose_path = (root / str(validated["composeRef"])).resolve()
    if (
        not compose_path.is_relative_to(root)
        or not compose_path.is_file()
        or compose_path.is_symlink()
    ):
        raise ValueError("candidate-owned Elasticsearch Compose is unsafe")
    projected.update(
        {
            "QWQ_OBSERVABILITY_LOG_SINK_COMPOSE_FILE": str(compose_path),
            "QWQ_OBSERVABILITY_LOG_SINK_DIGEST": str(
                validated["composeDigest"]
            ),
            str(validated["endpointEnvironmentKey"]): str(
                validated["runtimeEndpoint"]
            ),
        }
    )
    return projected


def _provider_runtime_launch_environment(
    provider_runtime: Mapping[str, Any],
    *,
    candidate_root: Path,
    workload: str,
    require_images: bool = True,
) -> dict[str, str]:
    """Project package-owned Provider Compose inputs without a runtime selector."""
    import quwoquan_ops.cli.stackctl as _stackctl


    composition = provider_runtime.get("composition")
    if not isinstance(composition, Mapping):
        raise TypeError("package-bound Provider runtime composition is invalid")
    environment_name = str(composition.get("environment") or "").strip()
    target_name = str(composition.get("target") or "").strip()
    validated = _stackctl.validate_provider_runtime_composition(
        dict(composition),
        expected_environment=environment_name,
        expected_target=target_name,
    )
    runtime_digest = str(validated["runtimeCompositionDigest"])
    projected = {
        "QWQ_PROVIDER_RUNTIME_DIGEST": runtime_digest,
        "QWQ_PROVIDER_RUNTIME_COMPOSE_FILES": "",
        "QWQ_PROVIDER_RUNTIME_COMPOSE_DIGESTS": "",
        "QWQ_PROVIDER_RUNTIME_COMPOSE_PROFILES": "",
    }
    if workload != "full":
        return projected
    if environment_name == "prod":
        if validated["workloads"]:
            raise ValueError("Prod Provider runtime cannot start local workloads")
        return projected
    if environment_name not in {"alpha", "beta", "gamma"}:
        raise ValueError("local Provider runtime environment is unsupported")

    artifacts = provider_runtime.get("workloads")
    if not isinstance(artifacts, list):
        raise TypeError("package-bound Provider workload artifacts are invalid")
    artifact_by_role: dict[str, tuple[Path, str]] = {}
    root = candidate_root.resolve()
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            raise TypeError("package-bound Provider workload artifact is invalid")
        role = str(artifact.get("role") or "").strip()
        compose_path = (root / str(artifact.get("composeRef") or "")).resolve()
        compose_digest = str(artifact.get("composeDigest") or "").strip()
        if (
            not role
            or role in artifact_by_role
            or not compose_path.is_relative_to(root)
            or not compose_path.is_file()
            or compose_path.is_symlink()
            or re.fullmatch(r"sha256:[0-9a-f]{64}", compose_digest) is None
            or _stackctl._sha256_file(compose_path) != compose_digest
        ):
            raise ValueError("package-bound Provider workload artifact is unsafe")
        artifact_by_role[role] = (compose_path, compose_digest)

    roles = [str(item["role"]) for item in validated["workloads"]]
    if set(roles) != set(artifact_by_role) or not roles:
        raise ValueError("nonprod full runtime Provider workload closure is incomplete")
    images = provider_runtime.get("images")
    if not isinstance(images, Mapping):
        raise TypeError("package-bound Provider image closure is invalid")
    if require_images and set(images) != set(roles):
        raise ValueError("package-bound Provider image closure is incomplete")
    if not require_images and images:
        raise ValueError("unsealed Provider runtime cannot project images")
    if require_images:
        for role in roles:
            descriptor = images.get(role)
            if not isinstance(descriptor, Mapping) or set(descriptor) != {
                "buildInputDigest",
                "ref",
                "imageDigest",
            }:
                raise ValueError(
                    f"package-bound Provider image descriptor is invalid: {role}"
                )
            image_digest = str(descriptor.get("imageDigest") or "").strip()
            build_input_digest = str(
                descriptor.get("buildInputDigest") or ""
            ).strip()
            if (
                re.fullmatch(r"sha256:[0-9a-f]{64}", image_digest) is None
                or re.fullmatch(
                    r"sha256:[0-9a-f]{64}", build_input_digest
                )
                is None
            ):
                raise ValueError(
                    f"package-bound Provider image digest is invalid: {role}"
                )
            projected[_stackctl.provider_runtime_image_environment_key(role)] = image_digest
    profiles = sorted(
        {
            str(profile)
            for item in validated["workloads"]
            for profile in item["composeProfiles"]
            if str(profile).strip()
        }
    )
    if not profiles:
        raise ValueError("nonprod full runtime Provider Compose profiles are missing")
    projected.update(
        {
            "QWQ_PROVIDER_RUNTIME_COMPOSE_FILES": "\n".join(
                str(artifact_by_role[role][0]) for role in roles
            ),
            "QWQ_PROVIDER_RUNTIME_COMPOSE_DIGESTS": "\n".join(
                artifact_by_role[role][1] for role in roles
            ),
            "QWQ_PROVIDER_RUNTIME_COMPOSE_PROFILES": ",".join(profiles),
        }
    )
    return projected
