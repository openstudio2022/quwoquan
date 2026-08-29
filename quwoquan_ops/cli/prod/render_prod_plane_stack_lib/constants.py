"""prod plane 渲染共享常量（从 render_prod_plane_stack.py 逐字搬移）。"""
from __future__ import annotations

from pathlib import Path

from quwoquan_ops.cli.lib.output_paths import deployment_render_dir

ROOT = Path(__file__).resolve().parents[4]

EXTERNAL_DATA_HOST = "host.containers.internal"
EXTERNAL_POSTGRES_PORT = 19400
EXTERNAL_MONGO_PORT = 19410
EXTERNAL_REDIS_PORT = 19420
EXTERNAL_MONGO_URI = f"mongodb://{EXTERNAL_DATA_HOST}:{EXTERNAL_MONGO_PORT}/?directConnection=true"
PROD_CADDY_IMAGE = (
    "docker.io/library/caddy:2.8.4-alpine@"
    "sha256:af32e97399febea808609119bb21544d0265c58a02836576e32a2d082c262c17"
)

PROD_PLANE_CADDY_ADMIN_CONTAINER_PORT = 2019
# prod 平面的 Caddy admin 主机端口由 prod 渲染器拥有，不派生自 local port manifest。
# prod/gray/prevalidate 是同一台机器上的三个实例，各自需要互不冲突的 admin 编号；
# manifest 只有单个 `prod-sim` profile，把它们归一过去会让三实例塌缩成同一个端口，
# 破坏隔离。集中声明是为了让这三个数字有唯一出处，而不是散落成看似漂移的字面量。
PROD_PLANE_ADMIN_PORTS = {
    "prod": 12019,
    "gray": 22019,
    "prevalidate": 32019,
}
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

ACCESS_MANIFEST = ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml"
OBSERVABILITY_SOURCE_ROOT = ROOT / "quwoquan_ops/observability/monitoring"
DEFAULT_OUTPUT_ROOT = deployment_render_dir(
    "prod",
    target="prod-hosted",
    name="service-prod",
)
