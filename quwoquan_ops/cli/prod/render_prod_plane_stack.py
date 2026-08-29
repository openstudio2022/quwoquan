#!/usr/bin/env python3
"""prod plane 渲染薄入口。

实现已按职责拆分到 ``render_prod_plane_stack_lib/`` 子包；本文件保留被
gate 源码文本扫描钉住的三个渲染函数（``_rewrite_service`` /
``_write_config_tree`` / ``_write_caddyfile``），并 re-export 子包全部
符号，保持既有 import、CLI 与 monkeypatch 表面不变。
"""
from __future__ import annotations

import copy
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.output_paths import service_deployment_package_dir
from quwoquan_ops.cli.prod.render_prod_plane_stack_lib.constants import (  # noqa: F401
    ACCESS_MANIFEST,
    DEFAULT_OUTPUT_ROOT,
    EXTERNAL_DATA_HOST,
    EXTERNAL_MONGO_PORT,
    EXTERNAL_MONGO_URI,
    EXTERNAL_POSTGRES_PORT,
    EXTERNAL_REDIS_PORT,
    OBSERVABILITY_SOURCE_ROOT,
    PREVALIDATION_AUTH_SECRET_KEYS,
    PROD_CADDY_IMAGE,
    PROD_PLANE_ADMIN_PORTS,
    PROD_PLANE_CADDY_ADMIN_CONTAINER_PORT,
    RUNTIME_LOG_EXPORT_SERVICES,
)
from quwoquan_ops.cli.prod.render_prod_plane_stack_lib.package_inputs import (  # noqa: F401
    _canonical_config_bytes,
    _git_revision,
    _load_yaml,
    _plane_spec,
    _prevalidation_secret_environment,
    _prevalidation_spec,
    _project_isolated_prevalidation_config,
    _require_external_deployment_root,
    _resolve_render_output_dir,
    _sha256,
    _verified_package_config,
    parse_args,
)
from quwoquan_ops.cli.prod.render_prod_plane_stack_lib.public_hosts import (  # noqa: F401
    _prod_public_hosts,
    _render_gray_routing_block,
)
from quwoquan_ops.cli.prod.render_prod_plane_stack_lib.render_entry import main  # noqa: F401
from quwoquan_ops.cli.prod.render_prod_plane_stack_lib.runtime_outputs import (  # noqa: F401
    _write_env_file,
    _write_observability_tree,
    _write_runtime_systemd_unit,
)
from quwoquan_ops.cli.prod.render_prod_plane_stack_lib.volume_layout import (  # noqa: F401
    _compose_bind_source,
    _filter_top_level_volumes,
    _named_volume_source,
    _rewrite_volume,
    _rewrite_volume_with_layout,
    _runtime_credential_source,
)
from quwoquan_ops.cli.prod.render_prod_plane_stack_lib.data_plane_wiring import (
    _wire_redis_scene,
)


