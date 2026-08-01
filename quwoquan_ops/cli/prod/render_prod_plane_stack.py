#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.output_paths import deployment_render_dir
from quwoquan_ops.cli.lib.output_paths import deployment_target_path
from quwoquan_ops.cli.lib.output_paths import legal_static_deployment_package_dir
from quwoquan_ops.cli.lib.output_paths import portal_deployment_package_dir
from quwoquan_ops.cli.lib.output_paths import remove_deployment_tree
from quwoquan_ops.cli.lib.output_paths import resolve_deployment_target_path
from quwoquan_ops.cli.lib.output_paths import service_deployment_package_dir
from quwoquan_ops.cli.lib.output_paths import target_local_dir as resolve_target_local_dir
from quwoquan_ops.cli.lib.output_paths import web_deployment_package_dir
from quwoquan_ops.cli.lib.environment_topology import get_target, load_environment_topology
from quwoquan_ops.cli.lib.compose_layout import domain_service_compose_files

try:
    import yaml
except ImportError:  # pragma: no cover
    raise SystemExit("FAIL: PyYAML required")

ACCESS_MANIFEST = ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml"
OBSERVABILITY_SOURCE_ROOT = ROOT / "quwoquan_ops/observability/monitoring"
DEFAULT_OUTPUT_ROOT = deployment_render_dir(
    "prod",
    target="prod-hosted",
    name="service-prod",
)

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
    "api-edge",
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

PREVALIDATION_AUTH_SECRET_KEYS = (
    "AUTH_JWT_SECRET",
    "AUTH_DEVICE_TICKET_SECRET",
    "OTP_CODE_REF_KEY",
    "QWQ_PUSH_TOKEN_ENCRYPTION_KEY",
    "CONTENT_ACCOUNT_CLOSURE_SUBJECT_HMAC_SECRET",
    "QWQ_COMPOSE_OBJECT_STORAGE_CDN_SIGN_KEY",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render prod plane rootless stack from truth sources.",
    )
    parser.add_argument("--plane", default="service", choices=["service", "edge"])
    parser.add_argument(
        "--instance",
        default="prod",
        choices=["gray", "prod", "prevalidate"],
    )
    parser.add_argument(
        "--rollout-stage",
        default="full",
        choices=["gray-initial", "carry-on", "full"],
    )
    parser.add_argument("--candidate-digest", required=True)
    parser.add_argument(
        "--image-transport-tag",
        default=os.environ.get("IMAGE_TRANSPORT_TAG", ""),
    )
    parser.add_argument(
        "--release-evidence-digest",
        default=os.environ.get("RELEASE_EVIDENCE_DIGEST", ""),
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help=(
            "resolver-derived target-scoped render directory; defaults to "
            "QWQ_DEPLOY_WORK_ROOT/prod-hosted/rendered/<plane>-<instance>"
        ),
    )
    parser.add_argument("--host", default="")
    parser.add_argument(
        "--data-mode",
        default="external",
        choices=["isolated", "external"],
    )
    parser.add_argument(
        "--prevalidate-scope",
        default="",
        choices=["", "first-party"],
    )
    return parser.parse_args()


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"FAIL: {path} must parse as object")
    return data


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _prevalidation_secret_environment() -> dict[str, str]:
    """Return target-local, non-release auth material shared by service/edge.

    The file lives in the external deployment workspace, is never included in
    provenance, and is intentionally separate from the formal prod credentials
    directory.  Both planes must share the JWT/device-ticket keys so an edge
    request can be authenticated by the first-party service plane.
    """

    secret_path = deployment_target_path(
        "prod-hosted", "secrets", "prevalidation-auth.env"
    )
    values: dict[str, str] = {}
    if secret_path.is_file():
        if secret_path.stat().st_mode & 0o077:
            raise SystemExit(
                f"FAIL: prevalidation auth material must be mode 0600: {secret_path}"
            )
        for line in secret_path.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key in PREVALIDATION_AUTH_SECRET_KEYS and value:
                values[key] = value
    if set(values) != set(PREVALIDATION_AUTH_SECRET_KEYS):
        values = {
            "AUTH_JWT_SECRET": secrets.token_urlsafe(48),
            "AUTH_DEVICE_TICKET_SECRET": secrets.token_urlsafe(48),
            "OTP_CODE_REF_KEY": base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
            "QWQ_PUSH_TOKEN_ENCRYPTION_KEY": base64.b64encode(
                secrets.token_bytes(32)
            ).decode("ascii"),
            "CONTENT_ACCOUNT_CLOSURE_SUBJECT_HMAC_SECRET": secrets.token_urlsafe(48),
            "QWQ_COMPOSE_OBJECT_STORAGE_CDN_SIGN_KEY": secrets.token_urlsafe(48),
        }
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        secret_path.write_text(
            "\n".join(f"{key}={values[key]}" for key in PREVALIDATION_AUTH_SECRET_KEYS)
            + "\n",
            encoding="utf-8",
        )
        secret_path.chmod(0o600)
    return values


def _canonical_config_bytes(payload: dict[str, Any]) -> bytes:
    return yaml.safe_dump(
        payload,
        allow_unicode=True,
        sort_keys=True,
        width=120,
    ).encode("utf-8")


def _project_isolated_prevalidation_config(
    path: Path,
) -> dict[str, Any]:
    """Project prod config onto a single-node, empty Redis data plane.

    This is a new immutable config snapshot with its own digest. It never
    changes the package or claims to prove the formal prod data topology.
    """

    payload = _load_yaml(path)
    changes: list[str] = []
    redis = payload.get("redis")
    if isinstance(redis, dict):
        for role, role_config in redis.items():
            if not isinstance(role_config, dict):
                continue
            if role_config.get("mode") != "standalone":
                role_config["mode"] = "standalone"
                changes.append(f"redis.{role}.mode=standalone")
            if role_config.get("tls") is not False:
                role_config["tls"] = False
                changes.append(f"redis.{role}.tls=false")
            if role_config.get("addr") != "redis:6379":
                role_config["addr"] = "redis:6379"
                changes.append(f"redis.{role}.addr=redis:6379")
            if "addrs" in role_config:
                role_config.pop("addrs")
                changes.append(f"redis.{role}.addrs=removed")
    config = payload.setdefault("config", {})
    if not isinstance(config, dict):
        raise SystemExit(f"FAIL: config section is not an object: {path}")
    config.pop("version", None)
    projected_version = "sha256:" + hashlib.sha256(
        _canonical_config_bytes(payload)
    ).hexdigest()
    config["version"] = projected_version
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )
    return {
        "projectedConfigurationDigest": projected_version,
        "projectedConfigDigest": _sha256(path),
        "changes": changes,
    }


def _resolve_render_output_dir(
    configured_output: str | Path | None,
    *,
    plane: str,
    instance: str,
) -> Path:
    render_name = f"{plane}-{instance}"
    try:
        return resolve_deployment_target_path(
            configured_output,
            target="prod-hosted",
            segments=("rendered", render_name),
        )
    except ValueError as exc:
        raise SystemExit(
            "FAIL: prod deployment rendering must use the QWQ_DEPLOY_WORK_ROOT "
            "resolver-derived prod-hosted target directory"
        ) from exc


