from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .common import ROOT, load_json_yaml


DEFAULT_PATH = ROOT / "deploy" / "shared" / "environment_topology_manifest.yaml"
ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
TARGETS = (
    "alpha-local",
    "beta-local",
    "gamma-local",
    "gamma-hosted",
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


def validate_environment_topology(manifest: dict[str, Any]) -> list[str]:
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
                elif not (
                    value.startswith("http://")
                    or value.startswith("https://")
                    or value.startswith("ws://")
                    or value.startswith("wss://")
                ):
                    issues.append(
                        f"{env_name}: publicBases.{field} must include http(s)/ws(s) scheme",
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
        backend = str(target.get("backend", "")).strip()
        if backend not in {"local", "ssh-hosted", "workflow"}:
            issues.append(
                f"{target_name}: backend must be local, ssh-hosted, or workflow"
            )
        profile = target.get("portProfile")
        if backend == "local" and not profile:
            issues.append(f"{target_name}: local targets require portProfile")
        if target_name == "prod-hosted" and env_name != "prod":
            issues.append("prod-hosted target must map to prod environment")
        if target_name == "gamma-hosted" and env_name != "gamma":
            issues.append("gamma-hosted target must map to gamma environment")

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
