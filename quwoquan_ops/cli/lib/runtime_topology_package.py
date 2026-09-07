from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, Mapping
import yaml
import sys
sys.dont_write_bytecode = True
from quwoquan_ops.cli.lib.data_plane_binding import (
    DataPlaneBindingError,
    DATA_PLANE_BINDING_PACKAGE_REF,
    materialize_data_plane_binding_package,
    resolve_data_plane_environment,
    validate_canonical_data_plane_binding,
)
from quwoquan_ops.cli.lib.immutable_image_composition import first_party_service_names
from quwoquan_ops.cli.lib.deployment_candidate_manifest.log_sink_package import (
    canonical_local_observability_log_sink_composition,
)
from quwoquan_ops.cli.lib.service_core_composition import (
    SERVICE_CORE_MODULE_SET,
    SERVICE_CORE_MODULES,
    SERVICE_CORE_WORKLOAD,
    project_compose_document,
)
ROOT = Path(__file__).resolve().parents[3]
SCHEMA = "qwq.runtime_topology_package.v4"
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
TOPOLOGY_RELATIVE_ROOT = PurePosixPath(
    "packages/runtime-shared/runtime-topology"
)
_RUNTIME_TOPOLOGY_LOAD_PURPOSES = frozenset(
    {"self_verify", "teardown", "currentness"}
)
CONTENT_RELEASE_SERVICES = frozenset(
    {
        "api-edge",
        "recommendation-service",
        "content-service",
        "user-service",
        "entity-service",
        "search-service",
    }
)
CONTENT_COMMERCIAL_SERVICES = frozenset(
    {*CONTENT_RELEASE_SERVICES, "product-ops-service"}
)
FULL_WORKLOAD_COMPOSE_PROFILES = frozenset(
    {
        "assistant-runtime",
        "commercial-observability",
        "control-plane",
        "edge-media",
    }
)
CONTENT_COMMERCIAL_COMPOSE_PROFILES = frozenset({"commercial-observability"})
OBSERVABILITY_ALERT_POLICY_SOURCE = PurePosixPath(
    "quwoquan_ops/observability/elasticsearch/product_telemetry_alerts.yaml"
)
_ALERT_POLICY_PACKAGE_REF = PurePosixPath(
    "policies/product_telemetry_alerts.yaml"
)
_SEALED_BIND_SOURCES: dict[str, str] = {
    OBSERVABILITY_ALERT_POLICY_SOURCE.as_posix(): (
        "./" + _ALERT_POLICY_PACKAGE_REF.as_posix()
    ),
}
_BOUNDED_SEARCH_ELASTICSEARCH_REF = PurePosixPath(
    "dependencies/search/elasticsearch.compose.yaml"
)


_PRODUCT_OPS_SERVICE = "product-ops-service"
_PRODUCT_OPS_BOOTSTRAP_SERVICE = "product-ops-service-migrate-elasticsearch"
_PRODUCT_OPS_BOOTSTRAP_COMMAND = "product-ops-elasticsearch-bootstrap"
_PRODUCT_OPS_ADMIN_BINDING = "deployment-control.telemetry.admin"
_PRODUCT_OPS_ADMIN_ENDPOINT = "PRODUCT_OPS_ELASTICSEARCH_ADMIN_ENDPOINT"
_PRODUCT_OPS_ADMIN_CREDENTIAL_ENV = "PRODUCT_OPS_ELASTICSEARCH_ADMIN_API_KEY"
_PRODUCT_OPS_BOOTSTRAP_INDEX_KEYS = frozenset(
    {
        "PRODUCT_OPS_TELEMETRY_ELASTICSEARCH_RAW_INDEX",
        "PRODUCT_OPS_TELEMETRY_ELASTICSEARCH_STARTUP_DIAGNOSTIC_INDEX",
        "PRODUCT_OPS_TELEMETRY_ELASTICSEARCH_AGGREGATE_INDEX",
        "PRODUCT_OPS_RUNTIME_LOG_ELASTICSEARCH_RAW_INDEX",
        "PRODUCT_OPS_RUNTIME_LOG_ELASTICSEARCH_AGGREGATE_INDEX",
    }
)
class RuntimeTopologyPackageError(ValueError):
    """The runtime topology package is missing, unsafe, or internally drifted."""