def _require_external_deployment_root(output_root: Path) -> None:
    """Compatibility guard retained for direct local-contract probes."""
    _resolve_render_output_dir(
        output_root,
        plane="service",
        instance="prod",
    )


def _verified_package_config(
    package_dir: Path,
    *,
    release_id: str,
) -> Path:
    report_path = package_dir / "provenance.json"
    config_path = package_dir / "config" / "config.yaml"
    if not report_path.is_file() or not config_path.is_file():
        raise SystemExit(f"FAIL: incomplete autonomous service package: {package_dir}")
    try:
        provenance = json.loads(report_path.read_text(encoding="utf-8"))
        file_digest = provenance["digests"]["config"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"FAIL: invalid package provenance: {report_path}") from exc
    if file_digest != _sha256(config_path):
        raise SystemExit(f"FAIL: package config digest mismatch: {config_path}")
    config_payload = _load_yaml(config_path)
    config_section = config_payload.get("config") if isinstance(config_payload, dict) else None
    embedded_version = (
        str(config_section.get("version") or "")
        if isinstance(config_section, dict)
        else ""
    )
    if provenance.get("configVersion") != embedded_version:
        raise SystemExit(f"FAIL: package CONFIG_VERSION differs from effective config: {report_path}")
    release_evidence = provenance.get("releaseEvidence")
    if not isinstance(release_evidence, dict):
        raise SystemExit(f"FAIL: package release evidence provenance missing: {report_path}")
    if release_evidence.get("candidateId") != release_id:
        raise SystemExit(f"FAIL: package candidate ID mismatch: {report_path}")
    if release_evidence.get("verifiedConfigDigest") != file_digest:
        raise SystemExit(f"FAIL: package release config evidence mismatch: {report_path}")
    manifest_rel = str(release_evidence.get("manifest") or "")
    manifest_path = Path(manifest_rel)
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path
    if (
        not manifest_rel
        or not manifest_path.is_file()
        or release_evidence.get("evidenceFileDigest") != _sha256(manifest_path)
    ):
        raise SystemExit(f"FAIL: package release artifact manifest mismatch: {report_path}")
    return config_path


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


