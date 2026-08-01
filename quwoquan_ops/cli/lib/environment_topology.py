from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .common import ROOT, load_json_yaml
from .port_manifest import load_port_manifest, profile_ports


DEFAULT_PATH = ROOT / "quwoquan_ops" / "environments"
ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
TARGETS = (
    "alpha-local",
    "beta-local",
    "gamma-local",
    "prod-sim",
    "prod-hosted",
)
ROLE_CATALOG_PATH = DEFAULT_PATH / "domain_governance.yaml"
_ROLE_CATALOG = {
    str(entry["role"]): entry
    for entry in load_json_yaml(ROLE_CATALOG_PATH)["endpointRegistry"]
}
URL_FIELDS = tuple(_ROLE_CATALOG)
URL_GOVERNANCE_FIELDS = frozenset(
    {"name", "role", "classification", "owner", "exposure", "consumers"}
)
URL_SHAPE_FIELDS = frozenset(
    {"scheme", "host", "portRole", "pathBase", "tlsProfile"}
)
REQUIRED_SUBNETS = ("edge", "media", "service", "data")
REQUIRED_APP_POLICY = (
    "runtimeEnv",
    "allowSeeds",
    "allowLocalHosts",
    "allowProdHosts",
    "distribution",
)
REQUIRED_SERVICE_POLICY = (
    "allowFixtureRefs",
    "allowReleaseSnapshot",
    "secretScope",
    "distribution",
)
ENVIRONMENT_CANONICAL_TARGET = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    "prod": "prod-hosted",
}
LOCAL_PUBLIC_PORT_ROLES = {
    "api": "api-edge",
    "realtime": "api-edge",
    "rtc": "api-edge",
    "productOps": "product-ops-edge",
    "publicWeb": "api-edge",
    "legal": "api-edge",
    "appDownload": "media-edge",
    "mediaAvatar": "media-edge",
    "mediaImage": "media-edge",
    "mediaVideo": "media-edge",
    "mediaUpload": "media-edge",
}
LOCAL_ORIGIN_PORT_ROLES = {
    "mediaOrigin": "media-origin",
    "contentService": "content-service",
}
DATA_RELEASE_MODES = {"projection-only", "local-import", "hosted-import"}
DATA_RELEASE_ENV_KEY_RE = re.compile(r"^QWQ_[A-Z0-9_]+$")
WORKLOAD_PLANES = {"edge", "media", "service", "data"}
LOCAL_TLS_PROFILE_BY_TARGET = {
    "alpha-local": "local-managed",
    "beta-local": "local-managed",
    "gamma-local": "local-managed",
    "prod-sim": "acme-dns01-sim",
}
PROD_TLS_PROFILE = "public-ca-prod"


def load_environment_topology(path: Path | None = None) -> dict[str, Any]:
    if path is not None and path.is_file():
        loaded = load_json_yaml(path)
        if not isinstance(loaded, dict):
            raise RuntimeError("environment topology input must be a mapping")
        return _materialize_public_bases(loaded)

    environment_root = path or DEFAULT_PATH
    environments: dict[str, dict[str, Any]] = {}
    targets: dict[str, dict[str, Any]] = {}
    for env_name in ENVIRONMENTS:
        runtime_path = environment_root / env_name / "runtime.yaml"
        runtime = load_json_yaml(runtime_path)
        if not isinstance(runtime, dict):
            raise RuntimeError(f"{runtime_path}: environment runtime must be a mapping")
        if runtime.get("schema") != "environment-runtime" or runtime.get("environment") != env_name:
            raise RuntimeError(f"{runtime_path}: schema/environment identity mismatch")
        environment = {
            key: value
            for key, value in runtime.items()
            if key not in {"schema", "environment", "targets"}
        }
        environment["workloads"] = _scan_environment_workloads(env_name)
        environments[env_name] = environment
        runtime_targets = runtime.get("targets") or {}
        if not isinstance(runtime_targets, dict):
            raise RuntimeError(f"{runtime_path}: targets must be a mapping")
        for target_name, target in runtime_targets.items():
            if target_name in targets:
                raise RuntimeError(f"duplicate target definition: {target_name}")
            targets[str(target_name)] = target
    return _materialize_public_bases({
        "schema": "environment-topology",
        "environments": environments,
        "targets": targets,
    })


