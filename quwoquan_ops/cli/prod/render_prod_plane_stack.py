#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.output_paths import output_root as resolve_output_root
from quwoquan_ops.cli.lib.output_paths import deployment_work_root
from quwoquan_ops.cli.lib.output_paths import legal_static_deployment_package_dir
from quwoquan_ops.cli.lib.output_paths import portal_deployment_package_dir
from quwoquan_ops.cli.lib.output_paths import service_deployment_package_dir
from quwoquan_ops.cli.lib.output_paths import target_local_dir as resolve_target_local_dir

try:
    import yaml
except ImportError:  # pragma: no cover
    raise SystemExit("FAIL: PyYAML required")

ACCESS_MANIFEST = ROOT / "quwoquan_ops/environments/prod_plane_access_isolation.yaml"
TOPOLOGY_MANIFEST = ROOT / "quwoquan_ops/environments/environment_topology_manifest.yaml"
OBSERVABILITY_SOURCE_ROOT = ROOT / "quwoquan_ops/observability/monitoring"
DEFAULT_OUTPUT_ROOT = deployment_work_root("prod-hosted") / "rendered"

CONFIG_PACKAGE_ALIAS = {
    "recommendation-service": "rec-model-service",
}
EXTERNAL_DATA_HOST = "host.containers.internal"
EXTERNAL_POSTGRES_PORT = 19400
EXTERNAL_MONGO_PORT = 19410
EXTERNAL_REDIS_PORT = 19420
EXTERNAL_MONGO_URI = f"mongodb://{EXTERNAL_DATA_HOST}:{EXTERNAL_MONGO_PORT}/?directConnection=true"
PROD_CADDY_IMAGE = (
    "docker.io/library/caddy:2.8.4-alpine@"
    "sha256:af32e97399febea808609119bb21544d0265c58a02836576e32a2d082c262c17"
)
RUNTIME_LOG_EXPORT_SERVICES = {
    "assistant-service",
    "chat-service",
    "circle-service",
    "content-service",
    "entity-service",
    "integration-service",
    "notification-service",
    "platform-ops-service",
    "product-ops-service",
    "realtime-gateway",
    "rtc-service",
    "search-service",
    "tag-service",
    "user-service",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render prod plane rootless stack from truth sources.",
    )
    parser.add_argument("--plane", default="service", choices=["service", "edge"])
    parser.add_argument("--instance", default="prod", choices=["gray", "prod"])
    parser.add_argument(
        "--rollout-stage",
        default="full",
        choices=["gray-initial", "carry-on", "full"],
    )
    parser.add_argument("--config-version", required=True)
    parser.add_argument("--image-version", default=os.environ.get("IMAGE_VERSION", "0.0.1"))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_ROOT / "service"))
    parser.add_argument("--host", default="")
    return parser.parse_args()


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"FAIL: {path} must parse as object")
    return data


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _require_external_deployment_root(output_root: Path) -> None:
    """Reject deployment configs under disposable repository output."""
    output_root = output_root.expanduser().resolve()
    repository_output_root = resolve_output_root().expanduser().resolve()
    try:
        output_root.relative_to(repository_output_root)
    except ValueError:
        return
    raise SystemExit(
        "FAIL: prod deployment rendering must use QWQ_DEPLOY_WORK_ROOT outside "
        "QWQ_OUTPUT_ROOT; .qwq_output may only retain redacted evidence, "
        "observability, process and cache records"
    )


def _verified_package_release(
    package_dir: Path,
    *,
    config_version: str,
) -> Path:
    report_path = package_dir / "report.json"
    release_path = package_dir / "releases" / f"{config_version}.yaml"
    if not report_path.is_file() or not release_path.is_file():
        raise SystemExit(
            f"FAIL: package missing report or requested config release: {package_dir}"
        )
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        provenance = report["provenance"]
        release_files = provenance["releaseFiles"]
        expected_digest = release_files[release_path.name]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"FAIL: invalid package provenance: {report_path}") from exc
    if expected_digest != _sha256(release_path):
        raise SystemExit(f"FAIL: package release digest mismatch: {release_path}")
    release_artifact = provenance.get("releaseArtifact")
    if not isinstance(release_artifact, dict):
        raise SystemExit(f"FAIL: package release artifact provenance missing: {report_path}")
    if release_artifact.get("configVersion") != config_version:
        raise SystemExit(f"FAIL: package release config version mismatch: {report_path}")
    manifest_rel = str(release_artifact.get("manifest") or "")
    manifest_path = Path(manifest_rel)
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path
    if (
        not manifest_rel
        or not manifest_path.is_file()
        or release_artifact.get("manifestSha256") != _sha256(manifest_path)
    ):
        raise SystemExit(f"FAIL: package release artifact manifest mismatch: {report_path}")
    return release_path


def _git_revision() -> str:
    revision = os.environ.get("GITHUB_SHA", "").strip()
    if revision:
        return revision
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _plane_spec(plane_name: str) -> dict[str, Any]:
    access = _load_yaml(ACCESS_MANIFEST)
    for plane in access.get("planes") or []:
        if str(plane.get("plane")) == plane_name:
            return plane
    raise SystemExit(f"FAIL: plane missing from access manifest: {plane_name}")


def _rewrite_volume(raw: str) -> str:
    return raw


def _compose_bind_source(path_value: str) -> str:
    value = str(path_value).strip()
    if not value:
        raise SystemExit("FAIL: compose bind source path is empty")
    if value.startswith("/"):
        return value
    if value.startswith("./"):
        return value
    return f"./{value}"


def _rewrite_volume_with_layout(
    raw: str,
    *,
    config_root: str,
    media_root: str,
    legal_root: str,
    portal_root: str,
    caddyfile_path: str,
    model_cache_root: str,
) -> str:
    mount_sources = {
        "/etc/qwq-config": config_root,
        "/srv/media": media_root,
        "/var/lib/quwoquan/chat-media": media_root,
        "/srv/legal": legal_root,
        "/srv/portal": portal_root,
        "/etc/caddy/Caddyfile": caddyfile_path,
        "/app/cache": model_cache_root,
    }
    for target, source in mount_sources.items():
        marker = f":{target}"
        if marker in raw:
            return f"{_compose_bind_source(source)}{raw[raw.index(marker):]}"
    return raw


def _named_volume_source(raw: str) -> str | None:
    if ":" not in raw:
        return None
    source = raw.split(":", 1)[0]
    if source.startswith(".") or source.startswith("/") or source.startswith("${"):
        return None
    return source