def _prevalidation_spec() -> dict[str, Any]:
    access = _load_yaml(ACCESS_MANIFEST)
    spec = access.get("prevalidation")
    if not isinstance(spec, dict) or spec.get("promotable") is not False:
        raise SystemExit("FAIL: non-promotable prod prevalidation projection is missing")
    return spec


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
    config_version: str,
    release_evidence_digest: str = "",
    versioned_image: bool,
    instance: str,
    config_root: str,
    media_root: str,
    legal_root: str,
    portal_root: str,
    web_root: str,
    caddyfile_path: str,
    model_cache_root: str,
    credentials_root: str = "",
    runtime_credentials: dict[str, Any] | None = None,
    data_mode: str = "external",
    prevalidation_images: dict[str, str] | None = None,
    startup_services: set[str] | None = None,
) -> dict[str, Any]:
    updated = copy.deepcopy(spec)
    updated.pop("build", None)
    if versioned_image:
        if not image_version or image_version == "latest":
            raise SystemExit(f"FAIL: immutable image version required for {name}")
        updated["image"] = f"localhost/quwoquan_service_{name}:{image_version}"
    if name in (prevalidation_images or {}):
        image = str((prevalidation_images or {})[name])
        if re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", image) is None:
            raise SystemExit(f"FAIL: prevalidation support image is not digest-pinned: {name}")
        updated["image"] = image
    # prod 渲染面按 rootlessGovernedComposeServices 显式选择服务，
    # gamma-local 的 compose profile 开关不进入生产 compose。
    updated.pop("profiles", None)
    if name == "gamma-proxy":
        updated["image"] = PROD_CADDY_IMAGE
        public_hosts = _prod_public_hosts()
        proxy_environment = updated.setdefault("environment", {})
        proxy_environment.update(
            {
                "QWQ_PUBLIC_API_HOST": public_hosts["api"],
                "QWQ_PUBLIC_WEB_HOST": public_hosts["publicWeb"],
                "QWQ_PUBLIC_RTC_HOST": public_hosts["rtc"],
                "QWQ_PUBLIC_OPS_HOST": public_hosts["productOps"],
                "QWQ_PUBLIC_CDN_HOST": public_hosts["mediaImage"],
            }
        )
        if instance == "prod":
            updated["ports"] = ["80:80", "443:443", "127.0.0.1:12019:2019"]
            updated["healthcheck"] = {
                "test": [
                    "CMD-SHELL",
                    "wget --no-check-certificate -qO- "
                    f"--header='Host: {public_hosts['api']}' "
                    "https://127.0.0.1/healthz >/dev/null 2>&1",
                ],
                "interval": "10s",
                "timeout": "3s",
                "start_period": "5s",
                "retries": 10,
            }
        elif instance == "prevalidate":
            updated["ports"] = ["39000:80", "127.0.0.1:32019:2019"]
            updated["healthcheck"] = {
                "test": [
                    "CMD-SHELL",
                    "wget -qO- http://127.0.0.1/healthz >/dev/null 2>&1",
                ],
                "interval": "10s",
                "timeout": "3s",
                "start_period": "5s",
                "retries": 10,
            }
        else:
            updated["ports"] = ["29000:80", "127.0.0.1:22019:2019"]
            updated["healthcheck"] = {
                "test": [
                    "CMD-SHELL",
                    "wget -qO- http://127.0.0.1/healthz >/dev/null 2>&1",
                ],
                "interval": "10s",
                "timeout": "3s",
                "start_period": "5s",
                "retries": 10,
            }
    if isinstance(updated.get("depends_on"), dict):
        updated["depends_on"] = {
            dep: dep_spec
            for dep, dep_spec in updated["depends_on"].items()
            if dep in selected and (startup_services is None or dep in startup_services)
        }
        if not updated["depends_on"]:
            updated.pop("depends_on")
    environment = updated.get("environment")
    if isinstance(environment, dict) and "APP_ENV" in environment:
        # Compose fragments carry a gamma-default interpolation expression.
        # A prod renderer must materialize prod explicitly instead of relying
        # on a caller environment that systemd will not necessarily inherit.
        environment["APP_ENV"] = "prod"
    if isinstance(environment, dict):
        if config_version:
            environment["CONFIG_VERSION"] = config_version
        if image_version:
            environment["IMAGE_VERSION"] = image_version
        if name in RUNTIME_LOG_EXPORT_SERVICES and release_evidence_digest:
            environment["RELEASE_EVIDENCE_DIGEST"] = release_evidence_digest
        if instance == "prevalidate":
            environment["QWQ_NONPROMOTABLE_PREVALIDATION"] = "first-party"
        environment["OTEL_EXPORTER_OTLP_ENDPOINT"] = (
            "${OTEL_EXPORTER_OTLP_ENDPOINT:-otel-collector:4318}"
        )
        if name in RUNTIME_LOG_EXPORT_SERVICES:
            # 所有受管服务在成功读取、校验当前发布包配置后，以服务+环境绑定的
            # 短期凭据 ACK。固定实例身份来自渲染器，禁止使用容器随机 hostname
            # 使 rollout convergence 无法判断成员完整性。
            cluster_name = f"prod-{instance}-control-a"
            environment["PLATFORM_OPS_BASE_URL"] = "http://platform-ops-service:18088"
            environment["CLUSTER_NAME"] = cluster_name
            environment["SERVICE_INSTANCE_ID"] = (
                f"{name}-{cluster_name}-0"
            )
            if name == "platform-ops-service":
                environment["CONFIG_ACK_REQUIRED_INSTANCES"] = ",".join(
                    f"{service}-{cluster_name}-0"
                    for service in sorted(RUNTIME_LOG_EXPORT_SERVICES)
                )
                environment["CONFIG_ACK_MAX_AGE_SECONDS"] = "120"
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
        edge_prevalidation = (
            instance == "prevalidate"
            and data_mode == "isolated"
            and name in {"realtime-gateway", "rtc-service"}
        )
        isolated_local = data_mode == "isolated" and not edge_prevalidation
        mongo_host = "mongodb" if isolated_local else EXTERNAL_DATA_HOST
        mongo_port = (
            27017
            if isolated_local
            else (39410 if edge_prevalidation else EXTERNAL_MONGO_PORT)
        )
        mongo_uri = f"mongodb://{mongo_host}:{mongo_port}/?directConnection=true"
        redis_host = "redis" if isolated_local else EXTERNAL_DATA_HOST
        redis_port = (
            6379
            if isolated_local
            else (39420 if edge_prevalidation else EXTERNAL_REDIS_PORT)
        )
        postgres_host = "postgres" if isolated_local else EXTERNAL_DATA_HOST
        postgres_port = (
            5432
            if isolated_local
            else (39400 if edge_prevalidation else EXTERNAL_POSTGRES_PORT)
        )
        if name == "recommendation-service":
            environment["MONGODB_URI"] = mongo_uri
        if name == "content-service":
            environment["MONGO_URI"] = mongo_uri
            environment["CONTENT_REDIS_REC_ADDR"] = f"{redis_host}:{redis_port}"
            environment["CONTENT_REDIS_GENERAL_ADDR"] = f"{redis_host}:{redis_port}"
        if name == "chat-service":
            environment["MONGO_URI"] = mongo_uri
        if name == "chat-service":
            environment["REDIS_ADDR"] = f"{redis_host}:{redis_port}"
            environment["CHAT_REDIS_REALTIME_ADDR"] = f"{redis_host}:{redis_port}"
            environment["CHAT_REDIS_GENERAL_ADDR"] = f"{redis_host}:{redis_port}"
            environment["CHAT_REDIS_RELIABLE_TASK_ADDR"] = f"{redis_host}:{redis_port}"
        if name == "user-service":
            environment["POSTGRES_DSN"] = (
                f"postgres://quwoquan:quwoquan@{postgres_host}:{postgres_port}/"
                "quwoquan?sslmode=disable"
            )
            environment["MONGODB_URI"] = mongo_uri
        if name == "user-service":
            environment["REDIS_ADDR"] = f"{redis_host}:{redis_port}"
        if name == "assistant-service":
            environment["MONGODB_URI"] = mongo_uri
            environment["REDIS_GENERAL_ADDR"] = f"{redis_host}:{redis_port}"
            environment["REDIS_REC_ADDR"] = f"{redis_host}:{redis_port}"
            if instance == "prevalidate":
                environment.update(
                    {
                        "ASSISTANT_MODEL_COMPLETION_URL": "https://model-provider-unavailable.invalid/v1/chat/completions",
                        "ASSISTANT_MODEL_API_KEY": "provider-unavailable",
                        "ASSISTANT_PUBLIC_SEARCH_URL": "https://search-provider-unavailable.invalid/",
                        "ASSISTANT_WEATHER_GEOCODING_URL": "https://weather-provider-unavailable.invalid/geocode",
                        "ASSISTANT_WEATHER_FORECAST_URL": "https://weather-provider-unavailable.invalid/forecast",
                        "ASSISTANT_FINANCE_CHART_URL": "https://finance-provider-unavailable.invalid/chart",
                    }
                )
        if name == "product-ops-service":
            environment["POSTGRES_DSN"] = (
                f"postgres://quwoquan:quwoquan@{postgres_host}:{postgres_port}/"
                "quwoquan?sslmode=disable"
            )
            environment["MONGO_URI"] = mongo_uri
            environment["PRODUCT_OPS_REDIS_REC_ADDR"] = f"{redis_host}:{redis_port}"
            environment["PRODUCT_OPS_REDIS_GENERAL_ADDR"] = f"{redis_host}:{redis_port}"
            environment["PROMETHEUS_URL"] = "${PRODUCT_OPS_PROMETHEUS_URL:-http://prometheus:9090}"
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
                f"postgres://quwoquan:quwoquan@{postgres_host}:{postgres_port}/"
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
            environment["REDIS_ADDR"] = f"{redis_host}:{redis_port}"
            environment["TAG_MONGO_URI"] = mongo_uri
        if name == "entity-service":
            environment["ENTITY_MONGO_URI"] = mongo_uri
            # prod-hosted 首波 service plane 不含 elasticsearch（search-service 未迁入），
            # 关闭 write-time 索引投影；主页读写主链路（Mongo homepages 权威集合）不受影响。
            if data_mode == "isolated":
                environment["SEARCH_ES_ENABLED"] = "true"
                environment["SEARCH_ES_ENDPOINTS"] = "http://elasticsearch:9200"
            else:
                environment["SEARCH_ES_ENABLED"] = "false"
                environment.pop("SEARCH_ES_ENDPOINTS", None)
        if name == "integration-service":
            environment["INTEGRATION_MONGO_URI"] = mongo_uri
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
        if instance == "prevalidate" and name == "user-service":
            environment.update(
                {
                    "ALIYUN_DYPNS_ENDPOINT": "provider-unavailable.invalid",
                    "ALIYUN_DYPNS_ACCESS_KEY_ID": "provider-unavailable",
                    "ALIYUN_DYPNS_ACCESS_KEY_SECRET": "provider-unavailable",
                    "WECHAT_OAUTH_TOKEN_URL": "https://login-provider-unavailable.invalid/wechat/token",
                    "WECHAT_OAUTH_USER_INFO_URL": "https://login-provider-unavailable.invalid/wechat/userinfo",
                    "ALIPAY_OAUTH_TOKEN_URL": "https://login-provider-unavailable.invalid/alipay/token",
                    "ALIPAY_OAUTH_USER_INFO_URL": "https://login-provider-unavailable.invalid/alipay/userinfo",
                    "QQ_OAUTH_USER_INFO_URL": "https://login-provider-unavailable.invalid/qq/userinfo",
                    "WECHAT_OAUTH_APP_ID": "provider-unavailable",
                    "WECHAT_OAUTH_APP_SECRET": "provider-unavailable",
                    "ALIPAY_OAUTH_APP_ID": "provider-unavailable",
                    "ALIPAY_OAUTH_APP_PRIVATE_KEY_PEM": "provider-unavailable",
                    "ALIPAY_OAUTH_PLATFORM_PUBLIC_KEY_PEM": "provider-unavailable",
                    "ALIPAY_OAUTH_MERCHANT_PID": "provider-unavailable",
                    "QQ_OAUTH_APP_ID": "provider-unavailable",
                }
            )
        if instance == "prevalidate" and name == "content-service":
            environment["CONTENT_EMBEDDING_ENDPOINT"] = (
                "https://embedding-provider-unavailable.invalid/v1/embeddings"
            )
            environment["CONTENT_EMBEDDING_API_KEY"] = "provider-unavailable"
        if name == "notification-service":
            environment["NOTIFICATION_MONGO_URI"] = mongo_uri
            environment["NOTIFICATION_REDIS_ADDR"] = (
                f"{redis_host}:{redis_port}"
            )
            environment["NOTIFICATION_REDIS_GENERAL_DB"] = "1"
            environment["NOTIFICATION_REDIS_REALTIME_DB"] = "4"
            environment["NOTIFICATION_REALTIME_BASE_URL"] = (
                f"http://{EXTERNAL_DATA_HOST}:"
                "${LOCAL_GAMMA_REALTIME_PORT:?realtime port is required}"
            )
        if name == "realtime-gateway":
            environment["REALTIME_REDIS_ADDR"] = (
                f"{redis_host}:{redis_port}"
            )
        if name == "rtc-service":
            environment["MONGO_URI"] = mongo_uri
            environment["REDIS_ADDR"] = (
                f"{redis_host}:{redis_port}"
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
    if name not in {"gamma-proxy", "postgres", "mongodb", "mongo-init", "redis", "object-storage", "object-storage-init", "elasticsearch"}:
        extra_hosts = list(updated.get("extra_hosts") or [])
        if f"{EXTERNAL_DATA_HOST}:host-gateway" not in extra_hosts:
            extra_hosts.append(f"{EXTERNAL_DATA_HOST}:host-gateway")
        updated["extra_hosts"] = extra_hosts
    if instance == "prevalidate" and name == "object-storage":
        environment = updated.setdefault("environment", {})
        environment.pop("MINIO_CERTS_DIR", None)
        updated["command"] = ["server", "/data", "--address", ":9000", "--console-address", ":9001"]
        updated["ports"] = ["39440:9000"]
        updated["volumes"] = ["local-gamma-object-storage:/data"]
    if instance == "prevalidate" and name == "object-storage-init":
        updated["volumes"] = []
        updated["entrypoint"] = [
            "/bin/sh",
            "-ec",
            (
                "for attempt in $(seq 1 60); do "
                "if mc alias set qwq http://object-storage:9000 "
                "\"$LOCAL_GAMMA_OBJECT_STORAGE_ACCESS_KEY_ID\" "
                "\"$LOCAL_GAMMA_OBJECT_STORAGE_ACCESS_KEY_SECRET\"; then "
                "mc mb --ignore-existing qwq/$LOCAL_GAMMA_OBJECT_STORAGE_BUCKET; exit 0; "
                "fi; sleep 2; done; exit 1"
            ),
        ]
    volumes = list(updated.get("volumes") or [])
    if name == "gamma-proxy":
        web_mount = f"{_compose_bind_source(web_root)}:/srv/web:ro"
        if web_mount not in volumes:
            volumes.append(web_mount)
        # The prod renderer uses Caddy automatic TLS, while gray/prevalidation
        # expose an internal HTTP-only projection. The gamma-local certificate
        # bind mounts therefore never belong in a rendered prod plane.
        volumes = [
            item
            for item in volumes
            if not (isinstance(item, str) and ":/etc/caddy/tls/" in item)
        ]
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
    if instance == "prevalidate":
        projected_volumes: list[Any] = []
        for item in volumes:
            if not isinstance(item, str):
                projected_volumes.append(item)
                continue
            if ":/etc/qwq-rec-policy/policy.yaml" in item:
                projected_volumes.append(
                    "./runtime/rec-policy/policy.yaml:/etc/qwq-rec-policy/policy.yaml:ro"
                )
                continue
            if ":/app/.qwq_output/env/repo/local/control-plane/process/platform-ops-service" in item:
                projected_volumes.append(
                    "platform-ops-prevalidation-state:"
                    "/app/.qwq_output/env/repo/local/control-plane/process/platform-ops-service"
                )
                continue
            projected_volumes.append(item)
        volumes = projected_volumes
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
    if instance == "prevalidate":
        limits = _prevalidation_spec().get("resourceLimits") or {}
        defaults = limits.get("defaults") or {}
        service_limits = (limits.get("services") or {}).get(name) or {}
        mem_limit = str(
            service_limits.get("memLimit") or defaults.get("memLimit") or ""
        ).strip()
        pids_limit = int(
            service_limits.get("pidsLimit") or defaults.get("pidsLimit") or 0
        )
        if not re.fullmatch(r"[1-9][0-9]*(?:m|g)", mem_limit) or pids_limit <= 0:
            raise SystemExit(
                f"FAIL: prevalidation resource limits are invalid for {name}"
            )
        updated["mem_limit"] = mem_limit
        updated["pids_limit"] = pids_limit
        if name == "elasticsearch":
            environment = updated.setdefault("environment", {})
            environment["ES_JAVA_OPTS"] = "-Xms128m -Xmx128m"
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


def _write_config_tree(
    *,
    config_services: list[str],
    candidate_digest: str,
    output_root: Path,
    isolated_prevalidation: bool = False,
) -> dict[str, Any]:
    config_root = output_root / "runtime" / "config-root"
    sources: dict[str, Any] = {}
    for service in config_services:
        package_dir = service_deployment_package_dir(
            "prod",
            service,
            target="prod-hosted",
        )
        if not package_dir.is_dir():
            raise SystemExit(f"FAIL: missing prod service package for {service}: {package_dir}")
        effective_config = package_dir / "config" / "config.yaml"
        if not effective_config.is_file():
            raise SystemExit(f"FAIL: incomplete service package for {service}: {package_dir}")
        sources[service] = {
            "package": str(package_dir),
            "effectiveConfigDigest": _sha256(effective_config),
        }

        config_src = _verified_package_config(
            package_dir,
            release_id=candidate_digest,
        )
        config_target = config_root / f"{service}.yaml"
        config_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(config_src, config_target)
        provenance = json.loads((package_dir / "provenance.json").read_text(encoding="utf-8"))
        sources[service]["configurationDigest"] = provenance["configVersion"]
        if isolated_prevalidation:
            projection = _project_isolated_prevalidation_config(config_target)
            sources[service]["prevalidationProjection"] = projection
            sources[service]["configurationDigest"] = projection[
                "projectedConfigurationDigest"
            ]

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
    routing_policy_src = ROOT / "quwoquan_ops" / "environments" / "prod" / "rollout" / "routing_policy.yaml"
    if not routing_policy_src.is_file():
        raise SystemExit(f"FAIL: missing gray routing policy: {routing_policy_src}")
    routing_target = config_root / "gray-routing" / "policy.yaml"
    routing_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(routing_policy_src, routing_target)
    sources["gray-routing"] = {
        "package": str(routing_policy_src),
        "policyDigest": _sha256(routing_policy_src),
    }
    if isolated_prevalidation:
        policy_source = (
            ROOT
            / "quwoquan_service/services/content-service/resources/policies/content/post/"
            "recommendation_policy.yaml"
        )
        if not policy_source.is_file():
            raise SystemExit(f"FAIL: missing prevalidation recommendation policy: {policy_source}")
        policy_target = output_root / "runtime" / "rec-policy" / "policy.yaml"
        policy_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(policy_source, policy_target)
        sources["prevalidationProjection"] = {
            "promotable": False,
            "releaseEvidenceEligible": False,
            "reason": "single-node empty data projection",
            "recommendationPolicySourceDigest": _sha256(policy_target),
        }
    return sources


def _prod_public_hosts() -> dict[str, str]:
    """从环境拓扑真相源解析生产域名，禁止生产 Caddy 回退本地域名或 IP。"""
    from urllib.parse import urlparse

    topology = load_environment_topology()
    public_bases = (
        ((topology.get("targets") or {}).get("prod-hosted") or {}).get("publicBases")
        or {}
    )
    hosts: dict[str, str] = {}
    for key in (
        "api",
        "realtime",
        "rtc",
        "productOps",
        "publicWeb",
        "legal",
        "appDownload",
        "mediaAvatar",
        "mediaImage",
        "mediaUpload",
    ):
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
    policy_path = ROOT / "quwoquan_ops" / "environments" / "prod" / "rollout" / "routing_policy.yaml"
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
    }
    for dimension in ("provinces", "carriers"):
        if any(str(item).strip() for item in (dimensions.get(dimension) or [])):
            raise SystemExit(
                "FAIL: province/carrier gray routing requires a trusted edge "
                "attestation pipeline; client-supplied headers are forbidden"
            )
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
}

