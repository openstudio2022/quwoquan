"""Typed projection of the Ops topology for Data release application."""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import yaml

from content.release.model import DeploymentEnvironment
from core.io import read_json
from core.paths import REPO_ROOT

_PORTS_PATH = REPO_ROOT / "quwoquan_ops" / "environments" / "local_env_port_manifest.yaml"


def _ops_topology_functions() -> tuple[Any, Any, Any]:
    """Load Ops topology only when an environment operation actually runs.

    Data campaign capsules intentionally contain the governed Data executor
    closure, not the Ops environment implementation.  Keeping this dependency
    lazy lets author/review/publish import the release contracts without
    silently broadening the capsule; ship/readiness still fail closed if Ops is
    unavailable at the environment boundary.
    """
    try:
        from quwoquan_ops.cli.lib.environment_topology import (
            get_environment,
            get_target,
            load_environment_topology,
        )
    except ImportError as exc:
        raise RuntimeError("Ops environment topology resolver is unavailable") from exc
    return load_environment_topology, get_environment, get_target


class EnvironmentReleaseMode(StrEnum):
    PROJECTION_ONLY = "projection-only"
    LOCAL_IMPORT = "local-import"
    HOSTED_IMPORT = "hosted-import"


class MediaDeliverySlice(StrEnum):
    AVATAR = "avatar"
    IMAGE = "image"
    VIDEO = "video"


def resolve_media_cdn_bases(
    environment: str,
    *,
    topology_manifest: Path | None = None,
) -> tuple[str, str]:
    """从 Ops 环境拓扑解析图片与视频 CDN 基址。"""
    load_environment_topology, get_environment, _get_target = (
        _ops_topology_functions()
    )
    manifest = (
        load_environment_topology(topology_manifest)
        if topology_manifest is not None
        else load_environment_topology()
    )
    try:
        node = get_environment(manifest, environment)
    except KeyError:
        node = {}
    public_bases = node.get("publicBases") or {}
    image_base = str(public_bases.get("mediaImage") or "").strip().rstrip("/")
    video_base = str(public_bases.get("mediaVideo") or "").strip().rstrip("/")

    if environment == "prod":
        if (
            "media.quwoquan.invalid" in image_base
            or "media.quwoquan.invalid" in video_base
        ):
            raise SystemExit("refusing media.quwoquan.invalid for prod media CDN")
        if not image_base:
            raise SystemExit("prod media CDN base unresolved")

    return image_base, video_base


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
    binding_digest: str = ""
    binding_artifact_digest: str = ""
    binding_artifact_path: Path | None = None
    tag_mongo_database: str = ""
    creator_mongo_database: str = ""
    homepage_mongo_database: str = ""
    content_mongo_database: str = ""
    creator_postgres_database: str = ""
    content_redis_namespace: str = ""
    post_safety_material_root: Path | None = None
    post_safety_current_binding_ref: str = ""
    post_safety_recovery_evidence_ref: str = ""
    post_safety_hmac_secret_ref: str = ""
    runtime_auth_env_ref: Path | None = None
    runtime_auth_issuer: str = ""
    runtime_auth_audience: str = ""
    runtime_auth_token_version: str = ""
    account_security_authority_base_url: str = ""
    account_security_authority_timeout_ms: int = 0
    content_importer_image_ref: str = ""

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
        raise TypeError(f"{label} must be a mapping")
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