def _rewrite_service(
    name: str,
    spec: dict[str, Any],
    selected: set[str],
    *,
    image_version: str,
    versioned_image: bool,
    instance: str,
    config_root: str,
    media_root: str,
    legal_root: str,
    portal_root: str,
    caddyfile_path: str,
    model_cache_root: str,
    credentials_root: str = "",
    runtime_credentials: dict[str, Any] | None = None,
) -> dict[str, Any]:
    updated = copy.deepcopy(spec)
    updated.pop("build", None)
    if versioned_image:
        if not image_version or image_version == "latest":
            raise SystemExit(f"FAIL: immutable image version required for {name}")
        updated["image"] = f"localhost/quwoquan_service_{name}:{image_version}"
    # prod 渲染面按 rootlessGovernedComposeServices 显式选择服务，
    # gamma-local 的 compose profile 开关不进入生产 compose。
    updated.pop("profiles", None)
    if name == "gamma-proxy":
        updated["image"] = PROD_CADDY_IMAGE
        updated["ports"] = (
            ["80:80", "443:443", "127.0.0.1:12019:2019"]
            if instance == "prod"
            else ["29000:80", "127.0.0.1:22019:2019"]
        )
    if isinstance(updated.get("depends_on"), dict):
        updated["depends_on"] = {
            dep: dep_spec
            for dep, dep_spec in updated["depends_on"].items()
            if dep in selected
        }
        if not updated["depends_on"]:
            updated.pop("depends_on")
    environment = updated.get("environment")
    if isinstance(environment, dict) and environment.get("APP_ENV") == "gamma":
        environment["APP_ENV"] = "prod"
    if isinstance(environment, dict):
        environment["OTEL_EXPORTER_OTLP_ENDPOINT"] = (
            "${OTEL_EXPORTER_OTLP_ENDPOINT:-otel-collector:4318}"
        )
        if name in RUNTIME_LOG_EXPORT_SERVICES:
            # 云侧服务日志上云：stdout 镜像批量推送到 product-ops 内部
            # runtime log ingest（机器凭据）并先写持久 spool。product-ops
            # 也通过同一端点回灌；其内部 ingest 路径绕开自身 access logger，
            # 因而不会形成 HTTP feedback loop。
            if "product-ops-service" in selected:
                environment["RUNTIME_LOG_INGEST_URL"] = (
                    "http://product-ops-service:18086/ops/internal/runtime-logs:ingest"
                )
            else:
                environment["RUNTIME_LOG_INGEST_URL"] = (
                    f"http://{EXTERNAL_DATA_HOST}:"
                    "${LOCAL_GAMMA_PRODUCT_OPS_SERVICE_PORT:?product ops port is required}"
                    "/ops/internal/runtime-logs:ingest"
                )
            environment["RUNTIME_LOG_INGEST_TOKEN"] = (
                "${RUNTIME_LOG_INGEST_TOKEN:?RUNTIME_LOG_INGEST_TOKEN is required}"
            )
            environment["RUNTIME_LOG_SPOOL_DIR"] = (
                f"/var/lib/quwoquan/runtime-log-spool/{name}"
            )
        if name == "rec-model-service":
            environment["MONGODB_URI"] = EXTERNAL_MONGO_URI
        if name == "content-service":
            environment["MONGO_URI"] = EXTERNAL_MONGO_URI
            environment["CONTENT_REDIS_REC_ADDR"] = f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
            environment["CONTENT_REDIS_GENERAL_ADDR"] = f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
        if name == "chat-service":
            environment["MONGO_URI"] = EXTERNAL_MONGO_URI
            environment["REDIS_ADDR"] = f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
            environment["CHAT_REDIS_REALTIME_ADDR"] = f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
            environment["CHAT_REDIS_GENERAL_ADDR"] = f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
            environment["CHAT_REDIS_RELIABLE_TASK_ADDR"] = f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
        if name == "user-service":
            environment["POSTGRES_DSN"] = (
                f"postgres://quwoquan:quwoquan@{EXTERNAL_DATA_HOST}:{EXTERNAL_POSTGRES_PORT}/"
                "quwoquan?sslmode=disable"
            )
            environment["MONGODB_URI"] = EXTERNAL_MONGO_URI
            environment["REDIS_ADDR"] = f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
        if name == "assistant-service":
            environment["MONGODB_URI"] = EXTERNAL_MONGO_URI
            environment["REDIS_GENERAL_ADDR"] = f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
            environment["REDIS_REC_ADDR"] = f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
        if name == "product-ops-service":
            environment["POSTGRES_DSN"] = (
                f"postgres://quwoquan:quwoquan@{EXTERNAL_DATA_HOST}:{EXTERNAL_POSTGRES_PORT}/"
                "quwoquan?sslmode=disable"
            )
            environment["MONGO_URI"] = EXTERNAL_MONGO_URI
            environment["PRODUCT_OPS_REDIS_REC_ADDR"] = f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
            environment["PRODUCT_OPS_REDIS_GENERAL_ADDR"] = f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
            environment["PROMETHEUS_URL"] = "${PRODUCT_OPS_PROMETHEUS_URL:-http://prometheus:9090}"
            # config_sync 循环从平台控制面拉取有效配置并回报 ACK；
            # prod 缺该地址时 config_sync 会 fail-fast，禁止静默跳过。
            environment["PLATFORM_OPS_BASE_URL"] = "http://platform-ops-service:18088"
            # 云侧服务日志上云内部通道的服务端校验密钥（fail-closed）。
            environment["RUNTIME_LOG_INGEST_TOKEN"] = (
                "${RUNTIME_LOG_INGEST_TOKEN:?RUNTIME_LOG_INGEST_TOKEN is required}"
            )
            environment["OPS_OIDC_ISSUER"] = (
                "${OPS_OIDC_ISSUER:?OPS_OIDC_ISSUER is required}"
            )
            environment["OPS_OIDC_AUDIENCE"] = (
                "${OPS_OIDC_AUDIENCE:?OPS_OIDC_AUDIENCE is required}"
            )
            environment["OPS_OIDC_JWKS_URL"] = (
                "${OPS_OIDC_JWKS_URL:?OPS_OIDC_JWKS_URL is required}"
            )
        if name == "platform-ops-service":
            environment["POSTGRES_DSN"] = (
                f"postgres://quwoquan:quwoquan@{EXTERNAL_DATA_HOST}:{EXTERNAL_POSTGRES_PORT}/"
                "quwoquan?sslmode=disable"
            )
            environment["PROMETHEUS_URL"] = "${PLATFORM_OPS_PROMETHEUS_URL:-http://prometheus:9090}"
            # Alertmanager 告警回流 ingest 的机器凭据；缺失时服务端 fail-closed。
            environment["ALERT_INGEST_TOKEN"] = "${ALERT_INGEST_TOKEN:?ALERT_INGEST_TOKEN is required}"
            environment["OPS_OIDC_ISSUER"] = (
                "${OPS_OIDC_ISSUER:?OPS_OIDC_ISSUER is required}"
            )
            environment["OPS_OIDC_AUDIENCE"] = (
                "${OPS_OIDC_AUDIENCE:?OPS_OIDC_AUDIENCE is required}"
            )
            environment["OPS_OIDC_JWKS_URL"] = (
                "${OPS_OIDC_JWKS_URL:?OPS_OIDC_JWKS_URL is required}"
            )
        if name == "tag-service":
            environment["REDIS_ADDR"] = f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
            environment["TAG_MONGO_URI"] = EXTERNAL_MONGO_URI
        if name == "entity-service":
            environment["ENTITY_MONGO_URI"] = EXTERNAL_MONGO_URI
            # prod-hosted 首波 service plane 不含 elasticsearch（search-service 未迁入），
            # 关闭 write-time 索引投影；主页读写主链路（Mongo homepages 权威集合）不受影响。
            environment["SEARCH_ES_ENABLED"] = "false"
            environment.pop("SEARCH_ES_ENDPOINTS", None)
        if name == "integration-service":
            environment["INTEGRATION_MONGO_URI"] = EXTERNAL_MONGO_URI
            environment["INTEGRATION_PUSH_ENABLED"] = "true"
            environment["INTEGRATION_PUSH_MODE"] = "real"
            environment["INTEGRATION_PUSH_USER_SERVICE_BASE_URL"] = (
                "http://user-service:18082"
            )
            environment["INTEGRATION_PUSH_APNS_ENVIRONMENT"] = "production"
            environment["INTEGRATION_PUSH_APNS_KEY_FILE"] = (
                "/run/secrets/quwoquan/integration/apns-auth-key.p8"
            )
            environment["INTEGRATION_PUSH_FCM_SERVICE_ACCOUNT_FILE"] = (
                "/run/secrets/quwoquan/integration/fcm-service-account.json"
            )
        if name == "notification-service":
            environment["NOTIFICATION_MONGO_URI"] = EXTERNAL_MONGO_URI
            environment["NOTIFICATION_REDIS_ADDR"] = (
                f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
            )
            environment["NOTIFICATION_REDIS_GENERAL_DB"] = "1"
            environment["NOTIFICATION_REDIS_REALTIME_DB"] = "4"
            environment["NOTIFICATION_REALTIME_BASE_URL"] = (
                f"http://{EXTERNAL_DATA_HOST}:"
                "${LOCAL_GAMMA_REALTIME_PORT:?realtime port is required}"
            )
        if name == "realtime-gateway":
            environment["REALTIME_REDIS_ADDR"] = (
                f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
            )
        if name == "rtc-service":
            environment["MONGO_URI"] = EXTERNAL_MONGO_URI
            environment["REDIS_ADDR"] = (
                f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
            )
            environment["RTC_MEDIA_CONNECTION_URL"] = (
                "${PROD_RTC_MEDIA_CONNECTION_URL:?PROD_RTC_MEDIA_CONNECTION_URL is required}"
            )
            environment["RTC_MEDIA_API_KEY"] = (
                "${PROD_RTC_MEDIA_API_KEY:?PROD_RTC_MEDIA_API_KEY is required}"
            )
            environment["RTC_MEDIA_API_SECRET"] = (
                "${PROD_RTC_MEDIA_API_SECRET:?PROD_RTC_MEDIA_API_SECRET is required}"
            )
    if name != "gamma-proxy":
        extra_hosts = list(updated.get("extra_hosts") or [])
        if f"{EXTERNAL_DATA_HOST}:host-gateway" not in extra_hosts:
            extra_hosts.append(f"{EXTERNAL_DATA_HOST}:host-gateway")
        updated["extra_hosts"] = extra_hosts
    volumes = list(updated.get("volumes") or [])
    credential_spec = (runtime_credentials or {}).get(name)
    if credential_spec is not None:
        if not credentials_root or not Path(credentials_root).is_absolute():
            raise SystemExit(
                f"FAIL: absolute credentialsPath required for runtime credentials: {name}"
            )
        env_file = _runtime_credential_source(
            credentials_root,
            credential_spec.get("envFile"),
            label=f"{name}.envFile",
        )
        updated["env_file"] = [env_file]
        credential_files = credential_spec.get("files") or {}
        if name == "integration-service":
            apns_key = _runtime_credential_source(
                credentials_root,
                credential_files.get("apnsKey"),
                label=f"{name}.files.apnsKey",
            )
            fcm_account = _runtime_credential_source(
                credentials_root,
                credential_files.get("fcmServiceAccount"),
                label=f"{name}.files.fcmServiceAccount",
            )
            volumes.extend(
                [
                    (
                        f"{apns_key}:"
                        "/run/secrets/quwoquan/integration/apns-auth-key.p8:ro"
                    ),
                    (
                        f"{fcm_account}:"
                        "/run/secrets/quwoquan/integration/"
                        "fcm-service-account.json:ro"
                    ),
                ]
            )
    if name in RUNTIME_LOG_EXPORT_SERVICES:
        spool_mount = "runtime-log-spool:/var/lib/quwoquan/runtime-log-spool"
        if spool_mount not in volumes:
            volumes.append(spool_mount)
    if name == "platform-ops-service":
        environment["QWQ_PROD_RELEASE_STATE_DIR"] = (
            "/var/lib/quwoquan/release-state"
        )
        ledger_mount = (
            "./release-ledger:/var/lib/quwoquan/release-state:ro"
        )
        if ledger_mount not in volumes:
            volumes.append(ledger_mount)
    if volumes:
        updated["volumes"] = [
            (
                _rewrite_volume_with_layout(
                    item,
                    config_root=config_root,
                    media_root=media_root,
                    legal_root=legal_root,
                    portal_root=portal_root,
                    caddyfile_path=caddyfile_path,
                    model_cache_root=model_cache_root,
                )
                if isinstance(item, str)
                else item
            )
            for item in volumes
        ]
    return updated