(public_sim_tls) {
\ttls {$QWQ_PUBLIC_TLS_CERT_FILE} {$QWQ_PUBLIC_TLS_KEY_FILE}
}

(media_cors) {
\theader {
\t\tAccess-Control-Allow-Origin "*"
\t\tAccess-Control-Allow-Methods "GET, HEAD, OPTIONS"
\t\tAccess-Control-Allow-Headers "*"
\t\tCross-Origin-Resource-Policy "cross-origin"
\t\t?Cache-Control "no-store"
\t}
\t@immutable_public_media {
\t\tpath_regexp immutable_public_media ^/media/(?:avatar|image|video|background|attachment)/s/(?:[^/]+/)+v[1-9][0-9]*/(?:[^/]+/)*[^/]+$
\t\tvars_regexp canonical_media_query {http.request.uri.query} ^$
\t}
\theader @immutable_public_media {
\t\tCache-Control "public, max-age=31536000, immutable"
\t\tX-QWQ-Media-Cache-Key "{http.request.uri.path}"
\t}
}

(business_api_edge) {
\treverse_proxy api-edge:18079 {
\t\theader_up X-Edge-Client-IP {remote_host}
\t}
}

api.sim.quwoquan.com {
\timport public_sim_tls
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
\t\timport business_api_edge
\t}
}