def _candidate_binding(candidate_root: Path, *, environment: str, target_name: str) -> tuple[dict[str, Any], dict[str, str], bytes, dict[str, Any]]:
    """Load one fully validated candidate and its exact canonical binding bytes."""
    from quwoquan_ops.cli.lib.data_plane_binding import (
        DATA_PLANE_BINDING_PACKAGE_REF,
        DataPlaneBindingError,
        resolve_data_plane_environment,
        validate_canonical_data_plane_binding,
    )
    from quwoquan_ops.cli.lib.deployment_candidate_manifest import validate_candidate_manifest

    root = candidate_root.expanduser().absolute()
    manifest_path = root / "manifest.json"
    binding_path = root / DATA_PLANE_BINDING_PACKAGE_REF.as_posix()
    try:
        manifest_raw = manifest_path.read_bytes()
        manifest = json.loads(manifest_raw)
        validated = validate_candidate_manifest(
            manifest,
            expected_environment=environment,
            expected_target=target_name,
            require_full=True,
            candidate_root=root,
        )
        binding_raw = binding_path.read_bytes()
        canonical = validate_canonical_data_plane_binding(json.loads(binding_raw))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, DataPlaneBindingError) as exc:
        raise RuntimeError(f"DATA.RELEASE.DATA_PLANE_BINDING_INVALID: {exc}") from exc
    descriptor = validated.get("dataPlaneBinding")
    actual = {
        "ref": DATA_PLANE_BINDING_PACKAGE_REF.as_posix(),
        "digest": "sha256:" + hashlib.sha256(binding_raw).hexdigest(),
        "bindingDigest": str(canonical["bindingDigest"]),
    }
    if descriptor != actual:
        raise RuntimeError("DATA.RELEASE.DATA_PLANE_BINDING_IDENTITY_DRIFT: candidate descriptor differs from exact artifact")
    mode = "external" if target_name == "prod-hosted" else "local"
    resolve_data_plane_environment(
        {"dataPlane": {"resources": canonical["resources"], "bindings": canonical["bindings"]}},
        mode=mode,
        target_name=target_name,
    )
    return canonical, actual, binding_raw, validated