def _materialize_public_bases(manifest: dict[str, Any]) -> dict[str, Any]:
    """从结构化 urlRoles 生成消费者兼容的只读 publicBases 投影。"""

    environments = manifest.get("environments")
    targets = manifest.get("targets")
    if not isinstance(environments, dict) or not isinstance(targets, dict):
        return manifest

    resolution_errors: list[str] = []
    for target_name, raw_target in list(targets.items()):
        if not isinstance(raw_target, dict):
            continue
        target = dict(raw_target)
        targets[target_name] = target
        env_name = str(target.get("env") or "")
        env = environments.get(env_name)
        if not isinstance(env, dict):
            continue
        try:
            resolved_roles, public_bases = _resolve_target_url_roles(
                target_name,
                env,
                target,
            )
        except (KeyError, TypeError, ValueError) as exc:
            resolution_errors.append(f"{target_name}: {exc}")
            continue
        target["resolvedUrlRoles"] = resolved_roles
        target["publicBases"] = public_bases

    for env_name, target_name in ENVIRONMENT_CANONICAL_TARGET.items():
        env = environments.get(env_name)
        target = targets.get(target_name)
        if not isinstance(env, dict) or not isinstance(target, dict):
            continue
        public_bases = target.get("publicBases")
        if isinstance(public_bases, dict):
            env["publicBases"] = dict(public_bases)

    if resolution_errors:
        manifest["_urlResolutionErrors"] = resolution_errors
    return manifest