ops.sim.quwoquan.com {
\timport public_sim_tls
\thandle /healthz {
\t\timport business_api_edge
\t}
\thandle /ops/* {
\t\timport business_api_edge
\t}
\thandle /control-plane/product/* {
\t\timport business_api_edge
\t}
\thandle /control-plane/platform/* {
\t\timport business_api_edge
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

cdn.sim.quwoquan.com,
cdn.sim.quwoquan.com,
cdn.sim.quwoquan.com,
upload.sim.quwoquan.com {
\timport public_sim_tls
\timport media_cors
\troot * /srv/media
\tfile_server
}

:80 {
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
\t\timport business_api_edge
\t}
}
"""
    if instance in {"gray", "prevalidate"}:
        direct_http = caddy_text.rfind("\n:80 {")
        if direct_http < 0:
            raise SystemExit("FAIL: gray Caddy HTTP route block is missing")
        public_sites = caddy_text.find("\napi.sim.quwoquan.com {")
        if public_sites < 0:
            raise SystemExit("FAIL: gray Caddy canonical snippet preamble is missing")
        caddy_text = (
            caddy_text[:public_sites].rstrip()
            + "\n\n"
            + caddy_text[direct_http + 1 :]
        )
    else:
        caddy_text = caddy_text.replace(
            "\n(public_sim_tls) {\n\t"
            "tls {$QWQ_PUBLIC_TLS_CERT_FILE} {$QWQ_PUBLIC_TLS_KEY_FILE}\n}\n",
            "",
            1,
        ).replace("\timport public_sim_tls\n", "")
        api_authorities = list(
            dict.fromkeys((public_hosts["api"], public_hosts["realtime"]))
        )
        api_sites = f"{', '.join(api_authorities)} {{"
        caddy_text = caddy_text.replace(
            "api.sim.quwoquan.com {",
            api_sites,
            1,
        )
        caddy_text = caddy_text.replace(
            "ops.sim.quwoquan.com {",
            f"{public_hosts['productOps']} {{",
            1,
        )
        media_site = f"""{public_hosts['mediaImage']} {{
\timport prod_security
\thandle /download* {{
\t\timport business_api_edge
\t}}
\thandle {{
\t\timport media_cors
\t\troot * /srv/media
\t\tfile_server
\t}}
}}"""
        caddy_text = caddy_text.replace(
            "cdn.sim.quwoquan.com,\n"
            "cdn.sim.quwoquan.com,\n"
            "cdn.sim.quwoquan.com,\n"
            "upload.sim.quwoquan.com {\n"
            "\timport media_cors\n"
            "\troot * /srv/media\n"
            "\tfile_server\n"
            "}",
            media_site,
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
        web_site = f"""
www.quwoquan.com {{
\timport prod_security
\tredir https://{public_hosts['publicWeb']}{{uri}} 308
}}

{public_hosts['publicWeb']} {{
\timport prod_security
\tencode zstd gzip
\thandle_path /api/* {{
\t\timport business_api_edge
\t}}
\thandle /ops/app-recovery/version {{
\t\timport business_api_edge
\t}}
\thandle /legal/manifest.json {{
\t\theader Content-Type "application/json"
\t\troot * /srv/legal
\t\tfile_server
\t}}
\thandle /legal/* {{
\t\theader Content-Type "text/html; charset=utf-8"
\t\troot * /srv/legal
\t\tfile_server
\t}}
\t@immutable path /assets/* /canvaskit/* /icons/* /fonts/*
\theader @immutable Cache-Control "public, max-age=31536000, immutable"
\t@html path / *.html
\theader @html Content-Type "text/html; charset=utf-8"
\thandle {{
\t\theader {{
\t\t\tContent-Security-Policy "default-src 'self'; connect-src 'self' https: wss:; img-src 'self' data: blob: https:; media-src 'self' blob: https:; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; worker-src 'self' blob:; manifest-src 'self'; frame-ancestors 'none'"
\t\t}}
\t\troot * /srv/web
\t\ttry_files {{path}} /index.html
\t\tfile_server
\t}}
}}
"""
        for site in (
            api_sites,
            f"{public_hosts['productOps']} {{",
        ):
            caddy_text = caddy_text.replace(site, site + "\n\timport prod_security", 1)
        direct_http = caddy_text.rfind("\n:80 {")
        if direct_http < 0:
            raise SystemExit("FAIL: prod Caddy direct HTTP fallback block is missing")
        caddy_text = (
            caddy_text[:direct_http].rstrip()
            + "\n\n"
            + web_site
        )
    if gray_routing_block:
        # 灰度路由 matcher 必须在 API handle 之前：命中维度的请求整体转发到
        # gray 栈 edge；未命中继续走本栈稳定服务。
        caddy_text = caddy_text.replace(
            "\thandle {\n\t\timport business_api_edge\n\t}",
            gray_routing_block
            + "\thandle {\n\t\timport business_api_edge\n\t}",
            1,
        )
    target.write_text(caddy_text, encoding="utf-8")


def _write_env_file(
    output_root: Path,
    candidate_digest: str,
    image_transport_tag: str,
    instance: str,
) -> None:
    from urllib.parse import urlsplit, urlunsplit

    public_bases = (
        get_target(load_environment_topology(), "prod-hosted").get("publicBases")
        or {}
    )
    public_hosts = _prod_public_hosts()
    media_delivery = urlsplit(str(public_bases["mediaImage"]))
    lines = [
        f"LOCAL_GAMMA_CONFIG_VERSION={candidate_digest}",
        f"LOCAL_GAMMA_IMAGE_VERSION={image_transport_tag}",
        (
            "LOCAL_GAMMA_REALTIME_GATEWAY_IMAGE="
            f"localhost/quwoquan_service_realtime-gateway:{image_transport_tag}"
        ),
        (
            "LOCAL_GAMMA_RTC_SERVICE_IMAGE="
            f"localhost/quwoquan_service_rtc-service:{image_transport_tag}"
        ),
        f"LOCAL_GAMMA_TLS_MODE={'internal' if instance in {'gray', 'prevalidate'} else 'automatic'}",
        "QWQ_COMPOSE_MEDIA_DELIVERY_BASE_URL="
        + urlunsplit((media_delivery.scheme, media_delivery.netloc, "", "", "")),
        "QWQ_COMPOSE_MEDIA_UPLOAD_BASE_URL=" + str(public_bases["mediaUpload"]),
        "QWQ_COMPOSE_PUBLIC_WEB_BASE_URL=" + str(public_bases["publicWeb"]),
        "QWQ_COMPOSE_MEDIA_AVATAR_BASE_URL=" + str(public_bases["mediaAvatar"]),
        "QWQ_PUBLIC_API_HOST=" + public_hosts["api"],
        "QWQ_PUBLIC_WEB_HOST=" + public_hosts["publicWeb"],
        "QWQ_PUBLIC_RTC_HOST=" + public_hosts["rtc"],
        "QWQ_PUBLIC_OPS_HOST=" + public_hosts["productOps"],
        "QWQ_PUBLIC_CDN_HOST=" + public_hosts["mediaImage"],
    ]
    if instance == "prevalidate":
        auth = _prevalidation_secret_environment()
        otp_key_version = "prod-hosted-prevalidation-k1"
        lines.extend(
            [
                "LOCAL_GAMMA_HTTP_PORT=39000",
                "LOCAL_GAMMA_PRODUCT_OPS_PORT=39010",
                "LOCAL_GAMMA_MEDIA_EDGE_PORT=39100",
                "LOCAL_GAMMA_HTTPS_PORT=38443",
                "LOCAL_GAMMA_ADMIN_PORT=32019",
                "LOCAL_GAMMA_CHAT_PORT=39200",
                "LOCAL_GAMMA_USER_PORT=39210",
                "LOCAL_GAMMA_CONTENT_PORT=39220",
                "LOCAL_GAMMA_ASSISTANT_PORT=39230",
                "LOCAL_GAMMA_REC_MODEL_PORT=39240",
                "LOCAL_GAMMA_PRODUCT_OPS_SERVICE_PORT=39250",
                "LOCAL_GAMMA_TAG_PORT=39270",
                "LOCAL_GAMMA_ENTITY_PORT=39290",
                "LOCAL_GAMMA_INTEGRATION_PORT=39310",
                "LOCAL_GAMMA_NOTIFICATION_PORT=39320",
                "LOCAL_GAMMA_REALTIME_PORT=39340",
                "LOCAL_GAMMA_RTC_PORT=39350",
                "LOCAL_GAMMA_POSTGRES_PORT=39400",
                "LOCAL_GAMMA_MONGO_PORT=39410",
                "LOCAL_GAMMA_REDIS_PORT=39420",
                "LOCAL_GAMMA_ES_PORT=39430",
                "LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT=39440",
                "LOCAL_GAMMA_OBJECT_STORAGE_ENDPOINT=object-storage:9000",
                "LOCAL_GAMMA_OBJECT_STORAGE_ACCESS_KEY_ID=prevalidation-only",
                "LOCAL_GAMMA_OBJECT_STORAGE_ACCESS_KEY_SECRET=prevalidation-only-not-production",
                "LOCAL_GAMMA_OBJECT_STORAGE_BUCKET=prevalidation-empty",
                "QWQ_COMPOSE_OBJECT_STORAGE_ENDPOINT=http://object-storage:9000",
                "QWQ_COMPOSE_OBJECT_STORAGE_BUCKET=prevalidation-empty",
                "QWQ_COMPOSE_OBJECT_STORAGE_REGION=prevalidation-local",
                "QWQ_COMPOSE_OBJECT_STORAGE_ACCESS_KEY_ID=prevalidation-only",
                "QWQ_COMPOSE_OBJECT_STORAGE_ACCESS_KEY_SECRET=prevalidation-only-not-production",
                (
                    "QWQ_COMPOSE_OBJECT_STORAGE_CDN_SIGN_KEY="
                    + auth["QWQ_COMPOSE_OBJECT_STORAGE_CDN_SIGN_KEY"]
                ),
                "AUTH_JWT_SECRET=" + auth["AUTH_JWT_SECRET"],
                "AUTH_JWT_ISSUER=quwoquan.prod-hosted.prevalidation",
                "AUTH_JWT_AUDIENCE=quwoquan-app",
                "AUTH_JWT_TOKEN_VERSION=1",
                "AUTH_DEVICE_TICKET_SECRET=" + auth["AUTH_DEVICE_TICKET_SECRET"],
                "AUTH_DEVICE_TICKET_ISSUER=quwoquan.prod-hosted.prevalidation.device",
                "AUTH_DEVICE_TICKET_AUDIENCE=quwoquan-app-device",
                "AUTH_DEVICE_TICKET_TOKEN_VERSION=1",
                "OTP_CODE_REF_ACTIVE_KEY_VERSION=" + otp_key_version,
                "OTP_CODE_REF_KEYS_JSON="
                + json.dumps(
                    {otp_key_version: auth["OTP_CODE_REF_KEY"]},
                    separators=(",", ":"),
                ),
                "QWQ_PUSH_TOKEN_ENCRYPTION_KEY="
                + auth["QWQ_PUSH_TOKEN_ENCRYPTION_KEY"],
                "CONTENT_ACCOUNT_CLOSURE_SUBJECT_HMAC_SECRET="
                + auth["CONTENT_ACCOUNT_CLOSURE_SUBJECT_HMAC_SECRET"],
                "RUNTIME_LOG_INGEST_TOKEN=prevalidation-not-release-evidence",
                "ALERT_INGEST_TOKEN=prevalidation-not-release-evidence",
                "OPS_OIDC_ISSUER=https://provider-unavailable.invalid",
                "OPS_OIDC_AUDIENCE=quwoquan-prevalidation",
                "OPS_OIDC_JWKS_URL=https://provider-unavailable.invalid/jwks.json",
                "PROD_RTC_MEDIA_CONNECTION_URL=wss://sfu-unavailable.invalid",
                "PROD_RTC_MEDIA_API_KEY=provider-unavailable",
                "PROD_RTC_MEDIA_API_SECRET=provider-unavailable",
                "PRODUCT_OPS_SLS_ENDPOINT=https://sls-unavailable.invalid",
                "PRODUCT_OPS_SLS_REGION=provider-unavailable",
                "PRODUCT_OPS_SLS_PROJECT=provider-unavailable",
                "ALIBABA_CLOUD_ACCESS_KEY_ID=provider-unavailable",
                "ALIBABA_CLOUD_ACCESS_KEY_SECRET=provider-unavailable",
            ]
        )
    elif instance == "gray":
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
    env_path = output_root / "stack.env"
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if instance == "prevalidate":
        env_path.chmod(0o600)


def _write_runtime_systemd_unit(
    output_root: Path,
    *,
    plane: dict[str, Any],
    plane_name: str,
    instance: str,
    startup_services: list[str],
) -> str:
    compose_root = str(plane.get("composeProjectRoot") or "").strip()
    credentials_root = str(plane.get("credentialsPath") or "").strip()
    if not compose_root.startswith("/") or not credentials_root.startswith("/"):
        raise SystemExit("FAIL: runtime systemd paths must be absolute")
    if instance == "prevalidate":
        compose_root = f"{compose_root.rstrip('/')}/prevalidate"
    layout = plane.get("rootlessRuntimeLayout") or {}
    compose_file = str(layout.get("composeFile") or "docker-compose.prod-hosted.yaml")
    env_file = str(layout.get("envFile") or "stack.env")
    unit_name = f"quwoquan-{plane_name}-{instance}.service"
    project = f"quwoquan-{plane_name}-{instance}"
    services = " ".join(startup_services)
    unit_dir = output_root / "systemd"
    unit_dir.mkdir(parents=True, exist_ok=True)
    service_lines = [
        "[Unit]",
        f"Description=Quwoquan {plane_name} {instance} rootless stack",
        "Wants=network-online.target",
        "After=network-online.target",
        "",
        "[Service]",
        "Type=oneshot",
        "RemainAfterExit=yes",
        f"WorkingDirectory={compose_root}",
    ]
    if instance != "prevalidate":
        service_lines.append(
            f"EnvironmentFile=-{credentials_root.rstrip('/')}/runtime.env"
        )
    service_lines.extend(
        [
            (
                f"ExecStart=/usr/bin/podman compose --env-file {env_file} "
                f"-f {compose_file} -p {project} up -d --remove-orphans {services}"
            ),
            (
                f"ExecStop=/usr/bin/podman compose --env-file {env_file} "
                f"-f {compose_file} -p {project} down"
            ),
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]
    )
    unit_dir.joinpath(unit_name).write_text(
        "\n".join(service_lines),
        encoding="utf-8",
    )
    return unit_name


def _write_observability_tree(
    output_root: Path,
    plane_name: str,
    *,
    render_name: str,
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

    destination = deployment_target_path(
        "prod-hosted",
        "rendered",
        render_name,
        *directory.parts,
    )
    if destination.exists():
        remove_deployment_tree(
            "prod-hosted",
            "rendered",
            render_name,
            *directory.parts,
        )
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
    startup_services = list(governed + support)
    image_only_services: list[str] = []
    prevalidation_images: dict[str, str] = {}
    if args.instance == "prevalidate":
        if args.prevalidate_scope != "first-party":
            raise SystemExit("FAIL: prevalidate instance requires --prevalidate-scope first-party")
        prevalidation = _prevalidation_spec()
        if args.data_mode not in (prevalidation.get("allowedDataModes") or []):
            raise SystemExit(f"FAIL: unsupported prevalidation data mode: {args.data_mode}")
        plane_projection = (prevalidation.get("planes") or {}).get(args.plane)
        if not isinstance(plane_projection, dict):
            raise SystemExit(f"FAIL: prevalidation plane projection missing: {args.plane}")
        startup_governed = [
            str(item) for item in (plane_projection.get("startupServices") or [])
        ]
        image_only_services = [
            str(item)
            for item in (plane_projection.get("imageAndConfigOnlyServices") or [])
        ]
        governed = startup_governed + image_only_services
        support = ["gamma-proxy"] if args.plane == "service" else []
        if args.data_mode == "isolated" and args.plane == "service":
            isolated = prevalidation.get("isolatedData") or {}
            support = [str(item) for item in (isolated.get("services") or [])] + support
            prevalidation_images = {
                str(name): str(ref)
                for name, ref in (isolated.get("images") or {}).items()
            }
        startup_services = support + startup_governed
        allowed = set(plane.get("rootlessGovernedComposeServices") or [])
        if not set(governed).issubset(allowed):
            raise SystemExit(
                f"FAIL: prevalidation services escape {args.plane} plane ownership"
            )
        if args.plane == "service" and "integration-service" not in image_only_services:
            raise SystemExit("FAIL: integration-service must remain image/config-only")
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
    web_root = str(layout.get("webStaticRoot") or "runtime/public-web")
    model_cache_root = str(layout.get("modelCacheRoot") or "runtime/model-cache")
    if Path(config_root).is_absolute() or ".." in Path(config_root).parts:
        raise SystemExit("FAIL: rootlessRuntimeLayout.configRoot must remain relative")
    if Path(caddyfile_path).is_absolute() or ".." in Path(caddyfile_path).parts:
        raise SystemExit("FAIL: rootlessRuntimeLayout.caddyfile must remain relative")
    if Path(legal_root).is_absolute() or ".." in Path(legal_root).parts:
        raise SystemExit("FAIL: rootlessRuntimeLayout.legalStaticRoot must remain relative")
    if Path(portal_root).is_absolute() or ".." in Path(portal_root).parts:
        raise SystemExit("FAIL: rootlessRuntimeLayout.portalStaticRoot must remain relative")
    if Path(web_root).is_absolute() or ".." in Path(web_root).parts:
        raise SystemExit("FAIL: rootlessRuntimeLayout.webStaticRoot must remain relative")
    if Path(model_cache_root).is_absolute() or ".." in Path(model_cache_root).parts:
        raise SystemExit("FAIL: rootlessRuntimeLayout.modelCacheRoot must remain relative")

    render_name = f"{args.plane}-{args.instance}"
    output_root = _resolve_render_output_dir(
        args.output_dir,
        plane=args.plane,
        instance=args.instance,
    )
    if output_root.exists():
        remove_deployment_tree("prod-hosted", "rendered", render_name)
    output_root.mkdir(parents=True, exist_ok=True)
    Path(media_root).mkdir(parents=True, exist_ok=True)
    legal_package_public = (
        legal_static_deployment_package_dir("prod", target="prod-hosted")
        / "current"
        / "public"
    )
    legal_output_root = deployment_target_path(
        "prod-hosted",
        "rendered",
        render_name,
        *Path(legal_root).parts,
    )
    if legal_output_root.exists():
        remove_deployment_tree(
            "prod-hosted",
            "rendered",
            render_name,
            *Path(legal_root).parts,
        )
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
    portal_output_root = deployment_target_path(
        "prod-hosted",
        "rendered",
        render_name,
        *Path(portal_root).parts,
    )
    if portal_output_root.exists():
        remove_deployment_tree(
            "prod-hosted",
            "rendered",
            render_name,
            *Path(portal_root).parts,
        )
    if portal_release_dist.is_dir():
        shutil.copytree(portal_release_dist, portal_output_root)
    else:
        portal_output_root.mkdir(parents=True, exist_ok=True)
    web_release_public = (
        web_deployment_package_dir("prod", target="prod-hosted")
        / "current"
        / "public"
    )
    web_output_root = deployment_target_path(
        "prod-hosted",
        "rendered",
        render_name,
        *Path(web_root).parts,
    )
    if web_output_root.exists():
        remove_deployment_tree(
            "prod-hosted",
            "rendered",
            render_name,
            *Path(web_root).parts,
        )
    if web_release_public.is_dir():
        shutil.copytree(web_release_public, web_output_root)
    else:
        web_output_root.mkdir(parents=True, exist_ok=True)
    deployment_target_path(
        "prod-hosted",
        "rendered",
        render_name,
        *Path(model_cache_root).parts,
    ).mkdir(parents=True, exist_ok=True)

    template = _load_yaml(compose_template)
    services = dict(template.get("services") or {})
    service_fragments = domain_service_compose_files(ROOT)
    service_fragments.append(
        ROOT
        / "quwoquan_service"
        / "control-plane"
        / "platform-ops"
        / "deploy"
        / "compose.yaml"
    )
    for fragment in service_fragments:
        fragment_services = _load_yaml(fragment).get("services") or {}
        duplicates = set(services) & set(fragment_services)
        if duplicates:
            raise SystemExit(
                f"FAIL: Compose service has multiple owners {sorted(duplicates)}: {fragment}"
            )
        services.update(fragment_services)
    rendered_services: dict[str, Any] = {}
    selected_names = set(selected)
    governed_names = set(governed)
    observability_config = plane.get("rootlessObservabilityRuntime") or {}
    service_network_name = str(
        observability_config.get("serviceNetworkName") or ""
    ).strip()
    config_sources = _write_config_tree(
        config_services=config_services,
        candidate_digest=args.candidate_digest,
        output_root=output_root,
        isolated_prevalidation=(
            args.instance == "prevalidate" and args.data_mode == "isolated"
        ),
    )
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
            image_version=args.image_transport_tag,
            config_version=str(
                (config_sources.get(service_name) or {}).get("configurationDigest") or ""
            ),
            release_evidence_digest=args.release_evidence_digest,
            versioned_image=service_name in governed_names,
            instance=args.instance,
            config_root=config_root,
            media_root=media_root,
            legal_root=legal_root,
            portal_root=portal_root,
            web_root=web_root,
            caddyfile_path=caddyfile_path,
            model_cache_root=model_cache_root,
            credentials_root=credentials_root,
            runtime_credentials=(
                {} if args.instance == "prevalidate" else runtime_credentials
            ),
            data_mode=args.data_mode,
            prevalidation_images=prevalidation_images,
            startup_services=set(startup_services),
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
    if args.instance == "prevalidate" and "platform-ops-service" in rendered_services:
        top_level_volumes.setdefault("platform-ops-prevalidation-state", {})
    filtered = _filter_top_level_volumes(rendered_services, top_level_volumes)
    if filtered:
        compose_payload["volumes"] = filtered

    compose_file_name = (
        ((plane.get("rootlessRuntimeLayout") or {}).get("composeFile"))
        or "docker-compose.prod-hosted.yaml"
    )
    if (
        Path(str(compose_file_name)).is_absolute()
        or ".." in Path(str(compose_file_name)).parts
    ):
        raise SystemExit("FAIL: rootlessRuntimeLayout.composeFile must remain relative")
    compose_out = output_root / str(compose_file_name)
    compose_out.write_text(
        yaml.safe_dump(compose_payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    observability_runtime = (
        None
        if args.instance == "prevalidate"
        else _write_observability_tree(
            output_root,
            args.plane,
            render_name=render_name,
        )
    )
    _write_caddyfile(output_root, args.instance, args.rollout_stage)
    _write_env_file(
        output_root,
        args.candidate_digest,
        args.image_transport_tag,
        args.instance,
    )
    systemd_unit_file = _write_runtime_systemd_unit(
        output_root,
        plane=plane,
        plane_name=args.plane,
        instance=args.instance,
        startup_services=startup_services,
    )

    report = {
        "plane": args.plane,
        "host": args.host or "",
        "composeTemplate": str(compose_template.relative_to(ROOT)),
        "composeFile": str(compose_out.relative_to(ROOT) if compose_out.is_relative_to(ROOT) else compose_out),
        "instance": args.instance,
        "governedComposeServices": governed,
        "supportComposeServices": support,
        "startupServices": startup_services,
        "imageAndConfigOnlyServices": image_only_services,
        "dataMode": args.data_mode,
        "configServices": config_services,
        "candidateDigest": args.candidate_digest,
        "imageTransportTag": args.image_transport_tag,
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
        "systemdUnitFile": systemd_unit_file,
    }
    (output_root / "provenance.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
