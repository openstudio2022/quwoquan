from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .common import ROOT, load_json_yaml
from .port_manifest import load_port_manifest, profile_ports


DEFAULT_PATH = ROOT / "quwoquan_ops" / "environments" / "environment_topology_manifest.yaml"
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
    "productOps": "product-ops-edge",
    "mediaAvatar": "media-edge",
    "mediaImage": "media-edge",
    "mediaVideo": "media-edge",
    "mediaUpload": "media-edge",
}
LOCAL_ORIGIN_PORT_ROLES = {
    "mediaOrigin": "media-origin",
}


def load_environment_topology(path: Path | None = None) -> dict[str, Any]:
    loaded = load_json_yaml(path or DEFAULT_PATH)
    if not isinstance(loaded, dict):
        raise RuntimeError("environment topology manifest must be a mapping")
    return loaded


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
    if manifest.get("schemaVersion") != "environment-topology/v1":
        issues.append("schemaVersion must be environment-topology/v1")

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

        mock_flags = env.get("mockBoundaryFlags")
        if not isinstance(mock_flags, dict):
            issues.append(f"{env_name}: mockBoundaryFlags must be a mapping")

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

        if env_name == "alpha":
            if env.get("artifactPolicy", {}).get("app", {}).get("dataSource") != "mock":
                issues.append("alpha: artifactPolicy.app.dataSource must be mock")
        else:
            if env.get("artifactPolicy", {}).get("app", {}).get("dataSource") != "remote":
                issues.append(
                    f"{env_name}: artifactPolicy.app.dataSource must be remote"
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
        profile = target.get("portProfile")
        if backend == "local" and not profile:
            issues.append(f"{target_name}: local targets require portProfile")
        if backend == "local" and profile and local_ports_manifest:
            try:
                role_ports = profile_ports(local_ports_manifest, str(profile))
            except KeyError:
                role_ports = {}
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
            environment_flags = environments.get(env_name, {}).get("mockBoundaryFlags", {})
            requires_media_origin = bool(
                isinstance(environment_flags, dict)
                and environment_flags.get("mediaOrigin")
            )
            if origins is None and not requires_media_origin:
                origins = {}
            if not isinstance(origins, dict):
                issues.append(f"{target_name}: origins must be a mapping when declared")
            elif requires_media_origin and not origins:
                issues.append(f"{target_name}: mediaOrigin boundary requires origins mapping")
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
        if target_name == "prod-hosted" and env_name != "prod":
            issues.append("prod-hosted target must map to prod environment")
        if target_name == "prod-hosted" and backend != "ssh-hosted":
            issues.append("prod-hosted target must use ssh-hosted backend")
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
    if field == "realtime":
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