def _post_safety_import_projection(
    candidate_root: Path, *, environment: str, target_name: str,
    candidate_manifest: Mapping[str, Any], binding_digest: str,
) -> tuple[Path, str, str, str, str]:
    """Project importer locators from the exact running candidate generation."""
    from quwoquan_ops.cli.lib import output_paths
    from quwoquan_ops.cli.lib.generated.post_safety_runtime import (
        PostSafetyDeploymentStartupMaterial,
    )
    process_root = (
        output_paths.DEFAULT_LOCAL_RUNTIME_OUTPUT_ROOT
        / "env" / environment / "local" / target_name / "process"
    )
    full_receipt = process_root / "startup_attempt.json"
    bounded_receipt = process_root / "workloads/content-release/startup_attempt.json"
    receipt_path = full_receipt
    try:
        full_value = json.loads(full_receipt.read_text(encoding="utf-8"))
        if full_value.get("status") == "running":
            receipt = full_value
        else:
            receipt_path = bounded_receipt
            receipt = json.loads(bounded_receipt.read_text(encoding="utf-8"))
        required_identity = {
            "schema": "stackctl-local-startup-attempt",
            "env": environment,
            "target": target_name,
            "status": "running",
        }
        if (
            any(receipt.get(key) != value for key, value in required_identity.items())
            or receipt.get("workload") not in {"full", "content-release"}
        ):
            raise ValueError("content-release startup receipt identity is invalid")
        run_root = Path(str(receipt.get("runRoot") or "")).expanduser().absolute()
        runtime_runs = (
            output_paths.DEFAULT_LOCAL_RUNTIME_OUTPUT_ROOT / "env" / environment / "runs"
        ).absolute()
        if run_root.parent != runtime_runs or not run_root.is_dir():
            raise ValueError("content-release startup receipt runRoot is not canonical runtime evidence")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"DATA.RELEASE.POST_SAFETY_STARTUP_GENERATION_DRIFT: {exc}"
        ) from exc
    if (
        not isinstance(receipt, Mapping)
        or receipt.get("status") != "running"
        or receipt.get("candidateDigest") != candidate_manifest.get("baselineId")
    ):
        raise RuntimeError(
            "DATA.RELEASE.POST_SAFETY_STARTUP_GENERATION_DRIFT: "
            "running startup receipt differs from runtime candidate"
        )
    startup_path = output_paths.post_safety_startup_material_path(target_name)
    try:
        raw = startup_path.read_bytes()
        startup = PostSafetyDeploymentStartupMaterial.model_validate_json(raw)
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            f"DATA.RELEASE.POST_SAFETY_STARTUP_INVALID: {exc}"
        ) from exc
    canonical_raw = json.dumps(
        startup.model_dump(mode="json"), separators=(",", ":"), ensure_ascii=False
    ).encode()
    if raw != canonical_raw:
        raise RuntimeError("DATA.RELEASE.POST_SAFETY_STARTUP_INVALID: non-canonical bytes")
    if (
        startup.environment != environment
        or startup.target != target_name
        or startup.candidateDigest != candidate_manifest.get("packageDigest")
        or startup.dataPlaneBindingDigest != binding_digest
        or startup.postSafetyCurrent is None
    ):
        raise RuntimeError(
            "DATA.RELEASE.POST_SAFETY_STARTUP_GENERATION_DRIFT: "
            "startup material differs from candidate/startup receipt"
        )
    material_root = output_paths.deployment_target_path(
        target_name, "secrets", "post-safety", startup.runtimeGeneration
    )
    current_path = material_root / startup.postSafetyCurrent.ref
    try:
        current_raw = current_path.read_bytes()
        if "sha256:" + hashlib.sha256(current_raw).hexdigest() != startup.postSafetyCurrent.digest:
            raise ValueError("current digest differs")
        current = json.loads(current_raw)
        recovery_ref = str(current["fact"]["ref"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"DATA.RELEASE.POST_SAFETY_CURRENT_INVALID: {exc}"
        ) from exc
    try:
        importer_image = str(receipt["imageComposition"]["ociImages"]["service-core"]["ref"])
    except (KeyError, TypeError) as exc:
        raise RuntimeError(
            f"DATA.RELEASE.CONTENT_IMPORTER_IMAGE_INVALID: {exc}"
        ) from exc
    return (material_root, startup.postSafetyCurrent.ref, recovery_ref, "post-safety.key", importer_image)


def _binding(canonical: Mapping[str, Any], key: str, *, engine: str) -> Mapping[str, Any]:
    bindings = _mapping(canonical.get("bindings"), label="canonical bindings")
    value = _mapping(bindings.get(key), label=f"canonical binding {key}")
    service, slot = key.split(".", 1)
    if value.get("service") != service or value.get("slot") != slot or value.get("engine") != engine:
        raise RuntimeError(f"DATA.RELEASE.DATA_PLANE_ROLE_DRIFT: {key}")
    resource = str(value.get("resource") or "")
    resources = _mapping(canonical.get("resources"), label="canonical resources")
    resource_row = _mapping(resources.get(resource), label=f"canonical resource {resource}")
    if resource_row.get("engine") != engine:
        raise RuntimeError(f"DATA.RELEASE.DATA_PLANE_RESOURCE_DRIFT: {key}")
    return value


def _injected(environment: Mapping[str, Any], service: str, key: str) -> str:
    service_values = _mapping(environment.get(service), label=f"resolved {service}")
    value = str(service_values.get(key) or "").strip()
    if not value:
        raise RuntimeError(f"DATA.RELEASE.DATA_PLANE_COORDINATE_MISSING: {service}.{key}")
    if value.startswith("${") and value.endswith(":?}"):
        secret_ref = value[2:-3]
        value = str(os.environ.get(secret_ref) or "").strip()
        if not value:
            raise RuntimeError(f"DATA.RELEASE.DATA_PLANE_SECRET_MISSING: {secret_ref}")
    return value


def _legacy_nonprod_target(
    *, environment: DeploymentEnvironment, target_name: str, target: Mapping[str, Any],
    release: Mapping[str, Any], media_delivery_base_url: str, api_base_url: str,
) -> EnvironmentReleaseTarget:
    """Retain Alpha/Beta until their candidate-bound release lane is migrated."""
    profile = str(target.get("portProfile") or "")
    ports = read_json(_PORTS_PATH)
    mongo_port = _local_port(ports, profile, str(release.get("mongoPortRole") or ""))
    postgres_port = _local_port(ports, profile, str(release.get("userPostgresPortRole") or ""))
    redis_port = _local_port(ports, profile, str(release.get("redisPortRole") or ""))
    from quwoquan_ops.cli.lib.output_paths import target_local_dir
    media_ref = Path(str(release.get("mediaLocalRef") or ""))
    if media_ref.is_absolute() or ".." in media_ref.parts:
        raise ValueError("dataRelease mediaLocalRef must remain inside target runtime")
    return EnvironmentReleaseTarget(
        environment, target_name, EnvironmentReleaseMode.LOCAL_IMPORT,
        f"mongodb://127.0.0.1:{mongo_port}/?directConnection=true",
        f"postgres://quwoquan:quwoquan@127.0.0.1:{postgres_port}/quwoquan?sslmode=disable",
        target_local_dir(target_name) / media_ref, media_delivery_base_url, api_base_url, (),
        ssl_cafile=_local_managed_ssl_cafile(target_name), redis_addr=f"127.0.0.1:{redis_port}",
        redis_database=int(release.get("redisDatabase") or 0),
    )


def resolve_environment_release_target(
    env: str,
    *,
    candidate_root: Path | None = None,
) -> EnvironmentReleaseTarget:
    load_environment_topology, get_environment, get_target = _ops_topology_functions()
    environment = DeploymentEnvironment(str(env))
    manifest = load_environment_topology()
    environment_row = get_environment(manifest, environment.value)
    target_name = str(environment_row.get("dataReleaseTarget") or "").strip()
    target = get_target(manifest, target_name)
    release = _mapping(target.get("dataRelease"), label=f"{target_name}.dataRelease")
    mode = EnvironmentReleaseMode(str(release.get("mode") or ""))
    public_bases = _mapping(target.get("publicBases"), label=f"{target_name}.publicBases")
    media_image = urlsplit(str(public_bases.get("mediaImage") or ""))
    media_delivery_base_url = urlunsplit((media_image.scheme, media_image.netloc, "", "", ""))
    api_base_url = str(public_bases.get("api") or "").rstrip("/")
    if mode is EnvironmentReleaseMode.PROJECTION_ONLY:
        return EnvironmentReleaseTarget(environment, target_name, mode, "", "", None, media_delivery_base_url, api_base_url, (), ssl_cafile=_local_managed_ssl_cafile(target_name))
    if environment in {DeploymentEnvironment.ALPHA, DeploymentEnvironment.BETA}:
        return _legacy_nonprod_target(
            environment=environment, target_name=target_name, target=target, release=release,
            media_delivery_base_url=media_delivery_base_url, api_base_url=api_base_url,
        )
    if candidate_root is None:
        raise RuntimeError("DATA.RELEASE.RUNTIME_CANDIDATE_MISSING: --runtime-candidate-root is required")

    canonical, descriptor, binding_raw, candidate_manifest = _candidate_binding(
        candidate_root, environment=environment.value, target_name=target_name
    )
    from quwoquan_ops.cli.lib.data_plane_binding import resolve_data_plane_environment
    # Prod ship is a prevalidation operation: consume the isolated candidate
    # instance identities, never the formal external namespace.
    resolution_mode = (
        "prevalidate"
        if environment is DeploymentEnvironment.PROD
        else "local"
    )
    resolved = resolve_data_plane_environment(
        {"dataPlane": {"resources": canonical["resources"], "bindings": canonical["bindings"]}},
        mode=resolution_mode,
        target_name=target_name,
    )["environment"]
    content = _binding(canonical, "content-service.mongodb", engine="mongodb")
    tag = _binding(canonical, "tag-service.mongodb", engine="mongodb")
    creator = _binding(canonical, "user-service.mongodb", engine="mongodb")
    homepage = _binding(canonical, "entity-service.mongodb", engine="mongodb")
    postgres = _binding(canonical, "user-service.postgres", engine="postgres")
    redis = _binding(canonical, "content-service.redis", engine="redis")
    mongo_uri = _injected(resolved, "content-service", "CONTENT_MONGO_URI")
    user_postgres_dsn = _injected(resolved, "user-service", "USER_POSTGRES_DSN")
    redis_addr = _injected(resolved, "content-service", "CONTENT_REDIS_GENERAL_ADDR")

    resources = _mapping(canonical["resources"], label="canonical resources")
    identity_mode = (
        "prevalidate"
        if environment is DeploymentEnvironment.PROD
        else "local"
    )

    def _resource_identity(binding: Mapping[str, Any], label: str) -> str:
        identity = _mapping(
            resources[binding["resource"]], label=label
        ).get("physicalIdentity")
        if isinstance(identity, Mapping):
            value = str(identity.get(identity_mode) or "").strip()
        else:
            value = str(identity or "").strip()
        if not value:
            raise RuntimeError(
                "DATA.RELEASE.DATA_PLANE_RESOURCE_DRIFT: "
                f"{label} lacks {identity_mode} identity"
            )
        return value

    if mode is EnvironmentReleaseMode.LOCAL_IMPORT:
        profile = str(target.get("portProfile") or "")
        ports = read_json(_PORTS_PATH)
        mongo_role = _resource_identity(content, "content mongo resource")
        postgres_role = _resource_identity(postgres, "creator postgres resource")
        redis_role = _resource_identity(redis, "content redis resource")
        mongo_uri = f"mongodb://127.0.0.1:{_local_port(ports, profile, mongo_role)}/?directConnection=true"
        user_postgres_dsn = f"postgres://quwoquan:quwoquan@127.0.0.1:{_local_port(ports, profile, postgres_role)}/{postgres['namespace']}?sslmode=disable"
        redis_addr = f"127.0.0.1:{_local_port(ports, profile, redis_role)}"
        from quwoquan_ops.cli.lib.output_paths import target_local_dir
        media_sync_root = target_local_dir(target_name) / "cache/media"
    else:
        mongo_uri = f"mongodb://{_resource_identity(content, 'content mongo resource')}:27017/?directConnection=true"
        user_postgres_dsn = (
            "postgres://quwoquan:quwoquan@"
            f"{_resource_identity(postgres, 'creator postgres resource')}:5432/"
            f"{postgres['namespace']}?sslmode=disable"
        )
        redis_addr = f"{_resource_identity(redis, 'content redis resource')}:6379"
        # Hosted media location is a topology coordinate, never a dataRelease env-name authority.
        access_path = REPO_ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml"
        access = yaml.safe_load(access_path.read_text(encoding="utf-8"))
        planes = access.get("planes") if isinstance(access, Mapping) else None
        service = next((row for row in planes or [] if isinstance(row, Mapping) and row.get("plane") == "service"), None)
        layout = service.get("rootlessRuntimeLayout") if isinstance(service, Mapping) else None
        compose_root = str(service.get("composeProjectRoot") or "") if isinstance(service, Mapping) else ""
        media_ref = str(layout.get("mediaStateRef") or "") if isinstance(layout, Mapping) else ""
        if not compose_root.startswith("/") or Path(media_ref).is_absolute() or ".." in Path(media_ref).parts or not media_ref:
            raise RuntimeError("DATA.RELEASE.DATA_PLANE_MEDIA_TOPOLOGY_INVALID: hosted media root is not canonical")
        media_sync_root = Path(compose_root) / "state/prod/r0" / media_ref

    post_safety = _post_safety_import_projection(
        candidate_root.expanduser().absolute(), environment=environment.value,
        target_name=target_name, candidate_manifest=candidate_manifest,
        binding_digest=descriptor["bindingDigest"],
    )
    if environment is DeploymentEnvironment.GAMMA:
        from quwoquan_ops.cli.lib import output_paths
        runtime_auth_env_ref = output_paths.deployment_target_path(
            target_name, "secrets", "auth.env"
        )
        authority_base_url = (
            f"http://127.0.0.1:{_local_port(read_json(_PORTS_PATH), profile, 'user-service')}"
        )
        runtime_auth_issuer = f"quwoquan.{environment.value}.local"
    else:
        from quwoquan_ops.cli.lib import output_paths
        runtime_auth_env_ref = output_paths.deployment_target_path(
            target_name, "secrets", "prevalidation-auth.env"
        )
        authority_base_url = "http://user-service:18081"
        runtime_auth_issuer = "quwoquan.prod-hosted.prevalidation"

    importer_image = post_safety[4]
    try:
        candidate_image = str(json.loads(
            (candidate_root.expanduser().absolute() / "packages/runtime-shared/oci-images.json").read_bytes()
        )["images"]["service-core"]["ref"])
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"DATA.RELEASE.CONTENT_IMPORTER_IMAGE_INVALID: {exc}") from exc
    if not importer_image or importer_image != candidate_image:
        raise RuntimeError(
            "DATA.RELEASE.CONTENT_IMPORTER_IMAGE_INVALID: startup/candidate image differs"
        )

    return EnvironmentReleaseTarget(
        environment=environment,
        target_name=target_name,
        mode=mode,
        mongo_uri=mongo_uri,
        user_postgres_dsn=user_postgres_dsn,
        media_sync_root=media_sync_root,
        media_delivery_base_url=media_delivery_base_url,
        api_base_url=api_base_url,
        missing_requirements=(),
        ssl_cafile=_local_managed_ssl_cafile(target_name),
        redis_addr=redis_addr,
        redis_database=0,
        binding_digest=descriptor["bindingDigest"],
        binding_artifact_digest=descriptor["digest"],
        binding_artifact_path=candidate_root.expanduser().absolute() / descriptor["ref"],
        tag_mongo_database=str(tag["namespace"]),
        creator_mongo_database=str(creator["namespace"]),
        homepage_mongo_database=str(homepage["namespace"]),
        content_mongo_database=str(content["namespace"]),
        creator_postgres_database=str(postgres["namespace"]),
        content_redis_namespace=str(redis["namespace"]),
        post_safety_material_root=post_safety[0],
        post_safety_current_binding_ref=post_safety[1],
        post_safety_recovery_evidence_ref=post_safety[2],
        post_safety_hmac_secret_ref=post_safety[3],
        runtime_auth_env_ref=runtime_auth_env_ref,
        runtime_auth_issuer=runtime_auth_issuer,
        runtime_auth_audience="quwoquan-app",
        runtime_auth_token_version="1",
        account_security_authority_base_url=authority_base_url,
        account_security_authority_timeout_ms=300,
        content_importer_image_ref=importer_image,
    )


def assert_environment_release_target_unchanged(target: EnvironmentReleaseTarget) -> None:
    """Revalidate active candidate bytes while the ship operation lock is held."""
    if target.binding_artifact_path is None:
        raise RuntimeError("DATA.RELEASE.DATA_PLANE_BINDING_MISSING: target has no candidate artifact")
    raw = target.binding_artifact_path.read_bytes()
    actual = "sha256:" + hashlib.sha256(raw).hexdigest()
    if actual != target.binding_artifact_digest:
        raise RuntimeError("DATA.RELEASE.DATA_PLANE_BINDING_CAS_DRIFT: exact artifact changed under lock")
    from quwoquan_ops.cli.lib.data_plane_binding import validate_canonical_data_plane_binding
    canonical = validate_canonical_data_plane_binding(json.loads(raw))
    if canonical["bindingDigest"] != target.binding_digest:
        raise RuntimeError("DATA.RELEASE.DATA_PLANE_BINDING_CAS_DRIFT: bindingDigest changed under lock")


__all__ = [
    "EnvironmentReleaseMode",
    "EnvironmentReleaseTarget",
    "resolve_environment_release_target",
    "assert_environment_release_target_unchanged",
    "resolve_media_cdn_bases",
]
