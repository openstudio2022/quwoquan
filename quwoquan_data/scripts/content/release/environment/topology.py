"""Typed projection of the Ops topology for Data release application."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import os
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

from core.io import read_json
from core.paths import OUTPUT_ROOT, REPO_ROOT
from content.release.model import DeploymentEnvironment
from quwoquan_ops.cli.lib.environment_topology import (
    get_environment,
    get_target,
    load_environment_topology,
)


_PORTS_PATH = REPO_ROOT / "quwoquan_ops" / "environments" / "local_env_port_manifest.yaml"


class EnvironmentReleaseMode(StrEnum):
    PROJECTION_ONLY = "projection-only"
    LOCAL_IMPORT = "local-import"
    HOSTED_IMPORT = "hosted-import"


class MediaDeliverySlice(StrEnum):
    AVATAR = "avatar"
    IMAGE = "image"
    VIDEO = "video"


@dataclass(frozen=True, slots=True)
class EnvironmentReleaseTarget:
    environment: DeploymentEnvironment
    target_name: str
    mode: EnvironmentReleaseMode
    mongo_uri: str
    user_postgres_dsn: str
    media_sync_root: Path | None
    media_delivery_base_url: str
    api_base_url: str
    missing_requirements: tuple[str, ...]
    ssl_cafile: str = ""
    redis_addr: str = ""
    redis_database: int = 0

    @property
    def import_ready(self) -> bool:
        return self.mode is not EnvironmentReleaseMode.PROJECTION_ONLY and not self.missing_requirements

    def media_base_url(self, media_slice: MediaDeliverySlice) -> str:
        return (
            f"{self.media_delivery_base_url.rstrip('/')}/media/{media_slice.value}"
        )


def _local_managed_ssl_cafile(target_name: str) -> str:
    """Return the local-managed root CA path when the target uses private TLS."""
    try:
        from quwoquan_ops.cli.lib.public_domain_tls import (
            PublicDomainTlsError,
            root_certificate_path,
            tls_profile,
        )
    except ImportError as exc:
        raise RuntimeError(
            "Ops local-managed TLS resolver is unavailable"
        ) from exc
    try:
        _profile_name, kind, _profile = tls_profile(target_name)
    except PublicDomainTlsError as exc:
        if not target_name.endswith("-local"):
            return ""
        raise RuntimeError(str(exc)) from exc
    if kind != "local-managed":
        return ""
    try:
        return str(root_certificate_path(target_name))
    except PublicDomainTlsError as exc:
        raise RuntimeError(str(exc)) from exc


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
    manifest = load_environment_topology()
    environment_row = get_environment(manifest, environment.value)
    target_name = str(environment_row.get("dataReleaseTarget") or "").strip()
    target = get_target(manifest, target_name)
    release = _mapping(target.get("dataRelease"), label=f"{target_name}.dataRelease")
    mode = EnvironmentReleaseMode(str(release.get("mode") or ""))
    public_bases = _mapping(target.get("publicBases"), label=f"{target_name}.publicBases")
    media_image = urlsplit(str(public_bases.get("mediaImage") or ""))
    media_delivery_base_url = urlunsplit(
        (media_image.scheme, media_image.netloc, "", "", "")
    )
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
            media_delivery_base_url=media_delivery_base_url,
            api_base_url=api_base_url,
            missing_requirements=(),
            ssl_cafile=_local_managed_ssl_cafile(target_name),
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
        redis_port = _local_port(
            ports,
            profile,
            str(release.get("redisPortRole") or ""),
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
            media_delivery_base_url=media_delivery_base_url,
            api_base_url=api_base_url,
            missing_requirements=(),
            ssl_cafile=_local_managed_ssl_cafile(target_name),
            redis_addr=f"127.0.0.1:{redis_port}",
            redis_database=int(release.get("redisDatabase") or 0),
        )

    mongo_env = str(release.get("mongoUriEnv") or "")
    redis_env = str(release.get("redisAddrEnv") or "")
    user_postgres_env = str(release.get("userPostgresDsnEnv") or "")
    media_env = str(release.get("mediaRootEnv") or "")
    mongo_uri = str(os.environ.get(mongo_env) or "").strip() if mongo_env else ""
    redis_addr = str(os.environ.get(redis_env) or "").strip() if redis_env else ""
    user_postgres_dsn = (
        str(os.environ.get(user_postgres_env) or "").strip() if user_postgres_env else ""
    )
    media_root = str(os.environ.get(media_env) or "").strip() if media_env else ""
    for field, env_key, value in (
        ("mongoUriEnv", mongo_env, mongo_uri),
        ("redisAddrEnv", redis_env, redis_addr),
        ("userPostgresDsnEnv", user_postgres_env, user_postgres_dsn),
        ("mediaRootEnv", media_env, media_root),
    ):
        if not env_key:
            missing.append(field)
        elif not value:
            missing.append(env_key)
    return EnvironmentReleaseTarget(
        environment=environment,
        target_name=target_name,
        mode=mode,
        mongo_uri=mongo_uri,
        user_postgres_dsn=user_postgres_dsn,
        media_sync_root=Path(media_root).expanduser() if media_root else None,
        media_delivery_base_url=media_delivery_base_url,
        api_base_url=api_base_url,
        missing_requirements=tuple(missing),
        ssl_cafile=_local_managed_ssl_cafile(target_name),
        redis_addr=redis_addr,
        redis_database=int(release.get("redisDatabase") or 0),
    )


__all__ = [
    "EnvironmentReleaseMode",
    "EnvironmentReleaseTarget",
    "resolve_environment_release_target",
]
