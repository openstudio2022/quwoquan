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
URL_FIELDS = (
    "api",
    "realtime",
    "rtc",
    "productOps",
    "mediaAvatar",
    "mediaImage",
    "mediaVideo",
    "mediaUpload",
)
SECURE_HTTP_FIELDS = (
    "api",
    "productOps",
    "mediaAvatar",
    "mediaImage",
    "mediaVideo",
    "mediaUpload",
)
REQUIRED_SUBNETS = ("edge", "media", "service", "data")
REQUIRED_APP_POLICY = (
    "runtimeEnv",
    "dataSource",
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


def load_environment_topology(path: Path | None = None) -> dict[str, Any]:
    if path is not None and path.is_file():
        loaded = load_json_yaml(path)
        if not isinstance(loaded, dict):
            raise RuntimeError("environment topology input must be a mapping")
        return loaded

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
    return {
        "schema": "environment-topology",
        "environments": environments,
        "targets": targets,
    }


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
    issues: list[str] = []
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
        public_bases = env.get("publicBases")
        if not isinstance(public_bases, dict):
            issues.append(f"{env_name}: publicBases must be a mapping")
        else:
            for field in URL_FIELDS:
                value = str(public_bases.get(field, "")).strip()
                if not value:
                    issues.append(f"{env_name}: publicBases.{field} is required")
                else:
                    issues.extend(_validate_public_base_url(f"{env_name}: publicBases.{field}", field, value))

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

        allowlist = env.get("hostAllowlist")
        if not isinstance(allowlist, list) or not allowlist:
            issues.append(f"{env_name}: hostAllowlist must be a non-empty list")
            allowlist_values: set[str] = set()
        else:
            allowlist_values = {str(item).strip() for item in allowlist if str(item).strip()}

        if isinstance(public_bases, dict):
            public_values = [
                str(public_bases.get(field, "")).strip()
                for field in URL_FIELDS
            ]
            public_hosts = {_url_host(value) for value in public_values}
            public_hosts.discard("")
            for host in sorted(public_hosts):
                if host not in allowlist_values:
                    issues.append(
                        f"{env_name}: publicBases host {host} must be listed in hostAllowlist"
                    )
            forbidden_tokens = [
                str(item).strip()
                for item in env.get("forbiddenHostTokens", [])
                if str(item).strip()
            ]
            joined_public_values = "\n".join(public_values)
            for token in forbidden_tokens:
                if token in joined_public_values:
                    issues.append(
                        f"{env_name}: publicBases must not contain forbidden host token {token}"
                    )

        if env.get("artifactPolicy", {}).get("app", {}).get("dataSource") != "remote":
            issues.append(f"{env_name}: artifactPolicy.app.dataSource must be remote")

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
        public_bases = target.get("publicBases")
        if not isinstance(public_bases, dict):
            issues.append(f"{target_name}: publicBases must be a mapping")
        else:
            for field in URL_FIELDS:
                value = str(public_bases.get(field, "")).strip()
                if not value:
                    issues.append(f"{target_name}: publicBases.{field} is required")
                else:
                    issues.extend(
                        _validate_public_base_url(
                            f"{target_name}: publicBases.{field}",
                            field,
                            value,
                        )
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
                    host = _url_host(value)
                    if not host.endswith(".quwoquan-env.test"):
                        issues.append(
                            f"{target_name}: publicBases.{field} must use a quwoquan-env.test host"
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
                public_key = str(data_release.get("mediaPublicBaseKey") or "")
                if public_key not in URL_FIELDS:
                    issues.append(
                        f"{target_name}: dataRelease.mediaPublicBaseKey must name a publicBases field"
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
                    for field in ("mongoPortRole",):
                        role = str(data_release.get(field) or "")
                        if not role or role not in role_ports:
                            issues.append(
                                f"{target_name}: dataRelease.{field} must reference a port role"
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
                        "mediaRootEnv",
                    ):
                        env_key = str(data_release.get(field) or "")
                        if not DATA_RELEASE_ENV_KEY_RE.fullmatch(env_key):
                            issues.append(
                                f"{target_name}: dataRelease.{field} must be an environment key name"
                            )
        if target_name == "prod-hosted" and env_name != "prod":
            issues.append("prod-hosted target must map to prod environment")
        if target_name == "prod-hosted" and backend != "ssh-hosted":
            issues.append("prod-hosted target must use ssh-hosted backend")
        if backend == "ssh-hosted":
            ssh_host = str(target.get("sshHost") or "").strip()
            if (
                not ssh_host
                or "://" in ssh_host
                or "/" in ssh_host
                or any(character.isspace() for character in ssh_host)
            ):
                issues.append(
                    f"{target_name}: sshHost must be a bare SSH hostname or IP address"
                )
        if backend == "ssh-hosted" and isinstance(public_bases, dict):
            env_allowlist = {
                str(item).strip()
                for item in get_environment(manifest, env_name).get("hostAllowlist", [])
                if str(item).strip()
            }
            for field in URL_FIELDS:
                host = _url_host(str(public_bases.get(field, "")).strip())
                if host and host not in env_allowlist:
                    issues.append(
                        f"{target_name}: publicBases.{field} host {host} must be allowed by {env_name}"
                    )

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
    return [str(item) for item in get_environment(manifest, env_name).get("hostAllowlist", [])]


def forbidden_host_tokens(manifest: dict[str, Any], env_name: str) -> list[str]:
    return [
        str(item)
        for item in get_environment(manifest, env_name).get("forbiddenHostTokens", [])
    ]


def app_artifact_policy(manifest: dict[str, Any], env_name: str) -> dict[str, Any]:
    return dict(get_environment(manifest, env_name).get("artifactPolicy", {}).get("app", {}))


def service_artifact_policy(manifest: dict[str, Any], env_name: str) -> dict[str, Any]:
    return dict(
        get_environment(manifest, env_name).get("artifactPolicy", {}).get("service", {})
    )


def _looks_like_cidr(value: str) -> bool:
    return bool(re.match(r"^\d{1,3}(?:\.\d{1,3}){3}/\d{1,2}$", value))


def _validate_public_base_url(label: str, field: str, value: str) -> list[str]:
    if field in {"realtime", "rtc"}:
        if value.startswith("wss://"):
            return []
        return [f"{label} must use secure wss://"]
    if field in SECURE_HTTP_FIELDS:
        if value.startswith("https://"):
            return []
        return [f"{label} must use secure https://"]
    if value.startswith(("http://", "https://", "ws://", "wss://")):
        return []
    return [f"{label} must include http(s)/ws(s) scheme"]


def _url_host(value: str) -> str:
    return (urlparse(value).hostname or "").lower()


def _url_port(value: str) -> int | None:
    parsed = urlparse(value)
    try:
        return parsed.port
    except ValueError:
        return None
