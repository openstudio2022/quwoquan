"""Typed projection of the Ops topology for Data release application."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import os
from pathlib import Path
from typing import Any, Mapping

from core.io import read_json
from core.paths import OUTPUT_ROOT, REPO_ROOT
from content.release.model import DeploymentEnvironment


_ENVIRONMENTS_ROOT = REPO_ROOT / "quwoquan_ops" / "environments"
_PORTS_PATH = REPO_ROOT / "quwoquan_ops" / "environments" / "local_env_port_manifest.yaml"


class EnvironmentReleaseMode(StrEnum):
    PROJECTION_ONLY = "projection-only"
    LOCAL_IMPORT = "local-import"
    HOSTED_IMPORT = "hosted-import"


@dataclass(frozen=True, slots=True)
class EnvironmentReleaseTarget:
    environment: DeploymentEnvironment
    target_name: str
    mode: EnvironmentReleaseMode
    mongo_uri: str
    user_postgres_dsn: str
    media_sync_root: Path | None
    media_base_url: str
    api_base_url: str
    missing_requirements: tuple[str, ...]

    @property
    def import_ready(self) -> bool:
        return self.mode is not EnvironmentReleaseMode.PROJECTION_ONLY and not self.missing_requirements

    @property
    def api_resolve_host(self) -> str:
        return "127.0.0.1" if self.mode is EnvironmentReleaseMode.LOCAL_IMPORT else ""

    @property
    def api_insecure_tls(self) -> bool:
        return self.mode is EnvironmentReleaseMode.LOCAL_IMPORT


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeError(f"{label} must be a mapping")
    return value


def _local_port(port_manifest: Mapping[str, Any], profile: str, role: str) -> int:
    profiles = _mapping(port_manifest.get("profiles"), label="local port profiles")
    roles = _mapping(port_manifest.get("roles"), label="local port roles")
    profile_row = _mapping(profiles.get(profile), label=f"port profile {profile}")
    role_row = _mapping(roles.get(role), label=f"port role {role}")
    port = int(profile_row.get("blockStart") or 0) + int(role_row.get("slotOffset") or 0)
    if port <= 0 or port > int(profile_row.get("blockEnd") or 0):
        raise RuntimeError(f"derived port outside profile: profile={profile} role={role}")
    return port


def resolve_environment_release_target(env: str) -> EnvironmentReleaseTarget:
    environment = DeploymentEnvironment(str(env))
    runtime_path = _ENVIRONMENTS_ROOT / environment.value / "runtime.yaml"
    environment_row = _mapping(read_json(runtime_path), label=f"environment {environment.value}")
    if (
        environment_row.get("schema") != "environment-runtime"
        or environment_row.get("environment") != environment.value
    ):
        raise RuntimeError(f"environment runtime identity mismatch: {runtime_path}")
    targets = _mapping(environment_row.get("targets"), label="environment targets")
    target_name = str(environment_row.get("dataReleaseTarget") or "").strip()
    target = _mapping(targets.get(target_name), label=f"data release target {target_name}")
    release = _mapping(target.get("dataRelease"), label=f"{target_name}.dataRelease")
    mode = EnvironmentReleaseMode(str(release.get("mode") or ""))
    public_bases = _mapping(target.get("publicBases"), label=f"{target_name}.publicBases")
    media_base_key = str(release.get("mediaPublicBaseKey") or "")
    media_base_url = str(public_bases.get(media_base_key) or "").rstrip("/")
    api_base_url = str(public_bases.get("api") or "").rstrip("/")
    missing: list[str] = []

    if mode is EnvironmentReleaseMode.PROJECTION_ONLY:
        return EnvironmentReleaseTarget(
            environment=environment,
            target_name=target_name,
            mode=mode,
            mongo_uri="",
            user_postgres_dsn="",
            media_sync_root=None,
            media_base_url=media_base_url,
            api_base_url=api_base_url,
            missing_requirements=(),
        )

    if mode is EnvironmentReleaseMode.LOCAL_IMPORT:
        profile = str(target.get("portProfile") or "")
        ports = read_json(_PORTS_PATH)
        mongo_port = _local_port(ports, profile, str(release.get("mongoPortRole") or ""))
        postgres_port = _local_port(
            ports,
            profile,
            str(release.get("userPostgresPortRole") or ""),
        )
        media_ref = Path(str(release.get("mediaLocalRef") or ""))
        return EnvironmentReleaseTarget(
            environment=environment,
            target_name=target_name,
            mode=mode,
            mongo_uri=f"mongodb://127.0.0.1:{mongo_port}/?directConnection=true",
            user_postgres_dsn=(
                f"postgres://quwoquan:quwoquan@127.0.0.1:{postgres_port}/quwoquan?sslmode=disable"
            ),
            media_sync_root=OUTPUT_ROOT / "env" / environment.value / "local" / target_name / media_ref,
            media_base_url=media_base_url,
            api_base_url=api_base_url,
            missing_requirements=(),
        )

    mongo_env = str(release.get("mongoUriEnv") or "")
    user_postgres_env = str(release.get("userPostgresDsnEnv") or "")
    media_env = str(release.get("mediaRootEnv") or "")
    mongo_uri = str(os.environ.get(mongo_env) or "").strip()
    user_postgres_dsn = str(os.environ.get(user_postgres_env) or "").strip()
    media_root = str(os.environ.get(media_env) or "").strip()
    for env_key, value in (
        (mongo_env, mongo_uri),
        (user_postgres_env, user_postgres_dsn),
        (media_env, media_root),
    ):
        if env_key and not value:
            missing.append(env_key)
    return EnvironmentReleaseTarget(
        environment=environment,
        target_name=target_name,
        mode=mode,
        mongo_uri=mongo_uri,
        user_postgres_dsn=user_postgres_dsn,
        media_sync_root=Path(media_root).expanduser() if media_root else None,
        media_base_url=media_base_url,
        api_base_url=api_base_url,
        missing_requirements=tuple(missing),
    )


__all__ = [
    "EnvironmentReleaseMode",
    "EnvironmentReleaseTarget",
    "resolve_environment_release_target",
]