def _prod_plane_admin_publish(instance: str) -> str:
    """按声明位渲染一条 prod 平面 admin 发布口，并就地锁住该端口的所有权边界。

    admin 只绑回环，不对外暴露。三实例编号必须互异，且不得落进任何 local port profile
    的 canonical block —— 一旦落进去，local teardown 的端口所有权判定会把 prod 平面的
    端口误认成目标 runtime 自有，从而在恢复路径上做出错误归因。
    """
    from quwoquan_ops.cli.lib.port_manifest import load_port_manifest

    if len(set(PROD_PLANE_ADMIN_PORTS.values())) != len(PROD_PLANE_ADMIN_PORTS):
        raise SystemExit("FAIL: prod plane admin ports must stay distinct per instance")
    host_port = PROD_PLANE_ADMIN_PORTS.get(instance)
    if host_port is None:
        raise SystemExit(f"FAIL: prod plane instance has no admin port: {instance}")
    profiles = load_port_manifest().get("profiles") or {}
    for profile_name, profile in profiles.items():
        start = profile.get("blockStart")
        end = profile.get("blockEnd")
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        if start <= host_port <= end:
            raise SystemExit(
                "FAIL: prod plane admin port must stay outside local port profile "
                f"{profile_name} block {start}-{end}: {host_port}"
            )
    return f"127.0.0.1:{host_port}:{PROD_PLANE_CADDY_ADMIN_CONTAINER_PORT}"


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
    replica_id: str,
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
            updated["ports"] = ["80:80", "443:443", _prod_plane_admin_publish("prod")]
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
            updated["ports"] = ["39000:80", _prod_plane_admin_publish("prevalidate")]
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
            updated["ports"] = ["29000:80", _prod_plane_admin_publish("gray")]
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
        # scheme 必须写出来：服务端按 scheme 决定 trace 是否加密传输，缺 scheme
        # 判否。collector 在共享网络内明文接收，所以这里声明 http://。
        environment["OTEL_EXPORTER_OTLP_ENDPOINT"] = (
            "${OTEL_EXPORTER_OTLP_ENDPOINT:-http://otel-collector:4318}"
        )
        if name in RUNTIME_LOG_EXPORT_SERVICES:
            # 所有受管服务在成功读取、校验当前发布包配置后，以服务+环境绑定的
            # 短期凭据 ACK。固定实例身份来自渲染器，禁止使用容器随机 hostname
            # 使 rollout convergence 无法判断成员完整性。
            cluster_name = f"prod-{instance}-control-{replica_id}"
            environment["PLATFORM_OPS_BASE_URL"] = "http://platform-ops-service:18088"
            environment["CLUSTER_NAME"] = cluster_name
            environment["SERVICE_INSTANCE_ID"] = (
                f"{name}-{cluster_name}-0"
            )
            if name == "platform-ops-service":
                environment["PLATFORM_OPS_CONFIG_ACK_REQUIRED_INSTANCES"] = ",".join(
                    f"{service}-{cluster_name}-0"
                    for service in sorted(RUNTIME_LOG_EXPORT_SERVICES)
                )
                environment["PLATFORM_OPS_CONFIG_ACK_MAX_AGE_SECONDS"] = "120"
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
        redis_addr = f"{redis_host}:{redis_port}"
        postgres_host = "postgres" if isolated_local else EXTERNAL_DATA_HOST
        postgres_port = (
            5432
            if isolated_local
            else (39400 if edge_prevalidation else EXTERNAL_POSTGRES_PORT)
        )
        if name == "recommendation-service":
            environment["MONGODB_URI"] = mongo_uri
        if name == "content-service":
            environment["CONTENT_MONGO_URI"] = mongo_uri
            for scene in ("REC", "GENERAL", "REALTIME"):
                _wire_redis_scene(environment, f"CONTENT_REDIS_{scene}", redis_addr)
            environment["SEARCH_ES_ENABLED"] = "true"
            if data_mode == "isolated":
                if (
                    "elasticsearch" not in selected
                    or startup_services is None
                    or "elasticsearch" not in startup_services
                ):
                    raise SystemExit(
                        "FAIL: isolated content-service Elasticsearch startup dependency "
                        "must be selected"
                    )
                environment["SEARCH_ES_ENDPOINTS"] = "http://elasticsearch:9200"
                updated.setdefault("depends_on", {})["elasticsearch"] = {
                    "condition": "service_healthy"
                }
            else:
                environment["SEARCH_ES_ENDPOINTS"] = (
                    "${PROD_CONTENT_SEARCH_ES_ENDPOINTS:?managed content search "
                    "endpoint is required}"
                )
        if name == "chat-service":
            environment["CHAT_MONGO_URI"] = mongo_uri
            # chat 的三个 scene 各自注入物理地址，不存在需要兜底的 scene，
            # 因此不再注入无前缀的共享 REDIS_ADDR。
            for scene in ("REALTIME", "GENERAL", "RELIABLE_TASK"):
                _wire_redis_scene(environment, f"CHAT_REDIS_{scene}", redis_addr)
        if name == "user-service":
            environment["USER_POSTGRES_DSN"] = (
                f"postgres://quwoquan:quwoquan@{postgres_host}:{postgres_port}/"
                "quwoquan?sslmode=disable"
            )
            environment["USER_MONGO_URI"] = mongo_uri
            # realtime scene 在 user-service 的装配里从 general 继承地址，因此
            # 只注入 general。
            _wire_redis_scene(environment, "USER_REDIS_GENERAL", redis_addr)
        if name == "assistant-service":
            environment["ASSISTANT_MONGO_URI"] = mongo_uri
            for scene in ("GENERAL", "REC"):
                _wire_redis_scene(environment, f"ASSISTANT_REDIS_{scene}", redis_addr)
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
            environment["PRODUCT_OPS_POSTGRES_DSN"] = (
                f"postgres://quwoquan:quwoquan@{postgres_host}:{postgres_port}/"
                "quwoquan?sslmode=disable"
            )
            environment["PRODUCT_OPS_MONGO_URI"] = mongo_uri
            for scene in ("REC", "GENERAL"):
                _wire_redis_scene(environment, f"PRODUCT_OPS_REDIS_{scene}", redis_addr)
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
            environment.pop("POSTGRES_DSN", None)
            environment["PLATFORM_OPS_POSTGRES_DSN"] = (
                f"postgres://quwoquan:quwoquan@{postgres_host}:{postgres_port}/"
                "quwoquan?sslmode=disable"
            )
            # ConfigInstanceReport transactional outbox 的 typed event 总线。
            # compose 基线里的 redis:6379 只在 isolated 数据面成立，hosted 面
            # 必须指向外部数据主机，否则 outbox 起不来。
            _wire_redis_scene(environment, "PLATFORM_OPS_REDIS_GENERAL", redis_addr)
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
            # tag-service 只读 scene 专属键。
            _wire_redis_scene(environment, "TAG_REDIS_GENERAL", redis_addr)
            environment["TAG_MONGO_URI"] = mongo_uri
        if name == "entity-service":
            environment["ENTITY_MONGO_URI"] = mongo_uri
            # general 是本服务 message transport binding 的必需 scene：homepage
            # 的跨服务事实流建立在跨副本可见的前提上，缺地址会回落进程内存。
            _wire_redis_scene(environment, "ENTITY_REDIS_GENERAL", redis_addr)
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
            # Redis 是 integration 的启动必需依赖（外部交互幂等与限流），此前
            # 本平面没有任何注入轨，环境快照只留了一个未兑现的占位符地址。
            _wire_redis_scene(environment, "INTEGRATION_REDIS_GENERAL", redis_addr)
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
        if name == "search-service":
            # rec scene 的快照声明是云上 cluster；general 未声明物理组网，按
            # 「本环境不接真实 Redis」保持原样。
            for scene in ("REC", "GENERAL"):
                _wire_redis_scene(environment, f"SEARCH_REDIS_{scene}", redis_addr)
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
            # notification-service 只读 scene 专属键。
            for scene in ("GENERAL", "REALTIME"):
                _wire_redis_scene(environment, f"NOTIFICATION_REDIS_{scene}", redis_addr)
            environment["NOTIFICATION_REDIS_GENERAL_DB"] = "1"
            environment["NOTIFICATION_REDIS_REALTIME_DB"] = "4"
            environment["NOTIFICATION_REALTIME_BASE_URL"] = (
                f"http://{EXTERNAL_DATA_HOST}:"
                "${LOCAL_GAMMA_REALTIME_PORT:?realtime port is required}"
            )
        if name == "realtime-gateway":
            _wire_redis_scene(
                environment, "REALTIME_GATEWAY_REDIS_REALTIME", redis_addr
            )
        if name == "rtc-service":
            environment["RTC_MONGO_URI"] = mongo_uri
            # rtc 的 rec scene 在装配里复用 general，因此只需接 general 与
            # realtime 两个 scene；共享兜底键 RTC_REDIS_ADDR 保留为该服务部署面
            # 的既有契约，scene 专属键优先。
            environment["RTC_REDIS_ADDR"] = redis_addr
            for scene in ("GENERAL", "REALTIME"):
                _wire_redis_scene(environment, f"RTC_REDIS_{scene}", redis_addr)
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

    # 灰度路由策略（IaC）同时供 API Edge 运行时和 Platform Ops 只读投影消费。
    # API Edge 的 policy_file 相对 CONFIG_ROOT 解析；两份投影必须复制自同一源字节。
    routing_policy_src = ROOT / "quwoquan_ops" / "environments" / "prod" / "rollout" / "routing_policy.yaml"
    if not routing_policy_src.is_file():
        raise SystemExit(f"FAIL: missing gray routing policy: {routing_policy_src}")
    for routing_target in (
        config_root / "rollout" / "routing_policy.yaml",
        config_root / "gray-routing" / "policy.yaml",
    ):
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