def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()
def _canonical_json(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
def _safe_source_bytes(path: Path, *, label: str) -> bytes:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise RuntimeTopologyPackageError(f"{label} is unavailable: {path}") from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise RuntimeTopologyPackageError(f"{label} must be a regular file: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise RuntimeTopologyPackageError(f"{label} is unreadable: {path}") from exc
def _sealed_compose_bytes(
    source: Path,
    *,
    data_plane_service: str = "",
    data_plane_environment: Mapping[str, str] | None = None,
    data_plane_bindings: tuple[Mapping[str, Any], ...] = (),
    postgres_namespaces: tuple[str, ...] | None = None,
    product_ops_bootstrap_environment: Mapping[str, str] | None = None,
) -> tuple[bytes, str]:
    source_bytes = _safe_source_bytes(source, label="runtime Compose source")
    try:
        compose = yaml.safe_load(source_bytes.decode("utf-8"))
    except (UnicodeError, yaml.YAMLError) as exc:
        raise RuntimeTopologyPackageError(
            f"runtime Compose source is invalid: {source}"
        ) from exc
    if not isinstance(compose, dict):
        raise RuntimeTopologyPackageError(
            f"runtime Compose source must be an object: {source}"
        )
    services = compose.get("services")
    if not isinstance(services, dict) or not services:
        raise RuntimeTopologyPackageError(
            f"runtime Compose source has no services: {source}"
        )
    for service_name, service in services.items():
        if not isinstance(service_name, str) or not isinstance(service, dict):
            raise RuntimeTopologyPackageError(
                f"runtime Compose service is invalid: {source}"
            )
        service.pop("build", None)
        _seal_relative_bind_mounts(service, source=source)
    if postgres_namespaces is not None:
        if not postgres_namespaces:
            raise RuntimeTopologyPackageError(
                "runtime topology requires at least one postgres namespace"
            )
        postgres_init = services.get("postgres-init")
        if not isinstance(postgres_init, dict):
            raise RuntimeTopologyPackageError(
                "runtime Compose postgres-init service is missing"
            )
        init_environment = postgres_init.get("environment")
        if not isinstance(init_environment, Mapping):
            raise RuntimeTopologyPackageError(
                "runtime Compose postgres-init environment is invalid"
            )
        postgres_init["environment"] = {
            **dict(init_environment),
            "QWQ_POSTGRES_DATABASES": " ".join(postgres_namespaces),
        }
    if data_plane_environment:
        definition = services.get(data_plane_service)
        if not isinstance(definition, dict):
            raise RuntimeTopologyPackageError(
                f"runtime Compose data-plane service is missing: {data_plane_service}"
            )
        environment = definition.get("environment")
        if environment is None:
            environment = {}
        if not isinstance(environment, Mapping):
            raise RuntimeTopologyPackageError(
                f"runtime Compose service environment is invalid: {data_plane_service}"
            )
        definition["environment"] = {
            **dict(environment),
            **dict(data_plane_environment),
        }
        if any(binding["engine"] == "postgres" for binding in data_plane_bindings):
            _inject_service_dependency(
                definition,
                dependency="postgres-init",
                service=data_plane_service,
            )
    if product_ops_bootstrap_environment is not None:
        _project_product_ops_elasticsearch_bootstrap(
            services,
            product_ops_bootstrap_environment,
        )
    compose = project_compose_document(compose)
    encoded = yaml.safe_dump(
        compose,
        allow_unicode=True,
        sort_keys=False,
    ).encode("utf-8")
    return encoded, _sha256_bytes(source_bytes)
def _inject_service_dependency(
    definition: dict[str, Any],
    *,
    dependency: str,
    service: str,
) -> None:
    dependencies = definition.get("depends_on")
    if dependencies is None:
        dependencies = {}
    if not isinstance(dependencies, Mapping):
        raise RuntimeTopologyPackageError(
            f"runtime Compose service dependencies are invalid: {service}"
        )
    definition["depends_on"] = {
        **dict(dependencies),
        dependency: {"condition": "service_completed_successfully"},
    }


def _product_ops_bootstrap_environment(
    data_plane_projection: Mapping[str, Any],
) -> dict[str, str] | None:
    deployment_environments = data_plane_projection.get("deploymentEnvironment")
    service_environments = data_plane_projection.get("environment")
    if not isinstance(deployment_environments, Mapping) or not isinstance(
        service_environments, Mapping
    ):
        raise RuntimeTopologyPackageError(
            "runtime topology data-plane environments are invalid"
        )
    raw_admin = deployment_environments.get(_PRODUCT_OPS_ADMIN_BINDING)
    if raw_admin is None:
        return None
    if not isinstance(raw_admin, Mapping):
        raise RuntimeTopologyPackageError(
            "Product Ops Elasticsearch admin binding is invalid"
        )
    endpoint = str(raw_admin.get("endpoint") or "").strip()
    credential = str(raw_admin.get("credential") or "").strip()
    if not endpoint or not credential:
        raise RuntimeTopologyPackageError(
            "Product Ops Elasticsearch admin binding is incomplete"
        )
    raw_owner = service_environments.get(_PRODUCT_OPS_SERVICE)
    if not isinstance(raw_owner, Mapping):
        raise RuntimeTopologyPackageError(
            "Product Ops Elasticsearch owner environment is missing"
        )
    index_environment = {
        str(key): str(value).strip()
        for key, value in raw_owner.items()
        if str(key).endswith("_INDEX") and str(value).strip()
    }
    if set(index_environment) != _PRODUCT_OPS_BOOTSTRAP_INDEX_KEYS:
        raise RuntimeTopologyPackageError(
            "Product Ops Elasticsearch bootstrap index binding is incomplete"
        )
    return {
        _PRODUCT_OPS_ADMIN_ENDPOINT: endpoint,
        _PRODUCT_OPS_ADMIN_CREDENTIAL_ENV: credential,
        **index_environment,
    }


def _project_product_ops_elasticsearch_bootstrap(
    services: dict[str, Any],
    environment: Mapping[str, str],
) -> None:
    bootstrap = services.get(_PRODUCT_OPS_BOOTSTRAP_SERVICE)
    owner = services.get(_PRODUCT_OPS_SERVICE)
    if not isinstance(bootstrap, dict) or not isinstance(owner, dict):
        raise RuntimeTopologyPackageError(
            "Product Ops Elasticsearch bootstrap service closure is missing"
        )
    command = bootstrap.get("command")
    if command != [_PRODUCT_OPS_BOOTSTRAP_COMMAND]:
        raise RuntimeTopologyPackageError(
            "Product Ops Elasticsearch bootstrap command drifted"
        )
    expected_keys = {
        _PRODUCT_OPS_ADMIN_ENDPOINT,
        _PRODUCT_OPS_ADMIN_CREDENTIAL_ENV,
        *_PRODUCT_OPS_BOOTSTRAP_INDEX_KEYS,
    }
    if set(environment) != expected_keys or any(
        not str(value).strip() for value in environment.values()
    ):
        raise RuntimeTopologyPackageError(
            "Product Ops Elasticsearch bootstrap environment is incomplete"
        )
    bootstrap["environment"] = dict(environment)
    _inject_service_dependency(
        owner,
        dependency=_PRODUCT_OPS_BOOTSTRAP_SERVICE,
        service=_PRODUCT_OPS_SERVICE,
    )
    owner_environment = owner.get("environment")
    if not isinstance(owner_environment, Mapping):
        raise RuntimeTopologyPackageError(
            "Product Ops service environment is invalid"
        )
    if (
        _PRODUCT_OPS_ADMIN_ENDPOINT in owner_environment
        or _PRODUCT_OPS_ADMIN_CREDENTIAL_ENV in owner_environment
    ):
        raise RuntimeTopologyPackageError(
            "Product Ops deployment admin credential leaked into the long-running service"
        )


def _seal_relative_bind_mounts(service: dict[str, Any], *, source: Path) -> None:
    """Rewrite declared relative bind sources to package-owned copies."""
    volumes = service.get("volumes")
    if not isinstance(volumes, list):
        return
    for index, volume in enumerate(volumes):
        if not isinstance(volume, str):
            continue
        host, separator, container = volume.partition(":")
        if not separator or not host.startswith(("./", "../")):
            continue
        normalized = os.path.normpath(host)
        replacement = next(
            (
                sealed
                for declared, sealed in _SEALED_BIND_SOURCES.items()
                if normalized == declared or normalized.endswith("/" + declared)
            ),
            None,
        )
        if replacement is None:
            raise RuntimeTopologyPackageError(
                "runtime Compose relative bind mount escapes the immutable "
                f"candidate: {host} ({source})"
            )
        volumes[index] = replacement + ":" + container


def bounded_search_elasticsearch_compose_bytes(
    repo_root: Path = ROOT,
) -> tuple[bytes, str]:
    """Project shared local Elasticsearch bytes into a Search-owned slice.

    本地 CJK Elasticsearch 的镜像/JVM 平台选择仍复用既有 package authority；
    bounded content-release 只封装其 ``elasticsearch`` service，并改用 Search
    数据面命名。Product Ops service、遥测策略与 promotion readiness 不得借由
    这份依赖投影进入 M1 consumer runtime。
    """

    source = (
        repo_root
        / "quwoquan_service/services/product-ops-service/deploy"
        / "local-elasticsearch.compose.yaml"
    )
    canonical = canonical_local_observability_log_sink_composition(source)
    raw_compose = canonical.get("compose")
    compose = json.loads(json.dumps(raw_compose)) if isinstance(raw_compose, dict) else None
    services = compose.get("services") if isinstance(compose, dict) else None
    elasticsearch = services.get("elasticsearch") if isinstance(services, dict) else None
    if not isinstance(compose, dict) or not isinstance(elasticsearch, dict):
        raise RuntimeTopologyPackageError(
            "bounded Search Elasticsearch source is incomplete"
        )

    volumes = elasticsearch.get("volumes")
    if not isinstance(volumes, list):
        raise RuntimeTopologyPackageError(
            "bounded Search Elasticsearch data volume is missing"
        )
    source_volume = "product-ops-elasticsearch-data"
    search_volume = "bounded-search-elasticsearch-data"
    rewritten_volumes: list[object] = []
    for volume in volumes:
        if isinstance(volume, str) and volume.startswith(source_volume + ":"):
            rewritten_volumes.append(search_volume + volume[len(source_volume) :])
        else:
            rewritten_volumes.append(volume)
    elasticsearch["volumes"] = rewritten_volumes
    environment = elasticsearch.get("environment")
    if not isinstance(environment, dict):
        raise RuntimeTopologyPackageError(
            "bounded Search Elasticsearch environment is missing"
        )
    environment["cluster.name"] = (
        "quwoquan-${QWQ_LOCAL_RELEASE_TARGET:?QWQ_LOCAL_RELEASE_TARGET is required}-search"
    )
    environment["node.name"] = (
        "${QWQ_LOCAL_RELEASE_TARGET:?QWQ_LOCAL_RELEASE_TARGET is required}-search-0"
    )
    compose["services"] = {"elasticsearch": elasticsearch}
    compose["volumes"] = {search_volume: None}
    encoded = yaml.safe_dump(
        project_compose_document(compose),
        allow_unicode=True,
        sort_keys=False,
    ).encode("utf-8")
    if "product-ops" in encoded.decode("utf-8"):
        raise RuntimeTopologyPackageError(
            "bounded Search Elasticsearch projection retained Product Ops ownership"
        )
    return encoded, str(canonical["sourceComposeDigest"])


def materialize_bounded_search_elasticsearch_compose(
    destination: Path,
    *,
    repo_root: Path = ROOT,
) -> str:
    """Write one build-only execution copy of the bounded Search dependency."""

    encoded, source_digest = bounded_search_elasticsearch_compose_bytes(repo_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(encoded)
    return source_digest


def _validate_relative(relative: PurePosixPath, *, label: str) -> None:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise RuntimeTopologyPackageError(f"{label} path is unsafe")


def _ensure_safe_directory(root: Path, relative: PurePosixPath) -> Path:
    _validate_relative(relative, label="runtime topology directory")
    current = root
    for part in relative.parts:
        current = current / part
        if current.exists() or current.is_symlink():
            metadata = current.lstat()
            if current.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
                raise RuntimeTopologyPackageError(
                    f"runtime topology directory is unsafe: {current}"
                )
        else:
            current.mkdir(mode=0o700)
    return current


def _write_exclusive(root: Path, relative: PurePosixPath, payload: bytes) -> None:
    _validate_relative(relative, label="runtime topology artifact")
    parent_relative = PurePosixPath(*relative.parts[:-1])
    parent = (
        _ensure_safe_directory(root, parent_relative)
        if parent_relative.parts
        else root
    )
    destination = parent / relative.name
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(destination, flags, 0o600)
    except OSError as exc:
        raise RuntimeTopologyPackageError(
            f"runtime topology artifact cannot be created safely: {destination}"
        ) from exc
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short runtime topology write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    parent_descriptor = os.open(
        parent,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    try:
        os.fsync(parent_descriptor)
    finally:
        os.close(parent_descriptor)


def _entry(
    *,
    role: str,
    layer: str,
    service: str,
    reference: PurePosixPath,
    payload: bytes,
    source_digest: str,
) -> dict[str, str]:
    return {
        "role": role,
        "layer": layer,
        "service": service,
        "ref": reference.as_posix(),
        "digest": _sha256_bytes(payload),
        "sourceDigest": source_digest,
    }


def materialize_runtime_topology_package(
    environment: str,
    target: str,
    runtime_shared_root: Path,
    *,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    if environment not in {"alpha", "beta", "gamma"}:
        raise RuntimeTopologyPackageError(
            "runtime topology package supports alpha, beta, and gamma only"
        )
    if target != f"{environment}-local":
        raise RuntimeTopologyPackageError(
            "runtime topology target does not match environment"
        )
    root = runtime_shared_root
    try:
        root_metadata = root.lstat()
    except OSError as exc:
        raise RuntimeTopologyPackageError(
            "runtime-shared package root is unavailable"
        ) from exc
    if root.is_symlink() or not stat.S_ISDIR(root_metadata.st_mode):
        raise RuntimeTopologyPackageError("runtime-shared package root is unsafe")

    data_plane_path = root / DATA_PLANE_BINDING_PACKAGE_REF.name
    if not data_plane_path.exists() and not data_plane_path.is_symlink():
        materialize_data_plane_binding_package(
            environment,
            target,
            root,
            repo_root=repo_root,
        )
    data_plane_bytes = _safe_source_bytes(
        data_plane_path,
        label="packaged data-plane binding",
    )
    try:
        data_plane_payload = validate_canonical_data_plane_binding(
            json.loads(data_plane_bytes.decode("utf-8"))
        )
        data_plane_projection = resolve_data_plane_environment(
            {
                "dataPlane": {
                    "resources": data_plane_payload["resources"],
                    "bindings": data_plane_payload["bindings"],
                }
            },
            mode="local",
            target_name=target,
        )
    except (UnicodeError, json.JSONDecodeError, DataPlaneBindingError) as exc:
        raise RuntimeTopologyPackageError(
            "packaged data-plane binding is invalid"
        ) from exc
    if not data_plane_payload["bindings"]:
        raise RuntimeTopologyPackageError(
            f"{target} data-plane binding cannot be empty"
        )
    if data_plane_projection["bindingDigest"] != data_plane_payload["bindingDigest"]:
        raise RuntimeTopologyPackageError(
            "packaged data-plane binding projection digest drifted"
        )
    data_plane_environments = data_plane_projection["environment"]
    product_ops_bootstrap_environment = _product_ops_bootstrap_environment(
        data_plane_projection
    )
    bindings_by_service: dict[str, tuple[Mapping[str, Any], ...]] = {}
    for binding in data_plane_payload["bindings"].values():
        service = binding["service"]
        bindings_by_service[service] = (
            *bindings_by_service.get(service, ()),
            binding,
        )
    postgres_namespaces = tuple(
        sorted(
            {
                binding["namespace"]
                for binding in data_plane_payload["bindings"].values()
                if binding["engine"] == "postgres" and binding["required"] is True
            }
        )
    )
    if not postgres_namespaces:
        raise RuntimeTopologyPackageError(
            f"{target} data-plane binding has no required postgres namespace"
        )
    data_plane_binding = {
        "ref": DATA_PLANE_BINDING_PACKAGE_REF.as_posix(),
        "digest": _sha256_bytes(data_plane_bytes),
        "bindingDigest": data_plane_payload["bindingDigest"],
    }

    output_prefix = PurePosixPath("runtime-topology")
    output_root = root / output_prefix
    if output_root.exists() or output_root.is_symlink():
        raise RuntimeTopologyPackageError(
            "runtime topology package already exists"
        )
    entries: list[dict[str, str]] = []

    def add_compose(
        source: Path,
        relative: PurePosixPath,
        *,
        role: str,
        layer: str,
        service: str = "",
        data_plane_service: str = "",
        seal_postgres_namespaces: bool = False,
    ) -> None:
        binding_service = data_plane_service or service
        binding_environment = (
            data_plane_environments.get(binding_service, {})
            if binding_service and layer == "base"
            else {}
        )
        encoded, source_digest = _sealed_compose_bytes(
            source,
            data_plane_service=binding_service,
            data_plane_environment=binding_environment,
            data_plane_bindings=bindings_by_service.get(binding_service, ()),
            postgres_namespaces=(
                postgres_namespaces if seal_postgres_namespaces else None
            ),
            product_ops_bootstrap_environment=(
                product_ops_bootstrap_environment
                if binding_service == _PRODUCT_OPS_SERVICE and layer == "base"
                else None
            ),
        )
        _write_exclusive(root, output_prefix / relative, encoded)
        entries.append(
            _entry(
                role=role,
                layer=layer,
                service=service,
                reference=TOPOLOGY_RELATIVE_ROOT / relative,
                payload=encoded,
                source_digest=source_digest,
            )
        )

    add_compose(
        repo_root
        / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml",
        PurePosixPath("base.compose.yaml"),
        role="ops-base",
        layer="base",
        seal_postgres_namespaces=True,
    )
    services_root = repo_root / "quwoquan_service/services"
    try:
        service_directories = sorted(services_root.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        raise RuntimeTopologyPackageError(
            "first-party service tree is unavailable"
        ) from exc
    active_services = set(first_party_service_names(repo_root))
    unknown_binding_services = sorted(set(data_plane_environments) - active_services)
    if unknown_binding_services:
        raise RuntimeTopologyPackageError(
            "data-plane binding projects services outside the runtime topology: "
            f"{unknown_binding_services}"
        )
    service_names: list[str] = []
    for service_root in service_directories:
        service = service_root.name
        if service not in active_services:
            continue
        if service_root.is_symlink():
            raise RuntimeTopologyPackageError(
                f"first-party service directory is unsafe: {service_root}"
            )
        try:
            service_metadata = service_root.lstat()
        except OSError as exc:
            raise RuntimeTopologyPackageError(
                f"first-party service directory is unavailable: {service_root}"
            ) from exc
        if not stat.S_ISDIR(service_metadata.st_mode):
            continue
        base_source = service_root / "deploy/compose.yaml"
        if not base_source.exists():
            continue
        service_names.append(service)
        add_compose(
            base_source,
            PurePosixPath("services", service, "base.compose.yaml"),
            role="service",
            layer="base",
            service=service,
        )
        environment_source = (
            service_root
            / "environments"
            / environment
            / "deploy/compose.yaml"
        )
        if environment_source.exists() or environment_source.is_symlink():
            add_compose(
                environment_source,
                PurePosixPath("services", service, "environment.compose.yaml"),
                role="service",
                layer="environment",
                service=service,
            )

    if not service_names:
        raise RuntimeTopologyPackageError(
            "runtime topology package has no first-party services"
        )
    if "search-service" in service_names:
        search_elasticsearch_bytes, search_elasticsearch_source_digest = (
            bounded_search_elasticsearch_compose_bytes(repo_root)
        )
        _write_exclusive(
            root,
            output_prefix / _BOUNDED_SEARCH_ELASTICSEARCH_REF,
            search_elasticsearch_bytes,
        )
        entries.append(
            _entry(
                role="bounded-dependency",
                layer="base",
                service="search-service",
                reference=(
                    TOPOLOGY_RELATIVE_ROOT / _BOUNDED_SEARCH_ELASTICSEARCH_REF
                ),
                payload=search_elasticsearch_bytes,
                source_digest=search_elasticsearch_source_digest,
            )
        )
    add_compose(
        repo_root
        / "quwoquan_service/control-plane/platform-ops/deploy/compose.yaml",
        PurePosixPath("control-plane/platform-ops.compose.yaml"),
        role="control-plane",
        layer="base",
        data_plane_service="platform-ops-service",
    )

    policy_source = (
        repo_root
        / "quwoquan_service/services/content-service/resources/policies/content/post/recommendation_policy.yaml"
    )
    policy_bytes = _safe_source_bytes(
        policy_source,
        label="recommendation policy source",
    )
    policy_relative = output_prefix / PurePosixPath(
        "policies/recommendation_policy.yaml"
    )
    _write_exclusive(root, policy_relative, policy_bytes)
    policy = {
        "ref": (
            TOPOLOGY_RELATIVE_ROOT / "policies/recommendation_policy.yaml"
        ).as_posix(),
        "digest": _sha256_bytes(policy_bytes),
    }
    alert_policy_bytes = _safe_source_bytes(
        repo_root / OBSERVABILITY_ALERT_POLICY_SOURCE.as_posix(),
        label="telemetry alert policy source",
    )
    _write_exclusive(
        root,
        output_prefix / _ALERT_POLICY_PACKAGE_REF,
        alert_policy_bytes,
    )
    observability_policy = {
        "ref": (TOPOLOGY_RELATIVE_ROOT / _ALERT_POLICY_PACKAGE_REF).as_posix(),
        "digest": _sha256_bytes(alert_policy_bytes),
    }
    runtime_service_names = sorted(
        (set(service_names) - SERVICE_CORE_MODULE_SET) | {SERVICE_CORE_WORKLOAD}
    )
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "quwoquan-runtime",
                "version": target,
            }
        },
        "components": [
            {
                "type": "application",
                "name": service,
                "version": "candidate-bound",
                **(
                    {
                        "properties": [
                            {
                                "name": "quwoquan.service-core.modules",
                                "value": ",".join(SERVICE_CORE_MODULES),
                            }
                        ]
                    }
                    if service == SERVICE_CORE_WORKLOAD
                    else {}
                ),
            }
            for service in runtime_service_names
        ],
    }
    sbom_bytes = (
        json.dumps(sbom, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    sbom_relative = output_prefix / "service-core.sbom.cdx.json"
    _write_exclusive(root, sbom_relative, sbom_bytes)
    composition_sbom = {
        "ref": (
            TOPOLOGY_RELATIVE_ROOT / "service-core.sbom.cdx.json"
        ).as_posix(),
        "digest": _sha256_bytes(sbom_bytes),
    }
    identity = {
        "compose": entries,
        "policy": policy,
        "observabilityPolicy": observability_policy,
        "serviceNames": service_names,
        "runtimeServiceNames": runtime_service_names,
        "serviceCoreModules": list(SERVICE_CORE_MODULES),
        "compositionSbom": composition_sbom,
        "dataPlaneBinding": data_plane_binding,
    }
    manifest = {
        "schema": SCHEMA,
        "environment": environment,
        "target": target,
        **identity,
        "topologyDigest": _sha256_bytes(_canonical_json(identity)),
    }
    _write_exclusive(
        root,
        output_prefix / "manifest.json",
        (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        ),
    )
    return manifest


def _open_directory(parent_descriptor: int, name: str) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    return os.open(name, flags, dir_fd=parent_descriptor)


def _read_candidate_bytes(
    candidate_root: Path,
    relative: PurePosixPath,
    *,
    label: str,
) -> bytes:
    _validate_relative(relative, label=label)
    root_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    root_flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(candidate_root, root_flags)
    except OSError as exc:
        raise RuntimeTopologyPackageError(
            "runtime candidate root is unsafe"
        ) from exc
    try:
        for part in relative.parts[:-1]:
            child = _open_directory(descriptor, part)
            os.close(descriptor)
            descriptor = child
        file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        file_descriptor = os.open(
            relative.parts[-1],
            file_flags,
            dir_fd=descriptor,
        )
        try:
            metadata = os.fstat(file_descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise RuntimeTopologyPackageError(
                    f"{label} must be a regular file"
                )
            chunks: list[bytes] = []
            while True:
                chunk = os.read(file_descriptor, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            os.close(file_descriptor)
    except OSError as exc:
        raise RuntimeTopologyPackageError(f"{label} is unsafe or missing") from exc
    finally:
        os.close(descriptor)


def _artifact_relative(value: object, *, label: str) -> PurePosixPath:
    text = str(value or "").strip()
    relative = PurePosixPath(text)
    _validate_relative(relative, label=label)
    if not relative.is_relative_to(TOPOLOGY_RELATIVE_ROOT):
        raise RuntimeTopologyPackageError(f"{label} escaped runtime topology")
    return relative


def _load_data_plane_binding_artifact(
    candidate_root: Path,
    identity: Mapping[str, Any],
    *,
    target: str,
    purpose: str,
) -> tuple[PurePosixPath, dict[str, Any]]:
    reference = PurePosixPath(str(identity.get("ref") or ""))
    _validate_relative(
        reference,
        label="runtime topology data-plane binding artifact",
    )
    if reference != DATA_PLANE_BINDING_PACKAGE_REF:
        raise RuntimeTopologyPackageError(
            "runtime topology data-plane binding artifact ref mismatch"
        )
    encoded = _read_candidate_bytes(
        candidate_root,
        reference,
        label="runtime topology data-plane binding artifact",
    )
    if identity.get("digest") != _sha256_bytes(encoded):
        raise RuntimeTopologyPackageError(
            "runtime topology data-plane binding artifact drifted"
        )
    try:
        payload = validate_canonical_data_plane_binding(
            json.loads(encoded.decode("utf-8"))
        )
        if target == "gamma-local" and not payload["bindings"]:
            raise DataPlaneBindingError("gamma-local data-plane binding cannot be empty")
    except (UnicodeError, json.JSONDecodeError, DataPlaneBindingError) as exc:
        raise RuntimeTopologyPackageError(
            "runtime topology data-plane binding is invalid"
        ) from exc
    if identity.get("bindingDigest") != payload["bindingDigest"]:
        raise RuntimeTopologyPackageError(
            "runtime topology data-plane binding digest drifted"
        )
    return reference, payload


def load_runtime_topology_package(
    candidate_root: Path,
    *,
    environment: str,
    target: str,
    workload: str,
    purpose: str = "self_verify",
) -> dict[str, Any]:
    if purpose not in _RUNTIME_TOPOLOGY_LOAD_PURPOSES:
        raise RuntimeTopologyPackageError(
            "runtime topology load purpose is invalid"
        )
    try:
        manifest = json.loads(
            _read_candidate_bytes(
                candidate_root,
                TOPOLOGY_RELATIVE_ROOT / "manifest.json",
                label="runtime topology manifest",
            ).decode("utf-8")
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeTopologyPackageError(
            "runtime topology manifest is unreadable"
        ) from exc
    required = {
        "schema",
        "environment",
        "target",
        "compose",
        "policy",
        "observabilityPolicy",
        "serviceNames",
        "runtimeServiceNames",
        "serviceCoreModules",
        "compositionSbom",
        "dataPlaneBinding",
        "topologyDigest",
    }
    if not isinstance(manifest, dict) or set(manifest) != required:
        raise RuntimeTopologyPackageError("runtime topology manifest fields mismatch")
    if (
        manifest.get("schema") != SCHEMA
        or manifest.get("environment") != environment
        or manifest.get("target") != target
    ):
        raise RuntimeTopologyPackageError("runtime topology identity mismatch")
    service_names = manifest.get("serviceNames")
    if (
        not isinstance(service_names, list)
        or not service_names
        or any(not isinstance(item, str) or not item for item in service_names)
        or service_names != sorted(set(service_names))
    ):
        raise RuntimeTopologyPackageError("runtime topology service closure is invalid")
    runtime_service_names = manifest.get("runtimeServiceNames")
    service_core_modules = manifest.get("serviceCoreModules")
    composition_sbom = manifest.get("compositionSbom")
    data_plane_binding = manifest.get("dataPlaneBinding")
    expected_runtime_services = sorted(
        (set(service_names) - SERVICE_CORE_MODULE_SET) | {SERVICE_CORE_WORKLOAD}
    )
    if (
        runtime_service_names != expected_runtime_services
        or service_core_modules != list(SERVICE_CORE_MODULES)
        or not SERVICE_CORE_MODULE_SET.issubset(service_names)
    ):
        raise RuntimeTopologyPackageError(
            "runtime topology service-core composition is invalid"
        )
    if not isinstance(composition_sbom, dict) or set(composition_sbom) != {
        "ref",
        "digest",
    }:
        raise RuntimeTopologyPackageError(
            "runtime topology composition SBOM identity is invalid"
        )
    if not isinstance(data_plane_binding, dict) or set(data_plane_binding) != {
        "ref",
        "digest",
        "bindingDigest",
    }:
        raise RuntimeTopologyPackageError(
            "runtime topology data-plane binding identity is invalid"
        )
    compose = manifest.get("compose")
    policy = manifest.get("policy")
    observability_policy = manifest.get("observabilityPolicy")
    identity = {
        "compose": compose,
        "policy": policy,
        "observabilityPolicy": observability_policy,
        "serviceNames": service_names,
        "runtimeServiceNames": runtime_service_names,
        "serviceCoreModules": service_core_modules,
        "compositionSbom": composition_sbom,
        "dataPlaneBinding": data_plane_binding,
    }
    if manifest.get("topologyDigest") != _sha256_bytes(_canonical_json(identity)):
        raise RuntimeTopologyPackageError("runtime topology identity digest drifted")
    if not isinstance(compose, list) or not compose:
        raise RuntimeTopologyPackageError("runtime topology Compose closure is empty")
    if not isinstance(policy, dict) or set(policy) != {"ref", "digest"}:
        raise RuntimeTopologyPackageError("runtime topology policy fields mismatch")
    if not isinstance(observability_policy, dict) or set(observability_policy) != {
        "ref",
        "digest",
    }:
        raise RuntimeTopologyPackageError(
            "runtime topology observability policy fields mismatch"
        )

    selected_services: frozenset[str] | None
    include_control_plane = False
    if workload == "full":
        selected_services = None
        include_control_plane = True
    elif workload == "content-release":
        selected_services = CONTENT_RELEASE_SERVICES
    elif workload == "content-commercial":
        selected_services = CONTENT_COMMERCIAL_SERVICES
    else:
        raise RuntimeTopologyPackageError(
            "runtime topology workload is unsupported"
        )
    if selected_services is not None and not selected_services.issubset(service_names):
        raise RuntimeTopologyPackageError(
            "runtime topology content workload service closure is incomplete"
        )

    seen_refs: set[str] = set()
    seen_base = 0
    seen_service_layers: set[tuple[str, str]] = set()
    seen_bounded_dependencies = 0
    seen_control_plane = 0
    selected_paths: list[Path] = []
    for item in compose:
        expected_fields = {
            "role",
            "layer",
            "service",
            "ref",
            "digest",
            "sourceDigest",
        }
        if not isinstance(item, dict) or set(item) != expected_fields:
            raise RuntimeTopologyPackageError(
                "runtime topology Compose entry fields mismatch"
            )
        role = str(item.get("role") or "")
        layer = str(item.get("layer") or "")
        service = str(item.get("service") or "")
        reference = _artifact_relative(
            item.get("ref"),
            label="runtime topology Compose artifact",
        )
        if reference.as_posix() in seen_refs:
            raise RuntimeTopologyPackageError(
                "runtime topology Compose artifact is duplicated"
            )
        seen_refs.add(reference.as_posix())
        if role == "ops-base":
            if layer != "base" or service:
                raise RuntimeTopologyPackageError(
                    "runtime topology base entry identity is invalid"
                )
            seen_base += 1
            selected = True
        elif role == "service":
            if service not in service_names or layer not in {"base", "environment"}:
                raise RuntimeTopologyPackageError(
                    "runtime topology service entry identity is invalid"
                )
            service_layer = (service, layer)
            if service_layer in seen_service_layers:
                raise RuntimeTopologyPackageError(
                    "runtime topology service layer is duplicated"
                )
            seen_service_layers.add(service_layer)
            selected = (
                selected_services is None
                or service in selected_services
                or (
                    service in SERVICE_CORE_MODULE_SET
                    and bool(SERVICE_CORE_MODULE_SET & selected_services)
                )
            )
        elif role == "bounded-dependency":
            if (
                layer != "base"
                or service != "search-service"
                or reference
                != TOPOLOGY_RELATIVE_ROOT / _BOUNDED_SEARCH_ELASTICSEARCH_REF
            ):
                raise RuntimeTopologyPackageError(
                    "runtime topology bounded dependency identity is invalid"
                )
            seen_bounded_dependencies += 1
            selected = (
                workload == "content-release"
                and selected_services is not None
                and "search-service" in selected_services
            )
        elif role == "control-plane":
            if layer != "base" or service:
                raise RuntimeTopologyPackageError(
                    "runtime topology control-plane identity is invalid"
                )
            seen_control_plane += 1
            selected = include_control_plane
        else:
            raise RuntimeTopologyPackageError(
                "runtime topology Compose role is invalid"
            )
        encoded = _read_candidate_bytes(
            candidate_root,
            reference,
            label="runtime topology Compose artifact",
        )
        if (
            item.get("digest") != _sha256_bytes(encoded)
            or _DIGEST.fullmatch(str(item.get("sourceDigest") or "")) is None
        ):
            raise RuntimeTopologyPackageError(
                "runtime topology Compose artifact drifted"
            )
        try:
            parsed = yaml.safe_load(encoded.decode("utf-8"))
        except (UnicodeError, yaml.YAMLError) as exc:
            raise RuntimeTopologyPackageError(
                "runtime topology Compose artifact is unreadable"
            ) from exc
        services = parsed.get("services") if isinstance(parsed, dict) else None
        if not isinstance(services, dict) or not services:
            raise RuntimeTopologyPackageError(
                "runtime topology Compose artifact has no services"
            )
        if any(
            not isinstance(definition, Mapping) or "build" in definition
            for definition in services.values()
        ):
            raise RuntimeTopologyPackageError(
                "runtime topology Compose artifact retains a live build context"
            )
        workload_selector = parsed.get("x-qwq-workloads")
        if workload_selector is not None:
            allowed_workloads = {"full", "content-release", "content-commercial"}
            if (
                role != "service"
                or layer != "environment"
                or not isinstance(workload_selector, list)
                or not workload_selector
                or any(
                    not isinstance(item, str) or item not in allowed_workloads
                    for item in workload_selector
                )
                or len(workload_selector) != len(set(workload_selector))
            ):
                raise RuntimeTopologyPackageError(
                    "runtime topology workload selector is invalid"
                )
            selected = selected and workload in workload_selector
        if selected:
            selected_paths.append(candidate_root / reference.as_posix())

    seen_service_base = {
        service for service, layer in seen_service_layers if layer == "base"
    }
    if (
        seen_base != 1
        or seen_control_plane != 1
        or seen_bounded_dependencies != (1 if "search-service" in service_names else 0)
        or seen_service_base != set(service_names)
    ):
        raise RuntimeTopologyPackageError(
            "runtime topology Compose service closure is incomplete"
        )
    policy_reference = _artifact_relative(
        policy.get("ref"),
        label="runtime topology policy artifact",
    )
    policy_bytes = _read_candidate_bytes(
        candidate_root,
        policy_reference,
        label="runtime topology policy artifact",
    )
    if policy.get("digest") != _sha256_bytes(policy_bytes):
        raise RuntimeTopologyPackageError("runtime topology policy artifact drifted")
    alert_policy_reference = _artifact_relative(
        observability_policy.get("ref"),
        label="runtime topology observability policy artifact",
    )
    alert_policy_bytes = _read_candidate_bytes(
        candidate_root,
        alert_policy_reference,
        label="runtime topology observability policy artifact",
    )
    if observability_policy.get("digest") != _sha256_bytes(alert_policy_bytes):
        raise RuntimeTopologyPackageError(
            "runtime topology observability policy artifact drifted"
        )
    data_plane_reference, canonical_data_plane = _load_data_plane_binding_artifact(
        candidate_root,
        data_plane_binding,
        target=target,
        purpose=purpose,
    )

    sbom_reference = _artifact_relative(
        composition_sbom.get("ref"),
        label="runtime topology composition SBOM",
    )
    sbom_bytes = _read_candidate_bytes(
        candidate_root,
        sbom_reference,
        label="runtime topology composition SBOM",
    )
    if composition_sbom.get("digest") != _sha256_bytes(sbom_bytes):
        raise RuntimeTopologyPackageError(
            "runtime topology composition SBOM drifted"
        )
    try:
        sbom = json.loads(sbom_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeTopologyPackageError(
            "runtime topology composition SBOM is unreadable"
        ) from exc
    components = sbom.get("components") if isinstance(sbom, dict) else None
    component_names = (
        [str(item.get("name") or "") for item in components]
        if isinstance(components, list)
        and all(isinstance(item, dict) for item in components)
        else []
    )
    if component_names != runtime_service_names:
        raise RuntimeTopologyPackageError(
            "runtime topology composition SBOM workload closure drifted"
        )

    return {
        "schema": SCHEMA,
        "environment": environment,
        "target": target,
        "workload": workload,
        "topologyDigest": manifest["topologyDigest"],
        "composeFiles": selected_paths,
        "policyFile": candidate_root / policy_reference.as_posix(),
        "serviceNames": service_names,
        "runtimeServiceNames": runtime_service_names,
        "serviceCoreModules": service_core_modules,
        "compositionSbomFile": candidate_root / sbom_reference.as_posix(),
        "dataPlaneBindingFile": candidate_root / data_plane_reference.as_posix(),
        "dataPlaneBindingDigest": canonical_data_plane["bindingDigest"],
    }


def _main() -> int:
    from quwoquan_ops.cli.lib.runtime_topology_package_cli import main

    return main(load_runtime_topology_package, RuntimeTopologyPackageError)


if __name__ == "__main__":
    raise SystemExit(_main())