def _resolve_target_url_roles(
    target_name: str,
    environment: dict[str, Any],
    target: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    base_roles = environment.get("urlRoles")
    if not isinstance(base_roles, dict):
        raise TypeError("environment urlRoles must be a mapping")
    overrides = target.get("urlOverrides") or {}
    if not isinstance(overrides, dict):
        raise TypeError("urlOverrides must be a mapping")
    unknown_overrides = sorted(set(overrides) - set(URL_FIELDS))
    if unknown_overrides:
        raise ValueError(f"urlOverrides contains unknown roles: {unknown_overrides}")

    backend = str(target.get("backend") or "")
    profile = target.get("portProfile")
    role_ports: dict[str, int] = {}
    if backend == "local":
        if not profile:
            raise ValueError("local target requires portProfile")
        role_ports = profile_ports(load_port_manifest(), str(profile))

    resolved_roles: dict[str, dict[str, Any]] = {}
    public_bases: dict[str, str] = {}
    for field in URL_FIELDS:
        base = base_roles.get(field)
        if not isinstance(base, dict):
            raise TypeError(f"urlRoles.{field} must be a mapping")
        override = overrides.get(field) or {}
        if not isinstance(override, dict):
            raise TypeError(f"urlOverrides.{field} must be a mapping")
        governance = _ROLE_CATALOG[field]
        overlap = sorted(set(governance).intersection(base))
        if overlap:
            raise ValueError(
                f"urlRoles.{field} duplicates domain governance fields: {overlap}"
            )
        role_shape = {**base, **override}
        role = {**governance, **role_shape}
        port_role = role.get("portRole")
        port: int | None = None
        if backend == "local":
            if not isinstance(port_role, str) or port_role not in role_ports:
                raise ValueError(
                    f"urlRoles.{field}.portRole must reference {profile}"
                )
            port = role_ports[port_role]
        elif port_role is not None:
            raise ValueError(
                f"urlRoles.{field}.portRole must be null for non-local targets"
            )
        resolved_roles[field] = role
        public_bases[field] = _build_role_base_url(role, port=port)
    return resolved_roles, public_bases


def _build_role_base_url(role: dict[str, Any], *, port: int | None) -> str:
    scheme = str(role.get("scheme") or "").strip()
    host = str(role.get("host") or "").strip()
    path_base = str(role.get("pathBase") or "").strip()
    authority = f"{host}:{port}" if port is not None else host
    suffix = "" if path_base == "/" else path_base
    return f"{scheme}://{authority}{suffix}"


def _scan_environment_workloads(env_name: str) -> list[dict[str, str]]:
    workloads: list[dict[str, str]] = []
    services_root = ROOT / "quwoquan_service" / "services"
    for service_root in sorted(path for path in services_root.iterdir() if path.is_dir()):
        deployment = service_root / "environments" / env_name / "deploy" / "kustomization.yaml"
        if deployment.is_file():
            workloads.append(
                {
                    "id": service_root.name,
                    "plane": _workload_plane(service_root.name),
                    "deploymentRef": deployment.parent.relative_to(ROOT).as_posix(),
                }
            )
    external_root = ROOT / "quwoquan_ops" / "external"
    if external_root.is_dir():
        for workload_root in sorted(path for path in external_root.iterdir() if path.is_dir()):
            deployment = workload_root / "environments" / env_name / "kustomization.yaml"
            if deployment.is_file():
                workloads.append(
                    {
                        "id": workload_root.name,
                        "plane": _workload_plane(workload_root.name),
                        "deploymentRef": deployment.parent.relative_to(ROOT).as_posix(),
                    }
                )
    platform_deployment = (
        ROOT
        / "quwoquan_service"
        / "control-plane"
        / "platform-ops"
        / "environments"
        / env_name
        / "deploy"
        / "kustomization.yaml"
    )
    if platform_deployment.is_file():
        workloads.append(
            {
                "id": "platform-ops-service",
                "plane": "service",
                "deploymentRef": platform_deployment.parent.relative_to(ROOT).as_posix(),
            }
        )
    return workloads


def _workload_plane(workload_id: str) -> str:
    if workload_id == "realtime-gateway":
        return "edge"
    if workload_id in {"rtc-service", "coturn", "livekit"}:
        return "media"
    return "service"


def get_environment(manifest: dict[str, Any], env_name: str) -> dict[str, Any]:
    env = (manifest.get("environments") or {}).get(env_name)
    if not isinstance(env, dict):
        raise KeyError(f"unknown environment: {env_name}")
    return env


def get_target(manifest: dict[str, Any], target_name: str) -> dict[str, Any]:
    target = (manifest.get("targets") or {}).get(target_name)
    if not isinstance(target, dict):
        raise KeyError(f"unknown target profile: {target_name}")
    return target


def validate_environment_topology(
    manifest: dict[str, Any],
    *,
    port_manifest: dict[str, Any] | None = None,
) -> list[str]:
    issues: list[str] = [
        str(issue) for issue in manifest.get("_urlResolutionErrors", [])
    ]
    if manifest.get("schema") != "environment-topology":
        issues.append("schema must be environment-topology")

    environments = manifest.get("environments")
    if not isinstance(environments, dict):
        issues.append("environments must be a mapping")
        return issues

    missing_envs = [env for env in ENVIRONMENTS if env not in environments]
    if missing_envs:
        issues.append(f"missing environments: {', '.join(missing_envs)}")

    for env_name in ENVIRONMENTS:
        env = environments.get(env_name)
        if not isinstance(env, dict):
            continue
        workloads = env.get("workloads")
        declared_refs: set[str] = set()
        declared_ids: set[str] = set()
        if not isinstance(workloads, list):
            issues.append(f"{env_name}: workloads must be a list")
        else:
            for index, workload in enumerate(workloads):
                location = f"{env_name}: workloads[{index}]"
                if not isinstance(workload, dict):
                    issues.append(f"{location} must be a mapping")
                    continue
                if set(workload) != {"id", "plane", "deploymentRef"}:
                    issues.append(
                        f"{location} may contain only id/plane/deploymentRef"
                    )
                workload_id = str(workload.get("id") or "").strip()
                plane = str(workload.get("plane") or "").strip()
                deployment_ref = str(workload.get("deploymentRef") or "").strip()
                if not workload_id or workload_id in declared_ids:
                    issues.append(f"{location}.id must be non-empty and unique")
                declared_ids.add(workload_id)
                if plane not in WORKLOAD_PLANES:
                    issues.append(
                        f"{location}.plane must be one of {sorted(WORKLOAD_PLANES)}"
                    )
                if not deployment_ref or deployment_ref in declared_refs:
                    issues.append(
                        f"{location}.deploymentRef must be non-empty and unique"
                    )
                    continue
                declared_refs.add(deployment_ref)
                ref_path = ROOT / deployment_ref
                if not (ref_path / "kustomization.yaml").is_file():
                    issues.append(
                        f"{location}.deploymentRef has no kustomization.yaml: {deployment_ref}"
                    )
            actual_refs = {
                workload["deploymentRef"]
                for workload in _scan_environment_workloads(env_name)
            }
            missing = sorted(actual_refs - declared_refs)
            stale = sorted(declared_refs - actual_refs)
            if missing:
                issues.append(
                    f"{env_name}: deployment overlays missing from topology: {missing}"
                )
            if stale:
                issues.append(
                    f"{env_name}: topology deploymentRef has no environment overlay: {stale}"
                )
        url_roles = env.get("urlRoles")
        if not isinstance(url_roles, dict):
            issues.append(f"{env_name}: urlRoles must be a mapping")
        else:
            for field in URL_FIELDS:
                role = url_roles.get(field)
                if not isinstance(role, dict):
                    issues.append(f"{env_name}: urlRoles.{field} is required")
                else:
                    issues.extend(
                        _validate_url_role_definition(
                            f"{env_name}: urlRoles.{field}",
                            field,
                            role,
                        )
                    )
        public_bases = env.get("publicBases")
        if not isinstance(public_bases, dict):
            issues.append(f"{env_name}: derived publicBases must be a mapping")
        if "hostAllowlist" in env:
            issues.append(f"{env_name}: hostAllowlist must be derived, not declared")
        if "forbiddenHostTokens" in env:
            issues.append(
                f"{env_name}: forbiddenHostTokens is retired; use host grammar validation"
            )

        subnets = env.get("subnets")
        if not isinstance(subnets, dict):
            issues.append(f"{env_name}: subnets must be a mapping")
        else:
            for field in REQUIRED_SUBNETS:
                value = str(subnets.get(field, "")).strip()
                if not value:
                    issues.append(f"{env_name}: subnets.{field} is required")
                elif not _looks_like_cidr(value):
                    issues.append(f"{env_name}: subnets.{field} must be CIDR")

        aliases = env.get("serviceAliases")
        if not isinstance(aliases, dict):
            issues.append(f"{env_name}: serviceAliases must be a mapping")

        artifact_policy = env.get("artifactPolicy")
        if not isinstance(artifact_policy, dict):
            issues.append(f"{env_name}: artifactPolicy must be a mapping")
        else:
            app_policy = artifact_policy.get("app")
            if not isinstance(app_policy, dict):
                issues.append(f"{env_name}: artifactPolicy.app must be a mapping")
            else:
                for field in REQUIRED_APP_POLICY:
                    if field not in app_policy:
                        issues.append(f"{env_name}: artifactPolicy.app.{field} is required")
            service_policy = artifact_policy.get("service")
            if not isinstance(service_policy, dict):
                issues.append(f"{env_name}: artifactPolicy.service must be a mapping")
            else:
                for field in REQUIRED_SERVICE_POLICY:
                    if field not in service_policy:
                        issues.append(
                            f"{env_name}: artifactPolicy.service.{field} is required"
                        )

    targets = manifest.get("targets")
    if not isinstance(targets, dict):
        issues.append("targets must be a mapping")
        return issues

    missing_targets = [target for target in TARGETS if target not in targets]
    if missing_targets:
        issues.append(f"missing targets: {', '.join(missing_targets)}")

    try:
        local_ports_manifest = port_manifest or load_port_manifest()
    except Exception as exc:  # pragma: no cover - defensive gate detail.
        local_ports_manifest = {}
        issues.append(f"local port manifest could not be loaded: {exc}")

    for target_name in TARGETS:
        target = targets.get(target_name)
        if not isinstance(target, dict):
            continue
        env_name = str(target.get("env", "")).strip()
        if env_name not in ENVIRONMENTS:
            issues.append(f"{target_name}: env must be one of {', '.join(ENVIRONMENTS)}")
        if target.get("baseRoleSet") != "environment":
            issues.append(f"{target_name}: baseRoleSet must be environment")
        url_overrides = target.get("urlOverrides") or {}
        if not isinstance(url_overrides, dict):
            issues.append(f"{target_name}: urlOverrides must be a mapping")
        public_bases = target.get("publicBases")
        if not isinstance(public_bases, dict):
            issues.append(f"{target_name}: derived publicBases must be a mapping")
        else:
            for field in URL_FIELDS:
                value = str(public_bases.get(field, "")).strip()
                if not value:
                    issues.append(
                        f"{target_name}: derived publicBases.{field} is required"
                    )
                else:
                    issues.extend(
                        _validate_target_public_base(
                            f"{target_name}: publicBases.{field}",
                            target_name,
                            field,
                            value,
                        )
                    )
        resolved_roles = target.get("resolvedUrlRoles")
        if not isinstance(resolved_roles, dict):
            issues.append(f"{target_name}: resolvedUrlRoles must be a mapping")
        else:
            expected_tls_profile = (
                PROD_TLS_PROFILE
                if target_name == "prod-hosted"
                else LOCAL_TLS_PROFILE_BY_TARGET.get(target_name)
            )
            for field in URL_FIELDS:
                role = resolved_roles.get(field)
                if not isinstance(role, dict):
                    issues.append(
                        f"{target_name}: resolvedUrlRoles.{field} is required"
                    )
                    continue
                expected_port_role = None
                if target_name != "prod-hosted":
                    expected_port_role = LOCAL_PUBLIC_PORT_ROLES[field]
                    if target_name == "gamma-local" and field == "mediaUpload":
                        expected_port_role = "object-storage-edge"
                if role.get("portRole") != expected_port_role:
                    issues.append(
                        f"{target_name}: resolvedUrlRoles.{field}.portRole must be "
                        f"{expected_port_role}"
                    )
                if role.get("tlsProfile") != expected_tls_profile:
                    issues.append(
                        f"{target_name}: resolvedUrlRoles.{field}.tlsProfile must be "
                        f"{expected_tls_profile}"
                    )
        backend = str(target.get("backend", "")).strip()
        if backend not in {"local", "ssh-hosted"}:
            issues.append(
                f"{target_name}: backend must be local or ssh-hosted"
            )
        local_resource_group = str(
            target.get("localResourceGroup", "")
        ).strip()
        if backend == "local" and not re.fullmatch(
            r"[a-z][a-z0-9-]{2,63}",
            local_resource_group,
        ):
            issues.append(
                f"{target_name}: local targets require a canonical localResourceGroup"
            )
        if backend != "local" and local_resource_group:
            issues.append(
                f"{target_name}: localResourceGroup is reserved for local targets"
            )
        profile = target.get("portProfile")
        role_ports: dict[str, int] = {}
        if backend == "local" and not profile:
            issues.append(f"{target_name}: local targets require portProfile")
        if backend == "local" and profile and local_ports_manifest:
            try:
                role_ports = profile_ports(local_ports_manifest, str(profile))
            except KeyError:
                issues.append(
                    f"{target_name}: portProfile {profile} must exist in local port manifest"
                )
            if isinstance(public_bases, dict):
                for field, role_name in LOCAL_PUBLIC_PORT_ROLES.items():
                    if target_name == "gamma-local" and field == "mediaUpload":
                        role_name = "object-storage-edge"
                    value = str(public_bases.get(field, "")).strip()
                    actual_port = _url_port(value)
                    expected_port = role_ports.get(role_name)
                    if actual_port != expected_port:
                        issues.append(
                            f"{target_name}: publicBases.{field} port must match {profile}/{role_name}={expected_port}, got {actual_port}"
                        )
            origins = target.get("origins")
            if origins is None:
                origins = {}
            if not isinstance(origins, dict):
                issues.append(f"{target_name}: origins must be a mapping when declared")
            elif origins:
                for field, role_name in LOCAL_ORIGIN_PORT_ROLES.items():
                    value = str(origins.get(field, "")).strip()
                    actual_port = _url_port(value)
                    expected_port = role_ports.get(role_name)
                    if actual_port != expected_port:
                        issues.append(
                            f"{target_name}: origins.{field} port must match {profile}/{role_name}={expected_port}, got {actual_port}"
                        )
                    host = _url_host(value)
                    if host not in {"127.0.0.1", "localhost"}:
                        issues.append(
                            f"{target_name}: origins.{field} must stay on loopback host"
                        )
        data_release = target.get("dataRelease")
        if target_name in ENVIRONMENT_CANONICAL_TARGET.values():
            if not isinstance(data_release, dict):
                issues.append(f"{target_name}: dataRelease must be a mapping")
            else:
                mode = str(data_release.get("mode") or "")
                if mode not in DATA_RELEASE_MODES:
                    issues.append(
                        f"{target_name}: dataRelease.mode must be one of {sorted(DATA_RELEASE_MODES)}"
                    )
                if mode == "projection-only" and env_name != "alpha":
                    issues.append(
                        f"{target_name}: projection-only data release is reserved for alpha"
                    )
                if mode == "local-import":
                    if backend != "local":
                        issues.append(f"{target_name}: local-import requires local backend")
                    ready_timeout = data_release.get("publicReadyTimeoutSeconds")
                    if (
                        isinstance(ready_timeout, bool)
                        or not isinstance(ready_timeout, int)
                        or ready_timeout < 1
                    ):
                        issues.append(
                            f"{target_name}: dataRelease.publicReadyTimeoutSeconds must be a positive integer"
                        )
                    for field in (
                        "mongoPortRole",
                        "redisPortRole",
                        "userPostgresPortRole",
                    ):
                        role = str(data_release.get(field) or "")
                        if not role or role not in role_ports:
                            issues.append(
                                f"{target_name}: dataRelease.{field} must reference a port role"
                            )
                    redis_database = data_release.get("redisDatabase")
                    if (
                        isinstance(redis_database, bool)
                        or not isinstance(redis_database, int)
                        or redis_database < 0
                    ):
                        issues.append(
                            f"{target_name}: dataRelease.redisDatabase must be a non-negative integer"
                        )
                    media_ref = str(data_release.get("mediaLocalRef") or "")
                    if not media_ref or Path(media_ref).is_absolute() or ".." in Path(media_ref).parts:
                        issues.append(
                            f"{target_name}: dataRelease.mediaLocalRef must be a safe target-local relative path"
                        )
                if mode == "hosted-import":
                    if backend != "ssh-hosted":
                        issues.append(f"{target_name}: hosted-import requires ssh-hosted backend")
                    for field in (
                        "mongoUriEnv",
                        "redisAddrEnv",
                        "userPostgresDsnEnv",
                        "mediaRootEnv",
                    ):
                        env_key = str(data_release.get(field) or "")
                        if not DATA_RELEASE_ENV_KEY_RE.fullmatch(env_key):
                            issues.append(
                                f"{target_name}: dataRelease.{field} must be an environment key name"
                            )
                    redis_database = data_release.get("redisDatabase")
                    if (
                        isinstance(redis_database, bool)
                        or not isinstance(redis_database, int)
                        or redis_database < 0
                    ):
                        issues.append(
                            f"{target_name}: dataRelease.redisDatabase must be a non-negative integer"
                        )
        if target_name == "prod-hosted" and env_name != "prod":
            issues.append("prod-hosted target must map to prod environment")
        if target_name == "prod-hosted" and backend != "ssh-hosted":
            issues.append("prod-hosted target must use ssh-hosted backend")
    for env_name, target_name in ENVIRONMENT_CANONICAL_TARGET.items():
        env = environments.get(env_name)
        target = targets.get(target_name)
        if not isinstance(env, dict) or not isinstance(target, dict):
            continue
        env_bases = env.get("publicBases")
        target_bases = target.get("publicBases")
        if isinstance(env_bases, dict) and isinstance(target_bases, dict):
            for field in URL_FIELDS:
                env_value = str(env_bases.get(field, "")).strip()
                target_value = str(target_bases.get(field, "")).strip()
                if env_value != target_value:
                    issues.append(
                        f"{env_name}: publicBases.{field} must match canonical target {target_name}, got {env_value} vs {target_value}"
                    )

    return issues


def environment_url_values(manifest: dict[str, Any], env_name: str) -> list[str]:
    public_bases = get_environment(manifest, env_name).get("publicBases", {})
    return [str(public_bases.get(field, "")).strip() for field in URL_FIELDS]


def host_allowlist(manifest: dict[str, Any], env_name: str) -> list[str]:
    return sorted(
        {
            _url_host(value)
            for value in environment_url_values(manifest, env_name)
            if _url_host(value)
        }
    )


def forbidden_host_tokens(manifest: dict[str, Any], env_name: str) -> list[str]:
    if env_name == "prod":
        return [
            ".test",
            ".alpha.quwoquan.com",
            ".beta.quwoquan.com",
            ".gamma.quwoquan.com",
            ".sim.quwoquan.com",
            "127.0.0.1",
            "10.0.2.2",
            ".localhost",
        ]
    other_labels = sorted({"alpha", "beta", "gamma", "sim"} - {env_name})
    return [
        ".test",
        *(f".{label}.quwoquan.com" for label in other_labels),
    ]


def app_artifact_policy(manifest: dict[str, Any], env_name: str) -> dict[str, Any]:
    return dict(get_environment(manifest, env_name).get("artifactPolicy", {}).get("app", {}))


def service_artifact_policy(manifest: dict[str, Any], env_name: str) -> dict[str, Any]:
    return dict(
        get_environment(manifest, env_name).get("artifactPolicy", {}).get("service", {})
    )


def _looks_like_cidr(value: str) -> bool:
    return bool(re.match(r"^\d{1,3}(?:\.\d{1,3}){3}/\d{1,2}$", value))


def _validate_url_role_definition(
    label: str,
    field: str,
    role: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    actual_fields = set(role)
    if actual_fields != URL_SHAPE_FIELDS:
        missing = sorted(URL_SHAPE_FIELDS - actual_fields)
        unsupported = sorted(actual_fields - URL_SHAPE_FIELDS)
        if missing:
            issues.append(f"{label} is missing URL shape fields: {missing}")
        if unsupported:
            issues.append(
                f"{label} duplicates governance or contains unsupported fields: "
                f"{unsupported}"
            )
    scheme = str(role.get("scheme") or "").strip()
    if scheme not in {"https", "wss"}:
        issues.append(f"{label}.scheme must be https or wss")
    host = str(role.get("host") or "").strip()
    if not re.fullmatch(
        r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+quwoquan\.com",
        host,
    ) and host != "quwoquan.com":
        issues.append(f"{label}.host must be a canonical quwoquan.com hostname")
    path_base = str(role.get("pathBase") or "").strip()
    if (
        not path_base.startswith("/")
        or "//" in path_base
        or "?" in path_base
        or "#" in path_base
        or ".." in Path(path_base).parts
    ):
        issues.append(f"{label}.pathBase must be a canonical absolute path")
    tls_profile = str(role.get("tlsProfile") or "").strip()
    if not tls_profile:
        issues.append(f"{label}.tlsProfile is required")
    port_role = role.get("portRole")
    if port_role is not None and (
        not isinstance(port_role, str)
        or not re.fullmatch(r"[a-z][a-z0-9-]{2,63}", port_role)
    ):
        issues.append(f"{label}.portRole must be null or a canonical port role")
    return issues


def _validate_target_public_base(
    label: str,
    target_name: str,
    field: str,
    value: str,
) -> list[str]:
    issues: list[str] = []
    parsed = urlparse(value)
    if parsed.scheme not in {"https", "wss"}:
        issues.append(f"{label} must use a secure public scheme")
    host = parsed.hostname or ""
    if not re.fullmatch(
        r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+quwoquan\.com",
        host,
    ) and host != "quwoquan.com":
        issues.append(f"{label} must use a canonical quwoquan.com hostname")
    actual_path = parsed.path or "/"
    if (
        not actual_path.startswith("/")
        or "//" in actual_path
        or ".." in Path(actual_path).parts
    ):
        issues.append(f"{label} path must be canonical")
    if parsed.username or parsed.password:
        issues.append(f"{label} must not contain userinfo")
    if parsed.query or parsed.fragment:
        issues.append(f"{label} must not contain query or fragment")
    if target_name == "prod-hosted" and _url_port(value) is not None:
        issues.append(f"{label} must use implicit port 443")
    return issues
def _url_host(value: str) -> str:
    return (urlparse(value).hostname or "").lower()


def _url_port(value: str) -> int | None:
    parsed = urlparse(value)
    try:
        return parsed.port
    except ValueError:
        return None