def _write_caddyfile(
    output_root: Path,
    instance: str,
    rollout_stage: str = "100",
) -> None:
    target = output_root / "runtime" / "Caddyfile"
    target.parent.mkdir(parents=True, exist_ok=True)
    public_hosts = _prod_public_hosts()
    gray_routing_block = (
        _render_gray_routing_block(rollout_stage) if instance == "prod" else ""
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
\t@runtime_config path /runtime-config-trust.json /runtime-config-package.json
\theader @runtime_config {{
\t\tCache-Control "no-store"
\t\tContent-Type "application/json; charset=utf-8"
\t}}
\t@service_worker path /flutter_service_worker.js
\theader @service_worker Cache-Control "no-cache, no-store, must-revalidate"
\t@revalidated_web_asset path /assets/* /canvaskit/* /icons/* /fonts/* /main.dart.js /flutter.js /flutter_bootstrap.js *.ttf *.woff2
\theader @revalidated_web_asset Cache-Control "no-cache, must-revalidate"
\thandle {{
\t\troot * /srv/web
\t\troute {{
\t\t\ttry_files {{path}} /index.html
\t\t\t@html path /index.html
\t\t\theader @html {{
\t\t\t\tCache-Control "no-cache, must-revalidate"
\t\t\t\tContent-Type "text/html; charset=utf-8"
\t\t\t}}
\t\t\theader {{
\t\t\t\tContent-Security-Policy "default-src 'self'; connect-src 'self' https: wss:; img-src 'self' data: blob: https:; media-src 'self' blob: https:; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; worker-src 'self' blob:; manifest-src 'self'; frame-ancestors 'none'"
\t\t\t}}
\t\t\tfile_server
\t\t}}
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


if __name__ == "__main__":
    raise SystemExit(main())