def _runtime_credential_source(
    credentials_root: str,
    relative_source: Any,
    *,
    label: str,
) -> str:
    normalized = str(relative_source or "").strip()
    relative = Path(normalized)
    if not normalized or relative.is_absolute() or ".." in relative.parts:
        raise SystemExit(
            f"FAIL: {label} must be a non-empty credentialsPath-relative path"
        )
    return str(Path(credentials_root) / relative)


def _filter_top_level_volumes(services: dict[str, Any], top_level: dict[str, Any]) -> dict[str, Any]:
    referenced: set[str] = set()
    for spec in services.values():
        for item in spec.get("volumes") or []:
            if not isinstance(item, str):
                continue
            source = _named_volume_source(item)
            if source:
                referenced.add(source)
    return {name: value for name, value in top_level.items() if name in referenced}


def _ensure_mapping(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    node = payload
    for key in keys:
        child = node.get(key)
        if not isinstance(child, dict):
            child = {}
            node[key] = child
        node = child
    return node


def _set_standalone_redis(spec: dict[str, Any], addr_placeholder: str) -> None:
    spec["mode"] = "standalone"
    spec["addr"] = addr_placeholder
    spec["addrs"] = []
    spec["tls"] = False


def _rewrite_env_override(service: str, payload: dict[str, Any]) -> dict[str, Any]:
    updated = copy.deepcopy(payload)
    if service == "content-service":
        _ensure_mapping(updated, "mongo")["uri"] = "${MONGO_URI}"
        _set_standalone_redis(_ensure_mapping(updated, "redis", "rec"), "${CONTENT_REDIS_REC_ADDR}")
        _set_standalone_redis(
            _ensure_mapping(updated, "redis", "general"),
            "${CONTENT_REDIS_GENERAL_ADDR}",
        )
        rec_model = _ensure_mapping(updated, "rec_model_service")
        rec_model["url"] = "${REC_MODEL_SERVICE_URL}"
        rec_model["enabled"] = True
    elif service == "chat-service":
        _ensure_mapping(updated, "mongodb")["uri"] = "${MONGO_URI}"
        _set_standalone_redis(_ensure_mapping(updated, "redis", "realtime"), "${REDIS_ADDR}")
        _set_standalone_redis(_ensure_mapping(updated, "redis", "general"), "${REDIS_ADDR}")
        _set_standalone_redis(
            _ensure_mapping(updated, "redis", "reliabletask"),
            "${REDIS_ADDR}",
        )
    elif service == "user-service":
        _ensure_mapping(updated, "postgres")["dsn"] = "${POSTGRES_DSN}"
        _ensure_mapping(updated, "mongodb")["uri"] = "${MONGODB_URI}"
        _set_standalone_redis(_ensure_mapping(updated, "redis", "general"), "${REDIS_ADDR}")
    elif service == "assistant-service":
        _ensure_mapping(updated, "mongodb")["uri"] = "${MONGODB_URI}"
        _set_standalone_redis(_ensure_mapping(updated, "redis", "rec"), "${REDIS_REC_ADDR}")
        _set_standalone_redis(
            _ensure_mapping(updated, "redis", "general"),
            "${REDIS_GENERAL_ADDR}",
        )
    elif service == "product-ops-service":
        _ensure_mapping(updated, "postgres")["dsn"] = "${POSTGRES_DSN}"
        _ensure_mapping(updated, "mongodb")["uri"] = "${MONGO_URI}"
        _set_standalone_redis(
            _ensure_mapping(updated, "redis", "rec"),
            "${PRODUCT_OPS_REDIS_REC_ADDR}",
        )
        _set_standalone_redis(
            _ensure_mapping(updated, "redis", "general"),
            "${PRODUCT_OPS_REDIS_GENERAL_ADDR}",
        )
    elif service == "tag-service":
        _set_standalone_redis(_ensure_mapping(updated, "redis", "rec"), "${REDIS_ADDR}")
        _set_standalone_redis(_ensure_mapping(updated, "redis", "general"), "${REDIS_ADDR}")
    elif service == "entity-service":
        # mongo 经 ENTITY_MONGO_URI env 注入；prod-hosted 首波无 ES，配置层同步关闭。
        _ensure_mapping(updated, "es")["enabled"] = False
    return updated


def _write_config_tree(
    *,
    config_services: list[str],
    config_version: str,
    output_root: Path,
) -> dict[str, Any]:
    config_root = output_root / "runtime" / "config-root"
    sources: dict[str, Any] = {}
    for service in config_services:
        package_service = CONFIG_PACKAGE_ALIAS.get(service, service)
        package_dir = service_deployment_package_dir(
            "prod",
            package_service,
            target="prod-hosted",
        )
        if not package_dir.is_dir():
            raise SystemExit(f"FAIL: missing prod service package for {service}: {package_dir}")
        default_src = package_dir / "default_config.yaml"
        env_src = package_dir / "config.yaml"
        if not default_src.is_file() or not env_src.is_file():
            raise SystemExit(f"FAIL: incomplete service package for {service}: {package_dir}")
        target_default = config_root / "configs" / service / "default" / "config.yaml"
        target_env = config_root / "configs" / service / "prod" / "config.yaml"
        target_default.parent.mkdir(parents=True, exist_ok=True)
        target_env.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(default_src, target_default)
        env_payload = yaml.safe_load(env_src.read_text(encoding="utf-8")) or {}
        if not isinstance(env_payload, dict):
            raise SystemExit(f"FAIL: env override must be object: {env_src}")
        target_env.write_text(
            yaml.safe_dump(
                _rewrite_env_override(service, env_payload),
                sort_keys=False,
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        sources[service] = {
            "package": str(package_dir),
            "defaultConfigDigest": _sha256(default_src),
            "environmentConfigDigest": _sha256(env_src),
        }

        release_src = _verified_package_release(
            package_dir,
            config_version=config_version,
        )
        release_target = config_root / "releases" / "config" / service / f"{config_version}.yaml"
        release_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(release_src, release_target)
        sources[service]["releaseConfigDigest"] = _sha256(release_src)

    # IaC 只读配置快照的另外两个域：端侧 App 发布配置与数据工程共享 catalog。
    # platform-ops 生产容器只挂 config-root，不含仓库树，必须在渲染期落盘。
    app_config_src = ROOT / "quwoquan_app" / "configs" / "prod"
    if not app_config_src.is_dir():
        raise SystemExit(f"FAIL: missing app prod config tree: {app_config_src}")
    app_target = config_root / "configs" / "app" / "prod"
    app_target.mkdir(parents=True, exist_ok=True)
    for entry in sorted(app_config_src.iterdir()):
        if entry.is_file() and entry.suffix in {".yaml", ".yml", ".json"}:
            shutil.copy2(entry, app_target / entry.name)
    sources["app"] = {"package": str(app_config_src)}

    data_catalog_src = ROOT / "quwoquan_data" / "control_plane" / "_shared" / "catalogs"
    if not data_catalog_src.is_dir():
        raise SystemExit(f"FAIL: missing data catalogs tree: {data_catalog_src}")
    data_target = config_root / "data-catalogs"
    data_target.mkdir(parents=True, exist_ok=True)
    for entry in sorted(data_catalog_src.iterdir()):
        if entry.is_file() and entry.suffix in {".yaml", ".yml"}:
            shutil.copy2(entry, data_target / entry.name)
    sources["data"] = {"package": str(data_catalog_src)}

    # 灰度路由策略（IaC）：编译进 Caddyfile 的同时落进 config-root，
    # 供 platform-ops 生产容器只读展示（Portal 灰度页）。
    routing_policy_src = ROOT / "quwoquan_ops" / "environments" / "gray_routing_policy.yaml"
    if not routing_policy_src.is_file():
        raise SystemExit(f"FAIL: missing gray routing policy: {routing_policy_src}")
    routing_target = config_root / "gray-routing" / "policy.yaml"
    routing_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(routing_policy_src, routing_target)
    sources["gray-routing"] = {
        "package": str(routing_policy_src),
        "policyDigest": _sha256(routing_policy_src),
    }
    return sources


def _prod_public_hosts() -> dict[str, str]:
    """从环境拓扑真相源解析生产域名，禁止生产 Caddy 回退本地域名或 IP。"""
    from urllib.parse import urlparse

    topology = _load_yaml(TOPOLOGY_MANIFEST)
    public_bases = (
        ((topology.get("targets") or {}).get("prod-hosted") or {}).get("publicBases")
        or {}
    )
    hosts: dict[str, str] = {}
    for key in ("api", "realtime", "productOps", "mediaImage", "mediaUpload"):
        host = urlparse(str(public_bases.get(key) or "")).hostname or ""
        if (
            not host
            or host.endswith((".test", ".example"))
            or re.fullmatch(r"\d+(?:\.\d+){3}", host)
        ):
            raise SystemExit(f"FAIL: prod-hosted publicBases.{key} must use a public DNS name")
        hosts[key] = host
    return hosts


def _render_gray_routing_block(rollout_stage: str) -> str:
    """把灰度路由策略（IaC 真相源）编译为 Caddy named matcher + handle 块。

    仅 prod 实例栈注入：命中任一启用维度的请求被转发到 gray 栈 edge，
    未命中继续走本栈稳定服务。gray 栈自身不注入（防转发环）。
    """
    policy_path = ROOT / "quwoquan_ops" / "environments" / "gray_routing_policy.yaml"
    policy = (_load_yaml(policy_path).get("policy") or {}) if policy_path.is_file() else {}
    if not policy.get("enabled"):
        return ""
    if rollout_stage not in {"gray-initial", "carry-on", "full"}:
        raise SystemExit(
            "FAIL: gray routing policy received an unsupported rollout stage "
            f"{rollout_stage!r}"
        )
    stage_dimensions = policy.get("stageDimensions") or {}
    dimensions = stage_dimensions.get(rollout_stage) or {}
    upstream = str(policy.get("grayUpstream") or "").strip()
    if not upstream:
        raise SystemExit("FAIL: gray routing enabled but grayUpstream is empty")
    skip_verify = bool(policy.get("grayUpstreamTlsInsecureSkipVerify"))
    header_by_dimension = {
        "appVersions": "X-Client-App-Version",
        "userIds": "X-Client-User-Id",
        "provinces": "X-Client-Region-Code",
        "carriers": "X-Client-Carrier",
    }
    transport_lines = ""
    if upstream.startswith("https://") and skip_verify:
        transport_lines = (
            "\t\ttransport http {\n"
            "\t\t\ttls_insecure_skip_verify\n"
            "\t\t}\n"
        )
    blocks: list[str] = []
    for dimension, header_name in header_by_dimension.items():
        values = [str(item).strip() for item in (dimensions.get(dimension) or []) if str(item).strip()]
        if not values:
            continue
        matcher = f"@gray_{dimension.lower()}"
        header_lines = "".join(
            f"\t\theader {header_name} {value}\n" for value in values
        )
        blocks.append(
            f"\t{matcher} {{\n"
            f"{header_lines}"
            f"\t}}\n"
            f"\thandle {matcher} {{\n"
            f"\t\treverse_proxy {upstream} {{\n"
            f"\t\t\theader_up Host {{host}}\n"
            f"{transport_lines}"
            f"\t\t}}\n"
            f"\t}}\n"
        )
    return "".join(blocks)


def _write_caddyfile(
    output_root: Path,
    instance: str,
    rollout_stage: str = "full",
) -> None:
    target = output_root / "runtime" / "Caddyfile"
    target.parent.mkdir(parents=True, exist_ok=True)
    public_hosts = _prod_public_hosts()
    gray_routing_block = (
        _render_gray_routing_block(rollout_stage)
        if instance == "prod" and rollout_stage != "full"
        else ""
    )
    caddy_text = """{
\tadmin 0.0.0.0:2019
\tlocal_certs
}

(local_gamma_tls) {
\ttls internal
}

(media_cors) {
\theader {
\t\tAccess-Control-Allow-Origin "*"
\t\tAccess-Control-Allow-Methods "GET, HEAD, OPTIONS"
\t\tAccess-Control-Allow-Headers "*"
\t\tCross-Origin-Resource-Policy "cross-origin"
\t}
}

prod-api.quwoquan-env.test {
\timport local_gamma_tls
\thandle /healthz {
\t\treverse_proxy content-service:18080
\t}
\thandle /config/app {
\t\treverse_proxy content-service:18080
\t}
\thandle /livez {
\t\treverse_proxy content-service:18080
\t}
\thandle /startupz {
\t\treverse_proxy content-service:18080
\t}
\t@api_content path /content*
\thandle @api_content {
\t\treverse_proxy content-service:18080
\t}
\t@api_chat path /chat*
\thandle @api_chat {
\t\treverse_proxy chat-service:18081
\t}
\t@api_user path /auth* /owner* /user* /me /me/*
\thandle @api_user {
\t\treverse_proxy user-service:18082
\t}
\t@api_assistant path /assistant*
\thandle @api_assistant {
\t\treverse_proxy assistant-service:18087
\t}
\t@api_tag path /tag*
\thandle @api_tag {
\t\treverse_proxy tag-service:18092
\t}
\t@api_entity path /homepages*
\thandle @api_entity {
\t\treverse_proxy entity-service:18084
\t}
\thandle /ops/* {
\t\treverse_proxy product-ops-service:18086
\t}
\thandle /control-plane/product/* {
\t\treverse_proxy product-ops-service:18086
\t}
\thandle /legal/manifest.json {
\t\theader {
\t\t\tCache-Control "public, max-age=300"
\t\t\tX-Content-Type-Options "nosniff"
\t\t}
\t\troot * /srv/legal
\t\tfile_server
\t}
\thandle /legal/* {
\t\theader {
\t\t\tCache-Control "public, max-age=300"
\t\t\tX-Content-Type-Options "nosniff"
\t\t\tContent-Type "text/html; charset=utf-8"
\t\t}
\t\troot * /srv/legal
\t\tfile_server
\t}
\thandle /media/* {
\t\timport media_cors
\t\troot * /srv/media
\t\tfile_server
\t}
\thandle {
\t\trespond "prod-hosted route is not ready for this path" 404
\t}
}

prod-product-ops.quwoquan-env.test {
\timport local_gamma_tls
\thandle /healthz {
\t\treverse_proxy product-ops-service:18086
\t}
\thandle /ops/* {
\t\treverse_proxy product-ops-service:18086
\t}
\thandle /control-plane/product/* {
\t\treverse_proxy product-ops-service:18086
\t}
\thandle /control-plane/platform/* {
\t\treverse_proxy platform-ops-service:18088
\t}
\t# 运维运营 Portal SPA（同源静态站点：API 与前端共享 ops 域名，避免 CORS）。
\thandle {
\t\theader {
\t\t\tX-Content-Type-Options "nosniff"
\t\t\tX-Frame-Options "DENY"
\t\t\tReferrer-Policy "no-referrer"
\t\t\tContent-Security-Policy "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; connect-src 'self' https:; frame-ancestors 'none'"
\t\t}
\t\troot * /srv/portal
\t\ttry_files {path} /index.html
\t\tfile_server
\t}
}

prod-avatar.quwoquan-env.test,
prod-image.quwoquan-env.test,
prod-video.quwoquan-env.test,
prod-upload.quwoquan-env.test {
\timport local_gamma_tls
\timport media_cors
\troot * /srv/media
\tfile_server
}

:80 {
\thandle /healthz {
\t\treverse_proxy content-service:18080
\t}
\thandle /config/app {
\t\treverse_proxy content-service:18080
\t}
\t@pub_content path /content*
\thandle @pub_content {
\t\treverse_proxy content-service:18080
\t}
\t@pub_chat path /chat*
\thandle @pub_chat {
\t\treverse_proxy chat-service:18081
\t}
\t@pub_user path /auth* /owner* /user* /me /me/*
\thandle @pub_user {
\t\treverse_proxy user-service:18082
\t}
\t@pub_assistant path /assistant*
\thandle @pub_assistant {
\t\treverse_proxy assistant-service:18087
\t}
\t@pub_tag path /tag*
\thandle @pub_tag {
\t\treverse_proxy tag-service:18092
\t}
\t@pub_entity path /homepages*
\thandle @pub_entity {
\t\treverse_proxy entity-service:18084
\t}
\thandle /ops/* {
\t\treverse_proxy product-ops-service:18086
\t}
\thandle /control-plane/product/* {
\t\treverse_proxy product-ops-service:18086
\t}
\thandle /legal/manifest.json {
\t\theader {
\t\t\tCache-Control "public, max-age=300"
\t\t\tX-Content-Type-Options "nosniff"
\t\t}
\t\troot * /srv/legal
\t\tfile_server
\t}
\thandle /legal/* {
\t\theader {
\t\t\tCache-Control "public, max-age=300"
\t\t\tX-Content-Type-Options "nosniff"
\t\t\tContent-Type "text/html; charset=utf-8"
\t\t}
\t\troot * /srv/legal
\t\tfile_server
\t}
\thandle /media/* {
\t\timport media_cors
\t\troot * /srv/media
\t\tfile_server
\t}
\thandle {
\t\trespond "prod-hosted route is not ready for this path" 404
\t}
}
"""
    if instance == "gray":
        direct_http = caddy_text.rfind("\n:80 {")
        if direct_http < 0:
            raise SystemExit("FAIL: gray Caddy HTTP route block is missing")
        caddy_text = "{\n\tadmin 0.0.0.0:2019\n}\n" + caddy_text[direct_http + 1 :]
    else:
        caddy_text = caddy_text.replace(
            "{\n\tadmin 0.0.0.0:2019\n\tlocal_certs\n}",
            "{\n\tadmin 0.0.0.0:2019\n}",
            1,
        )
        caddy_text = caddy_text.replace(
            "\n(local_gamma_tls) {\n\ttls internal\n}\n",
            "",
            1,
        ).replace("\timport local_gamma_tls\n", "")
        api_sites = f"{public_hosts['api']}, {public_hosts['realtime']} {{"
        caddy_text = caddy_text.replace(
            "prod-api.quwoquan-env.test {",
            api_sites,
            1,
        )
        caddy_text = caddy_text.replace(
            "prod-product-ops.quwoquan-env.test {",
            f"{public_hosts['productOps']} {{",
            1,
        )
        caddy_text = caddy_text.replace(
            "prod-avatar.quwoquan-env.test,\n"
            "prod-image.quwoquan-env.test,\n"
            "prod-video.quwoquan-env.test,\n"
            "prod-upload.quwoquan-env.test {",
            f"{public_hosts['mediaImage']}, {public_hosts['mediaUpload']} {{",
            1,
        )
        security_snippet = """
(prod_security) {
\theader {
\t\tStrict-Transport-Security "max-age=31536000; includeSubDomains; preload"
\t\tX-Content-Type-Options "nosniff"
\t\tX-Frame-Options "DENY"
\t\tReferrer-Policy "strict-origin-when-cross-origin"
\t}
}
"""
        global_end = caddy_text.index("}\n") + 2
        caddy_text = caddy_text[:global_end] + security_snippet + caddy_text[global_end:]
        for site in (
            api_sites,
            f"{public_hosts['productOps']} {{",
            f"{public_hosts['mediaImage']}, {public_hosts['mediaUpload']} {{",
        ):
            caddy_text = caddy_text.replace(site, site + "\n\timport prod_security", 1)
        direct_http = caddy_text.rfind("\n:80 {")
        if direct_http < 0:
            raise SystemExit("FAIL: prod Caddy direct HTTP fallback block is missing")
        caddy_text = caddy_text[:direct_http].rstrip() + "\n"
    if gray_routing_block:
        # 灰度路由 matcher 必须在 API handle 之前：命中维度的请求整体转发到
        # gray 栈 edge；未命中继续走本栈稳定服务。
        caddy_text = caddy_text.replace(
            "\thandle /healthz {\n\t\treverse_proxy content-service:18080\n\t}",
            gray_routing_block
            + "\thandle /healthz {\n\t\treverse_proxy content-service:18080\n\t}",
            1,
        )
    target.write_text(caddy_text, encoding="utf-8")


def _write_env_file(
    output_root: Path,
    config_version: str,
    image_version: str,
    instance: str,
) -> None:
    lines = [
        f"LOCAL_GAMMA_CONFIG_VERSION={config_version}",
        f"LOCAL_GAMMA_IMAGE_VERSION={image_version}",
        (
            "LOCAL_GAMMA_REALTIME_GATEWAY_IMAGE="
            f"localhost/quwoquan_service_realtime-gateway:{image_version}"
        ),
        (
            "LOCAL_GAMMA_RTC_SERVICE_IMAGE="
            f"localhost/quwoquan_service_rtc-service:{image_version}"
        ),
        f"LOCAL_GAMMA_TLS_MODE={'internal' if instance == 'gray' else 'automatic'}",
    ]
    if instance == "gray":
        lines.extend(
            [
                "LOCAL_GAMMA_HTTP_PORT=29000",
                "LOCAL_GAMMA_PRODUCT_OPS_PORT=29010",
                "LOCAL_GAMMA_MEDIA_EDGE_PORT=29100",
                "LOCAL_GAMMA_HTTPS_PORT=28443",
                "LOCAL_GAMMA_ADMIN_PORT=22019",
                "LOCAL_GAMMA_CHAT_PORT=29200",
                "LOCAL_GAMMA_USER_PORT=29210",
                "LOCAL_GAMMA_CONTENT_PORT=29220",
                "LOCAL_GAMMA_ASSISTANT_PORT=29230",
                "LOCAL_GAMMA_REC_MODEL_PORT=29240",
                "LOCAL_GAMMA_PRODUCT_OPS_SERVICE_PORT=29250",
                "LOCAL_GAMMA_TAG_PORT=29270",
                "LOCAL_GAMMA_ENTITY_PORT=29290",
                "LOCAL_GAMMA_INTEGRATION_PORT=29310",
                "LOCAL_GAMMA_NOTIFICATION_PORT=29320",
                "LOCAL_GAMMA_REALTIME_PORT=29340",
                "LOCAL_GAMMA_RTC_PORT=29350",
                "LOCAL_GAMMA_POSTGRES_PORT=29400",
                "LOCAL_GAMMA_MONGO_PORT=29410",
                "LOCAL_GAMMA_REDIS_PORT=29420",
            ]
        )
    else:
        lines.extend(
            [
                "LOCAL_GAMMA_HTTP_PORT=19000",
                "LOCAL_GAMMA_PRODUCT_OPS_PORT=19010",
                "LOCAL_GAMMA_MEDIA_EDGE_PORT=19100",
                "LOCAL_GAMMA_HTTPS_PORT=18443",
                "LOCAL_GAMMA_ADMIN_PORT=12019",
                "LOCAL_GAMMA_CHAT_PORT=19200",
                "LOCAL_GAMMA_USER_PORT=19210",
                "LOCAL_GAMMA_CONTENT_PORT=19220",
                "LOCAL_GAMMA_ASSISTANT_PORT=19230",
                "LOCAL_GAMMA_REC_MODEL_PORT=19240",
                "LOCAL_GAMMA_PRODUCT_OPS_SERVICE_PORT=19250",
                "LOCAL_GAMMA_TAG_PORT=19270",
                "LOCAL_GAMMA_ENTITY_PORT=19290",
                "LOCAL_GAMMA_INTEGRATION_PORT=19310",
                "LOCAL_GAMMA_NOTIFICATION_PORT=19320",
                "LOCAL_GAMMA_REALTIME_PORT=19340",
                "LOCAL_GAMMA_RTC_PORT=19350",
                "LOCAL_GAMMA_POSTGRES_PORT=19400",
                "LOCAL_GAMMA_MONGO_PORT=19410",
                "LOCAL_GAMMA_REDIS_PORT=19420",
            ]
        )
    (output_root / "stack.env").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_observability_tree(
    output_root: Path,
    plane_name: str,
) -> dict[str, Any] | None:
    plane = _plane_spec(plane_name)
    runtime = plane.get("rootlessObservabilityRuntime")
    if runtime is None:
        return None
    if not isinstance(runtime, dict):
        raise SystemExit(
            f"FAIL: {plane_name}.rootlessObservabilityRuntime must be an object"
        )

    directory = Path(str(runtime.get("composeDirectory") or ""))
    compose_file = str(runtime.get("composeFile") or "").strip()
    systemd_unit_file = str(runtime.get("systemdUnitFile") or "").strip()
    runtime_env_file = str(runtime.get("runtimeEnvFile") or "").strip()
    service_network_name = str(runtime.get("serviceNetworkName") or "").strip()
    if (
        not directory.parts
        or directory.is_absolute()
        or ".." in directory.parts
        or not compose_file
        or Path(compose_file).name != compose_file
        or not systemd_unit_file.endswith(".service")
        or Path(systemd_unit_file).name != systemd_unit_file
        or not runtime_env_file
        or Path(runtime_env_file).name != runtime_env_file
        or not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{1,62}", service_network_name)
    ):
        raise SystemExit(
            "FAIL: rootlessObservabilityRuntime compose directory/file must be safe"
        )
    source_compose = OBSERVABILITY_SOURCE_ROOT / compose_file
    required_files = (
        source_compose,
        OBSERVABILITY_SOURCE_ROOT / "prometheus.yml",
        OBSERVABILITY_SOURCE_ROOT / "alertmanager.yml",
        OBSERVABILITY_SOURCE_ROOT / "otel-collector.yml",
    )
    if any(not path.is_file() for path in required_files):
        missing = ", ".join(
            str(path.relative_to(ROOT))
            for path in required_files
            if not path.is_file()
        )
        raise SystemExit(f"FAIL: observability source is incomplete: {missing}")
    alerts = OBSERVABILITY_SOURCE_ROOT / "alerts"
    if not alerts.is_dir():
        raise SystemExit(f"FAIL: observability alerts directory is missing: {alerts}")

    destination = output_root / directory
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for source in required_files:
        shutil.copy2(source, destination / source.name)
    shutil.copytree(alerts, destination / "alerts")
    (destination / runtime_env_file).write_text(
        f"PROD_SERVICE_NETWORK={service_network_name}\n",
        encoding="utf-8",
    )
    compose_root = str(plane.get("composeProjectRoot") or "").strip()
    credentials_root = str(plane.get("credentialsPath") or "").strip()
    credentials_env = str(runtime.get("credentialsEnvFile") or "").strip()
    if not (
        compose_root.startswith("/")
        and credentials_root.startswith("/")
        and credentials_env
        and not Path(credentials_env).is_absolute()
        and ".." not in Path(credentials_env).parts
    ):
        raise SystemExit("FAIL: observability systemd paths must be absolute/safe")
    unit_dir = destination / "systemd"
    unit_dir.mkdir()
    credentials_env_path = f"{credentials_root.rstrip('/')}/{credentials_env}"
    unit_dir.joinpath(systemd_unit_file).write_text(
        "\n".join(
            [
                "[Unit]",
                "Description=Quwoquan production observability rootless stack",
                "Wants=network-online.target",
                "After=network-online.target",
                "",
                "[Service]",
                "Type=oneshot",
                "RemainAfterExit=yes",
                f"WorkingDirectory={compose_root}",
                (
                    "ExecStart=/usr/bin/podman compose --env-file stack.env "
                    f"--env-file {directory.as_posix()}/{runtime_env_file} "
                    f"--env-file {credentials_env_path} "
                    f"-f {directory.as_posix()}/{compose_file} "
                    "-p quwoquan-observability-prod up -d --remove-orphans"
                ),
                (
                    "ExecStop=/usr/bin/podman compose --env-file stack.env "
                    f"--env-file {directory.as_posix()}/{runtime_env_file} "
                    f"--env-file {credentials_env_path} "
                    f"-f {directory.as_posix()}/{compose_file} "
                    "-p quwoquan-observability-prod down"
                ),
                "",
                "[Install]",
                "WantedBy=default.target",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "composeDirectory": directory.as_posix(),
        "composeFile": compose_file,
        "systemdUnitFile": systemd_unit_file,
        "runtimeEnvFile": runtime_env_file,
        "serviceNetworkName": service_network_name,
        "credentialsEnvFile": str(runtime.get("credentialsEnvFile") or ""),
        "requiredEnvironment": list(runtime.get("requiredEnvironment") or []),
        "healthURLs": list(runtime.get("healthURLs") or []),
    }


def main() -> int:
    args = parse_args()
    plane = _plane_spec(args.plane)
    compose_template = ROOT / str(plane.get("rootlessComposeTemplate") or "")
    if not compose_template.is_file():
        raise SystemExit(f"FAIL: missing compose template: {compose_template}")

    governed = [str(item) for item in plane.get("rootlessGovernedComposeServices") or []]
    support = [str(item) for item in plane.get("rootlessSupportComposeServices") or []]
    config_services = [str(item) for item in plane.get("rootlessConfigServices") or []]
    credentials_root = str(plane.get("credentialsPath") or "").strip()
    runtime_credentials = dict(plane.get("rootlessRuntimeCredentials") or {})
    selected = governed + support
    if not selected:
        raise SystemExit(f"FAIL: plane {args.plane} missing rootless compose service list")

    layout = plane.get("rootlessRuntimeLayout") or {}
    config_root = str(layout.get("configRoot") or "runtime/config-root")
    caddyfile_path = str(layout.get("caddyfile") or "runtime/Caddyfile")
    media_state_ref = str(layout.get("mediaStateRef") or "").strip()
    if not media_state_ref:
        raise SystemExit("FAIL: rootlessRuntimeLayout.mediaStateRef is required")
    media_ref_path = Path(media_state_ref)
    if media_ref_path.is_absolute() or ".." in media_ref_path.parts:
        raise SystemExit("FAIL: rootlessRuntimeLayout.mediaStateRef must be a safe state-relative path")
    media_root = str((resolve_target_local_dir("prod-hosted") / media_ref_path).resolve())
    legal_root = str(layout.get("legalStaticRoot") or "runtime/legal-static")
    portal_root = str(layout.get("portalStaticRoot") or "runtime/portal")
    model_cache_root = str(layout.get("modelCacheRoot") or "runtime/model-cache")
    if Path(config_root).is_absolute():
        raise SystemExit("FAIL: rootlessRuntimeLayout.configRoot must remain relative")
    if Path(caddyfile_path).is_absolute():
        raise SystemExit("FAIL: rootlessRuntimeLayout.caddyfile must remain relative")
    if Path(legal_root).is_absolute():
        raise SystemExit("FAIL: rootlessRuntimeLayout.legalStaticRoot must remain relative")
    if Path(portal_root).is_absolute():
        raise SystemExit("FAIL: rootlessRuntimeLayout.portalStaticRoot must remain relative")
    if Path(model_cache_root).is_absolute():
        raise SystemExit("FAIL: rootlessRuntimeLayout.modelCacheRoot must remain relative")

    output_root = Path(args.output_dir).expanduser().resolve()
    _require_external_deployment_root(output_root)
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    Path(media_root).mkdir(parents=True, exist_ok=True)
    legal_package_public = (
        legal_static_deployment_package_dir("prod", target="prod-hosted")
        / "current"
        / "public"
    )
    legal_output_root = output_root / legal_root
    if legal_output_root.exists():
        shutil.rmtree(legal_output_root)
    if legal_package_public.is_dir():
        shutil.copytree(legal_package_public, legal_output_root)
    else:
        legal_output_root.mkdir(parents=True, exist_ok=True)
    # 运维运营 Portal 静态站点：只消费 build_portal_release.py 发布的不可变
    # release 产物；缺失时保留空目录（Caddy 返回 404，不回退 dev server）。
    portal_release_dist = (
        portal_deployment_package_dir("prod", target="prod-hosted")
        / "current"
        / "dist"
    )
    portal_output_root = output_root / portal_root
    if portal_output_root.exists():
        shutil.rmtree(portal_output_root)
    if portal_release_dist.is_dir():
        shutil.copytree(portal_release_dist, portal_output_root)
    else:
        portal_output_root.mkdir(parents=True, exist_ok=True)
    (output_root / model_cache_root).mkdir(parents=True, exist_ok=True)

    template = _load_yaml(compose_template)
    services = template.get("services") or {}
    rendered_services: dict[str, Any] = {}
    selected_names = set(selected)
    governed_names = set(governed)
    observability_config = plane.get("rootlessObservabilityRuntime") or {}
    service_network_name = str(
        observability_config.get("serviceNetworkName") or ""
    ).strip()
    for service_name in selected:
        raw = services.get(service_name)
        if raw is None:
            raise SystemExit(
                f"FAIL: compose template missing selected service {service_name}: {compose_template}"
            )
        rendered = _rewrite_service(
            service_name,
            raw,
            selected_names,
            image_version=args.image_version,
            versioned_image=service_name in governed_names,
            instance=args.instance,
            config_root=config_root,
            media_root=media_root,
            legal_root=legal_root,
            portal_root=portal_root,
            caddyfile_path=caddyfile_path,
            model_cache_root=model_cache_root,
            credentials_root=credentials_root,
            runtime_credentials=runtime_credentials,
        )
        if service_network_name:
            rendered["networks"] = ["service-plane"]
        rendered_services[service_name] = rendered

    compose_payload: dict[str, Any] = {"services": rendered_services}
    if service_network_name:
        compose_payload["networks"] = {
            "service-plane": {"name": service_network_name}
        }
    top_level_volumes = dict(template.get("volumes") or {})
    if any(name in RUNTIME_LOG_EXPORT_SERVICES for name in rendered_services):
        top_level_volumes.setdefault("runtime-log-spool", {})
    filtered = _filter_top_level_volumes(rendered_services, top_level_volumes)
    if filtered:
        compose_payload["volumes"] = filtered

    compose_file_name = (
        ((plane.get("rootlessRuntimeLayout") or {}).get("composeFile"))
        or "docker-compose.prod-hosted.yaml"
    )
    compose_out = output_root / str(compose_file_name)
    compose_out.write_text(
        yaml.safe_dump(compose_payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    observability_runtime = _write_observability_tree(output_root, args.plane)
    config_sources = _write_config_tree(
        config_services=config_services,
        config_version=args.config_version,
        output_root=output_root,
    )
    _write_caddyfile(output_root, args.instance, args.rollout_stage)
    _write_env_file(output_root, args.config_version, args.image_version, args.instance)

    report = {
        "plane": args.plane,
        "host": args.host or "",
        "composeTemplate": str(compose_template.relative_to(ROOT)),
        "composeFile": str(compose_out.relative_to(ROOT) if compose_out.is_relative_to(ROOT) else compose_out),
        "instance": args.instance,
        "governedComposeServices": governed,
        "supportComposeServices": support,
        "configServices": config_services,
        "configVersion": args.config_version,
        "outputDir": str(output_root),
        "sourceRevision": _git_revision(),
        "configSources": config_sources,
        "mediaStateRef": media_state_ref,
        "mediaRoot": media_root,
        "legalStaticRoot": legal_root,
        "legalStaticSource": str(legal_package_public),
        "portalStaticRoot": portal_root,
        "portalStaticSource": str(portal_release_dist),
        "observabilityRuntime": observability_runtime,
    }
    (output_root / "provenance.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
