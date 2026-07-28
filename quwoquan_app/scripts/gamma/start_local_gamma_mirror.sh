#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
LOCAL_GAMMA_ACTIVE_CHILD_PID=""

cleanup_active_child() {
  local exit_status="$?"
  if [[ -n "$LOCAL_GAMMA_ACTIVE_CHILD_PID" ]] \
    && kill -0 "$LOCAL_GAMMA_ACTIVE_CHILD_PID" >/dev/null 2>&1; then
    echo "[local-gamma] stopping active child before exit" >&2
    kill "$LOCAL_GAMMA_ACTIVE_CHILD_PID" >/dev/null 2>&1 || true
    wait "$LOCAL_GAMMA_ACTIVE_CHILD_PID" >/dev/null 2>&1 || true
  fi
  LOCAL_GAMMA_ACTIVE_CHILD_PID=""
  trap - EXIT INT TERM HUP
  exit "$exit_status"
}
trap cleanup_active_child EXIT INT TERM HUP

QWQ_OUTPUT_ROOT="${QWQ_OUTPUT_ROOT:-$ROOT/.qwq_output}"
QWQ_DEPLOY_WORK_ROOT="${QWQ_DEPLOY_WORK_ROOT:-${XDG_CACHE_HOME:-$HOME/.cache}/quwoquan/deploy}"
PRODUCT_TELEMETRY_AVAILABLE="${QWQ_PRODUCT_TELEMETRY_AVAILABLE:-1}"
WORKLOAD="${QWQ_WORKLOAD:-full}"
case "$WORKLOAD" in
  content-release)
    # Content import/API/media are intentionally independent from commercial
    # telemetry.  The release profile validates telemetry separately.
    PRODUCT_TELEMETRY_AVAILABLE=0
    filtered_profiles_csv=""
    requested_profiles_csv="${COMPOSE_PROFILES:-}"
    while IFS= read -r profile; do
      case "$profile" in
        ""|commercial-observability|assistant-runtime) ;;
        *)
          filtered_profiles_csv="${filtered_profiles_csv:+${filtered_profiles_csv},}${profile}"
          ;;
      esac
    done < <(printf '%s\n' "$requested_profiles_csv" | tr ',' '\n')
    COMPOSE_PROFILES="$filtered_profiles_csv"
    export COMPOSE_PROFILES
    ;;
  full)
    if [[ "$PRODUCT_TELEMETRY_AVAILABLE" != "1" ]]; then
      echo "[local-gamma] GATE_BLOCK: full workload requires product telemetry" >&2
      exit 2
    fi
    export COMPOSE_PROFILES="${COMPOSE_PROFILES:+${COMPOSE_PROFILES},}commercial-observability,assistant-runtime,edge-media"
    ;;
  *)
    echo "[local-gamma] FAIL: QWQ_WORKLOAD must be content-release or full" >&2
    exit 2
    ;;
esac
LOCAL_RUN_ACTION="up"
for arg in "$@"; do
  if [[ "$arg" == "--down" ]]; then LOCAL_RUN_ACTION="down"; fi
done
eval "$(python3 "$ROOT/quwoquan_ops/cli/lib/local_run.py" \
  --env gamma --target gamma-local --action "$LOCAL_RUN_ACTION" --output-root "$QWQ_OUTPUT_ROOT")"
export QWQ_OUTPUT_ROOT QWQ_DEPLOY_WORK_ROOT QWQ_OBSERVABILITY_RUN_ROOT QWQ_RUN_ROOT
COMPOSE_FILE="$ROOT/quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
COMPOSE_FILES=("$COMPOSE_FILE")
while IFS= read -r service_compose_file; do
  COMPOSE_FILES+=("$service_compose_file")
done < <(find "$ROOT/quwoquan_service/services" -mindepth 3 -maxdepth 3 -path '*/deploy/compose.yaml' -type f | sort)
while IFS= read -r service_environment_compose_file; do
  COMPOSE_FILES+=("$service_environment_compose_file")
done < <(find "$ROOT/quwoquan_service/services" -mindepth 5 -maxdepth 5 -path '*/environments/gamma/deploy/compose.yaml' -type f | sort)
COMPOSE_FILES+=("$ROOT/quwoquan_service/control-plane/platform-ops/deploy/compose.yaml")
COMPOSE_FILE_ARGS=()
for service_compose_file in "${COMPOSE_FILES[@]}"; do
  COMPOSE_FILE_ARGS+=(-f "$service_compose_file")
done
LOCAL_GAMMA_COMPOSE_PROJECT_NAME="${LOCAL_GAMMA_COMPOSE_PROJECT_NAME:-quwoquan_service}"
LOCAL_GAMMA_REC_POLICY_SOURCE="${LOCAL_GAMMA_REC_POLICY_SOURCE:-$ROOT/quwoquan_service/services/content-service/resources/policies/content/post/recommendation_policy_object_cards_v1.yaml}"
export LOCAL_GAMMA_REC_POLICY_SOURCE
if [[ -z "${LOCAL_GAMMA_HTTP_PORT:-}" \
   || -z "${LOCAL_GAMMA_PRODUCT_OPS_PORT:-}" \
   || -z "${LOCAL_GAMMA_PLATFORM_OPS_PORT:-}" \
   || -z "${LOCAL_GAMMA_MEDIA_EDGE_PORT:-}" \
   || -z "${LOCAL_GAMMA_CONTENT_PORT:-}" \
   || -z "${LOCAL_GAMMA_CHAT_PORT:-}" \
   || -z "${LOCAL_GAMMA_USER_PORT:-}" \
   || -z "${LOCAL_GAMMA_ASSISTANT_PORT:-}" \
   || -z "${LOCAL_GAMMA_REC_MODEL_PORT:-}" \
   || -z "${LOCAL_GAMMA_PRODUCT_OPS_SERVICE_PORT:-}" \
   || -z "${LOCAL_GAMMA_PLATFORM_OPS_SERVICE_PORT:-}" \
   || -z "${LOCAL_GAMMA_TAG_PORT:-}" \
   || -z "${LOCAL_GAMMA_SEARCH_PORT:-}" \
   || -z "${LOCAL_GAMMA_ENTITY_PORT:-}" \
   || -z "${LOCAL_GAMMA_CIRCLE_PORT:-}" \
   || -z "${LOCAL_GAMMA_INTEGRATION_PORT:-}" \
   || -z "${LOCAL_GAMMA_NOTIFICATION_PORT:-}" \
   || -z "${LOCAL_GAMMA_POSTGRES_PORT:-}" \
   || -z "${LOCAL_GAMMA_MONGO_PORT:-}" \
   || -z "${LOCAL_GAMMA_REDIS_PORT:-}" \
   || -z "${LOCAL_GAMMA_ES_PORT:-}" ]]; then
  eval "$(python3 "$ROOT/quwoquan_ops/cli/print_local_port_profile.py" --profile gamma-local --format shell-defaults)"
fi
# docker compose 只读取导出的环境变量；这里把 canonical local-gamma 端口全部导出，
# 避免直接运行脚本/Makefile 时回退到 compose 文件里的旧默认端口。
export \
  LOCAL_GAMMA_HTTP_PORT \
  LOCAL_GAMMA_PRODUCT_OPS_PORT \
  LOCAL_GAMMA_PLATFORM_OPS_PORT \
  LOCAL_GAMMA_MEDIA_EDGE_PORT \
  LOCAL_GAMMA_CONTENT_PORT \
  LOCAL_GAMMA_CHAT_PORT \
  LOCAL_GAMMA_USER_PORT \
  LOCAL_GAMMA_ASSISTANT_PORT \
  LOCAL_GAMMA_REC_MODEL_PORT \
  LOCAL_GAMMA_PRODUCT_OPS_SERVICE_PORT \
  LOCAL_GAMMA_PLATFORM_OPS_SERVICE_PORT \
  LOCAL_GAMMA_TAG_PORT \
  LOCAL_GAMMA_SEARCH_PORT \
  LOCAL_GAMMA_ENTITY_PORT \
  LOCAL_GAMMA_CIRCLE_PORT \
  LOCAL_GAMMA_INTEGRATION_PORT \
  LOCAL_GAMMA_NOTIFICATION_PORT \
  LOCAL_GAMMA_POSTGRES_PORT \
  LOCAL_GAMMA_MONGO_PORT \
  LOCAL_GAMMA_MONGO_CACHE_SIZE_GB \
  LOCAL_GAMMA_REDIS_PORT \
  LOCAL_GAMMA_ES_PORT

export_service_compose_environment() {
  local source_name target_name
  export QWQ_COMPOSE_ENV=gamma
  while IFS= read -r source_name; do
    # gamma-local infrastructure Compose still owns LOCAL_GAMMA_* mount/port
    # variables (for example the immutable Caddyfile source). Export both the
    # source name and its service-owned QWQ_COMPOSE alias.
    export "$source_name"
    target_name="QWQ_COMPOSE_${source_name#LOCAL_GAMMA_}"
    printf -v "$target_name" '%s' "${!source_name}"
    export "$target_name"
  done < <(compgen -A variable LOCAL_GAMMA_ | sort)
}
CONFIG_VERSION="${LOCAL_GAMMA_CONFIG_VERSION:-local-gamma-v1}"
IMAGE_VERSION="${LOCAL_GAMMA_IMAGE_VERSION:-0.0.1}"
eval "$(
  PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import shlex
from urllib.parse import urlsplit

from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
)

bases = get_target(load_environment_topology(), "gamma-local")["publicBases"]
for name, role in (
    ("GATEWAY_BASE_URL", "api"),
    ("PRODUCT_OPS_BASE_URL", "productOps"),
    ("MEDIA_AVATAR_BASE_URL", "mediaAvatar"),
    ("MEDIA_IMAGE_BASE_URL", "mediaImage"),
    ("MEDIA_VIDEO_BASE_URL", "mediaVideo"),
    ("MEDIA_UPLOAD_BASE_URL", "mediaUpload"),
):
    print(f"{name}={shlex.quote(str(bases[role]))}")
for name, role in (
    ("QWQ_PUBLIC_API_HOST", "api"),
    ("QWQ_PUBLIC_WEB_HOST", "publicWeb"),
    ("QWQ_PUBLIC_RTC_HOST", "rtc"),
    ("QWQ_PUBLIC_OPS_HOST", "productOps"),
    ("QWQ_PUBLIC_CDN_HOST", "mediaImage"),
):
    print(f"{name}={shlex.quote(str(urlsplit(str(bases[role])).hostname))}")
PY
)"
PUBLIC_HOSTS=(
  "$QWQ_PUBLIC_API_HOST"
  "$QWQ_PUBLIC_WEB_HOST"
  "$QWQ_PUBLIC_OPS_HOST"
  "$QWQ_PUBLIC_CDN_HOST"
)
LOCAL_GAMMA_TAGS_DIR="${LOCAL_GAMMA_TAGS_DIR:-$ROOT/quwoquan_data/control_plane/governance/taxonomy}"
LOCAL_GAMMA_TAG_DB="${LOCAL_GAMMA_TAG_DB:-quwoquan_tag}"
# 2G onebox 在 gray/prod 切换窗口会短时双栈并存；显式压低 Mongo cache，避免数据面被 OOM kill。
LOCAL_GAMMA_MONGO_CACHE_SIZE_GB="${LOCAL_GAMMA_MONGO_CACHE_SIZE_GB:-0.25}"
# daocloud 镜像代理在部分网络下会 EOF；默认直连 Docker Hub，可通过环境变量覆盖。
DOCKER_LIBRARY_PREFIX="${LOCAL_GAMMA_DOCKER_LIBRARY_PREFIX:-docker.io/library}"
HOST_READY_TIMEOUT_SECONDS="${LOCAL_GAMMA_HOST_READY_TIMEOUT_SECONDS:-360}"
FORCE_CLEAN_RECREATE="${LOCAL_GAMMA_FORCE_CLEAN_RECREATE:-0}"
PRESERVE_POSTGRES_VOLUME="${LOCAL_GAMMA_PRESERVE_POSTGRES_VOLUME:-0}"
LOCAL_GAMMA_DEPLOY_RENDER_ROOT="${QWQ_DEPLOY_WORK_ROOT}/gamma-local/rendered"
LOCAL_GAMMA_CACHE_ROOT="${QWQ_OUTPUT_ROOT}/env/gamma/local/gamma-local/cache"
LOCAL_GAMMA_PROCESS_ROOT="${QWQ_OUTPUT_ROOT}/env/gamma/local/gamma-local/process"
LOCAL_GAMMA_RUNTIME_LOG_ROOT="${QWQ_OBSERVABILITY_RUN_ROOT}/logs/service"
GAMMA_RUN_ROOT="${QWQ_RUN_ROOT}"
# 渲染配置是部署过程临时输入，真相源始终在 Ops/服务的 deploy 与 configs 目录。
LOCAL_GAMMA_CONFIG_ROOT="${LOCAL_GAMMA_DEPLOY_RENDER_ROOT}/config-root"
LOCAL_GAMMA_MEDIA_ROOT="${LOCAL_GAMMA_CACHE_ROOT}/media"
# Ops owns the immutable local-gamma route table. Runtime output never carries static routing config.
LOCAL_GAMMA_CADDYFILE="$ROOT/quwoquan_ops/environments/gamma/local/Caddyfile"
LOCAL_GAMMA_CADDY_DATA_VOLUME="${LOCAL_GAMMA_CADDY_DATA_VOLUME:-local-gamma-caddy-data}"
LOCAL_GAMMA_CADDY_CONFIG_VOLUME="${LOCAL_GAMMA_CADDY_CONFIG_VOLUME:-local-gamma-caddy-config}"
eval "$(
  PYTHONDONTWRITEBYTECODE=1 python3 \
    "$ROOT/quwoquan_ops/cli/lib/public_domain_tls.py" paths \
    --target gamma-local \
    --format shell
)"
LOCAL_GAMMA_MODEL_CACHE_ROOT="${LOCAL_GAMMA_CACHE_ROOT}/model"
LOCAL_GAMMA_PORTAL_ROOT="${LOCAL_GAMMA_PORTAL_ROOT:-${QWQ_DEPLOY_WORK_ROOT}/gamma-local/build/ops-portal}"
LOCAL_GAMMA_STACK_STATUS_REPORT="${LOCAL_GAMMA_PROCESS_ROOT}/stack_status.json"
LOCAL_GAMMA_SEARCH_BACKFILL_REQUEST_TIMEOUT="${LOCAL_GAMMA_SEARCH_BACKFILL_REQUEST_TIMEOUT:-30s}"
STAGE="${STAGE:-gamma}"
LOCAL_GAMMA_APP_ENV="${LOCAL_GAMMA_APP_ENV:-}"
CONFIG_SOURCE_ENV="${CONFIG_SOURCE_ENV:-}"
LOCAL_GAMMA_READY_INDEX_SUFFIX="${LOCAL_GAMMA_READY_INDEX_SUFFIX:-}"
case "$STAGE" in
  ""|gamma|pre)
    LOCAL_GAMMA_APP_ENV="${LOCAL_GAMMA_APP_ENV:-gamma}"
    CONFIG_SOURCE_ENV="${CONFIG_SOURCE_ENV:-gamma}"
    LOCAL_GAMMA_READY_INDEX_SUFFIX="${LOCAL_GAMMA_READY_INDEX_SUFFIX:-local-gamma}"
    ENABLE_FIXTURE_SEEDS=0
    # gamma-local 保持生产 Remote composition 与完整第一方拓扑；
    # 所有外部 Provider 由服务 Binding 选择 Port 对等本地替身，并由 stackctl 统一材料化。
    ASSISTANT_SCENARIO_SEED_REFS="${ASSISTANT_SCENARIO_SEED_REFS:-assistant_p0_core}"
    ;;
  prod)
    LOCAL_GAMMA_APP_ENV="${LOCAL_GAMMA_APP_ENV:-prod}"
    CONFIG_SOURCE_ENV="${CONFIG_SOURCE_ENV:-prod}"
    LOCAL_GAMMA_READY_INDEX_SUFFIX="${LOCAL_GAMMA_READY_INDEX_SUFFIX:-prod-onebox}"
    ENABLE_FIXTURE_SEEDS="${ENABLE_FIXTURE_SEEDS:-0}"
    # prod 只消费 environments/prod 的真实 Provider Binding，缺凭据必须 fail-fast。
    ASSISTANT_SCENARIO_SEED_REFS="${ASSISTANT_SCENARIO_SEED_REFS:-}"
    ;;
  *)
    echo "[local-gamma] FAIL: unsupported STAGE=$STAGE (expected pre|gamma|prod)" >&2
    exit 2
    ;;
esac
if [[ "${ENABLE_FIXTURE_SEEDS:-0}" != "0" ]]; then
  echo "[local-gamma] GATE_BLOCK: environment-visible fixture seeding is retired; activate an immutable data release instead" >&2
  exit 2
fi
# Warm path: reuse persisted mongo/ES when watermark digest still matches seed inputs.
LOCAL_GAMMA_DATA_PLANE_WATERMARK="${LOCAL_GAMMA_DATA_PLANE_WATERMARK:-${LOCAL_GAMMA_CACHE_ROOT}/data-plane-watermark.json}"
compute_local_gamma_data_plane_digest() {
  PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - "$LOCAL_GAMMA_TAGS_DIR" <<'PY'
import hashlib
import sys
from pathlib import Path

tags_dir = Path(sys.argv[1])
digest = hashlib.sha256()
for path in sorted(tags_dir.rglob("*")):
    if path.is_file():
        digest.update(path.as_posix().encode())
        digest.update(path.read_bytes())
print(digest.hexdigest())
PY
}
maybe_reuse_local_gamma_data_plane() {
  if [[ "${LOCAL_GAMMA_REUSE_DATA_PLANE:-0}" != "1" ]]; then
    return 0
  fi
  if [[ "$ENABLE_FIXTURE_SEEDS" != "1" ]]; then
    return 0
  fi
  if [[ ! -f "$LOCAL_GAMMA_DATA_PLANE_WATERMARK" ]]; then
    echo "[local-gamma] data-plane reuse requested but watermark missing; full seed will run"
    return 0
  fi
  local current_digest
  current_digest="$(compute_local_gamma_data_plane_digest)"
  if PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - "$LOCAL_GAMMA_DATA_PLANE_WATERMARK" "$current_digest" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
raise SystemExit(0 if payload.get("status") == "ready" and payload.get("digest") == sys.argv[2] else 1)
PY
  then
    ENABLE_FIXTURE_SEEDS=0
    echo "[local-gamma] LOCAL_GAMMA_REUSE_DATA_PLANE hit watermark digest=${current_digest:0:12}…; skip fixture seed/ES backfill"
  else
    echo "[local-gamma] data-plane watermark stale or invalid; full seed will run"
  fi
}
write_local_gamma_data_plane_watermark() {
  local digest="$1"
  mkdir -p "$(dirname "$LOCAL_GAMMA_DATA_PLANE_WATERMARK")"
  PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - "$LOCAL_GAMMA_DATA_PLANE_WATERMARK" "$digest" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
path.write_text(
    json.dumps(
        {
            "schema": "local-gamma-data-plane-watermark",
            "status": "ready",
            "digest": sys.argv[2],
            "writtenAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        ensure_ascii=False,
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
print(path)
PY
}
maybe_reuse_local_gamma_data_plane
LOCAL_GAMMA_LEGAL_STATIC_ROOT="${LOCAL_GAMMA_LEGAL_STATIC_ROOT:-$(PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - "$CONFIG_SOURCE_ENV" <<'PY'
import sys
from quwoquan_ops.cli.lib.output_paths import legal_static_deployment_package_dir

print(legal_static_deployment_package_dir(sys.argv[1]) / "current" / "public")
PY
)}"
LOCAL_GAMMA_READY_INDEX_STREAM="${LOCAL_GAMMA_READY_INDEX_STREAM:-reliabletask:chat:avatar:ready:${LOCAL_GAMMA_READY_INDEX_SUFFIX}}"
LOCAL_GAMMA_READY_INDEX_GROUP="${LOCAL_GAMMA_READY_INDEX_GROUP:-chat.group_avatar_worker.${LOCAL_GAMMA_READY_INDEX_SUFFIX}}"
LOCAL_GAMMA_READY_INDEX_QUEUE="${LOCAL_GAMMA_READY_INDEX_QUEUE:-reliabletask.chat.avatar}"
PREVIOUS_IMAGE_VERSION="${PREVIOUS_IMAGE_VERSION:-${PREV_IMAGE_VERSION:-}}"
export \
  STAGE \
  LOCAL_GAMMA_APP_ENV \
  CONFIG_SOURCE_ENV \
  ENABLE_FIXTURE_SEEDS \
  ASSISTANT_SCENARIO_SEED_REFS \
  LOCAL_GAMMA_READY_INDEX_STREAM \
  LOCAL_GAMMA_READY_INDEX_GROUP \
  LOCAL_GAMMA_READY_INDEX_QUEUE \
  LOCAL_GAMMA_CADDY_DATA_VOLUME \
  LOCAL_GAMMA_CADDY_CONFIG_VOLUME \
  QWQ_PUBLIC_TLS_CERT_FILE \
  QWQ_PUBLIC_TLS_KEY_FILE \
  QWQ_PUBLIC_API_HOST \
  QWQ_PUBLIC_WEB_HOST \
  QWQ_PUBLIC_RTC_HOST \
  QWQ_PUBLIC_OPS_HOST \
  QWQ_PUBLIC_CDN_HOST \
  MEDIA_AVATAR_BASE_URL \
  MEDIA_IMAGE_BASE_URL \
  MEDIA_VIDEO_BASE_URL \
  MEDIA_UPLOAD_BASE_URL \
  LOCAL_GAMMA_CONFIG_ROOT \
  LOCAL_GAMMA_MEDIA_ROOT \
  LOCAL_GAMMA_MODEL_CACHE_ROOT \
  LOCAL_GAMMA_PORTAL_ROOT \
  GAMMA_RUN_ROOT \
  LOCAL_GAMMA_LEGAL_STATIC_ROOT \
  PREVIOUS_IMAGE_VERSION

library_image() {
  local image="$1"
  printf '%s/%s' "${DOCKER_LIBRARY_PREFIX%/}" "$image"
}

export LOCAL_GAMMA_POSTGRES_IMAGE="${LOCAL_GAMMA_POSTGRES_IMAGE:-$(library_image postgres:16-alpine)}"
export LOCAL_GAMMA_MONGO_IMAGE="${LOCAL_GAMMA_MONGO_IMAGE:-$(library_image mongo:7-jammy)}"
export LOCAL_GAMMA_REDIS_IMAGE="${LOCAL_GAMMA_REDIS_IMAGE:-$(library_image redis:7.2-alpine)}"
export LOCAL_GAMMA_GO_BOOKWORM_IMAGE="${LOCAL_GAMMA_GO_BOOKWORM_IMAGE:-$(library_image golang:1.24-bookworm)}"
export LOCAL_GAMMA_CADDY_IMAGE="${LOCAL_GAMMA_CADDY_IMAGE:-$(library_image caddy:2.8.4-alpine)}"
export LOCAL_GAMMA_MINIO_IMAGE="${LOCAL_GAMMA_MINIO_IMAGE:-minio/minio:RELEASE.2025-04-22T22-12-26Z}"
export LOCAL_GAMMA_MINIO_MC_IMAGE="${LOCAL_GAMMA_MINIO_MC_IMAGE:-minio/mc:RELEASE.2025-03-12T17-29-24Z}"
# ES 镜像来自 elastic 官方 registry（非 docker.io/library），不经 library_image 前缀。
export LOCAL_GAMMA_ELASTICSEARCH_IMAGE="${LOCAL_GAMMA_ELASTICSEARCH_IMAGE:-docker.elastic.co/elasticsearch/elasticsearch:8.13.4}"
case "$(uname -m)" in
  arm64|aarch64)
    # Apple Silicon 的 Colima/VZ 会向 bundled JDK 报告 guest 无法执行的
    # SVE；ES CLI bootstrap 与运行时都必须在 Elasticsearch 启动前禁用它。
    export LOCAL_GAMMA_ELASTICSEARCH_CLI_JAVA_OPTS="${LOCAL_GAMMA_ELASTICSEARCH_CLI_JAVA_OPTS:--XX:UseSVE=0}"
    export LOCAL_GAMMA_ELASTICSEARCH_JAVA_OPTS="${LOCAL_GAMMA_ELASTICSEARCH_JAVA_OPTS:--XX:UseSVE=0 -Xms512m -Xmx512m}"
    ;;
  *)
    export LOCAL_GAMMA_ELASTICSEARCH_CLI_JAVA_OPTS="${LOCAL_GAMMA_ELASTICSEARCH_CLI_JAVA_OPTS:-}"
    export LOCAL_GAMMA_ELASTICSEARCH_JAVA_OPTS="${LOCAL_GAMMA_ELASTICSEARCH_JAVA_OPTS:--Xms512m -Xmx512m}"
    ;;
esac
export LOCAL_GAMMA_GO_BASE_IMAGE="${LOCAL_GAMMA_GO_BASE_IMAGE:?LOCAL_GAMMA_GO_BASE_IMAGE is required}"
export LOCAL_GAMMA_ALPINE_BASE_IMAGE="${LOCAL_GAMMA_ALPINE_BASE_IMAGE:?LOCAL_GAMMA_ALPINE_BASE_IMAGE is required}"
export LOCAL_GAMMA_PYTHON_BASE_IMAGE="${LOCAL_GAMMA_PYTHON_BASE_IMAGE:-$(library_image python:3.11-slim)}"
LOCAL_GAMMA_RTC_SOURCE_IMAGE_PLACEHOLDER="localhost/quwoquan_service_rtc-service:source-provenance-required"

local_gamma_service_default_image_ref() {
  case "$1" in
    recommendation-service) echo "localhost/quwoquan_service_recommendation-service:source-provenance-required" ;;
    content-service) echo "localhost/quwoquan_service_content-service:source-provenance-required" ;;
    chat-service) echo "localhost/quwoquan_service_chat-service:source-provenance-required" ;;
    user-service) echo "localhost/quwoquan_service_user-service:source-provenance-required" ;;
    assistant-service) echo "localhost/quwoquan_service_assistant-service:source-provenance-required" ;;
    product-ops-service) echo "localhost/quwoquan_service_product-ops-service:source-provenance-required" ;;
    platform-ops-service) echo "localhost/quwoquan_service_platform-ops-service:source-provenance-required" ;;
    tag-service) echo "localhost/quwoquan_service_tag-service:source-provenance-required" ;;
    search-service) echo "localhost/quwoquan_service_search-service:source-provenance-required" ;;
    entity-service) echo "localhost/quwoquan_service_entity-service:source-provenance-required" ;;
    circle-service) echo "localhost/quwoquan_service_circle-service:source-provenance-required" ;;
    integration-service) echo "localhost/quwoquan_service_integration-service:source-provenance-required" ;;
    notification-service) echo "localhost/quwoquan_service_notification-service:source-provenance-required" ;;
    rtc-service) echo "$LOCAL_GAMMA_RTC_SOURCE_IMAGE_PLACEHOLDER" ;;
    *) return 1 ;;
  esac
}

local_gamma_service_repository_name() {
  case "$1" in
    recommendation-service) echo "recommendation-service" ;;
    content-service|chat-service|user-service|assistant-service|product-ops-service|platform-ops-service|tag-service|search-service|entity-service|circle-service|integration-service|notification-service|rtc-service) echo "$1" ;;
    *) return 1 ;;
  esac
}

resolve_local_gamma_service_image_ref() {
  local service="$1"
  local default_ref=""
  default_ref="$(local_gamma_service_default_image_ref "$service")" || return 1
  local root="${LOCAL_GAMMA_IMAGE_REPOSITORY_ROOT:-}"
  local tag="${IMAGE_VERSION:-${LOCAL_GAMMA_IMAGE_VERSION:-}}"
  if [[ -n "$root" && -n "$tag" ]]; then
    printf '%s/%s:%s\n' \
      "${root%/}" \
      "$(local_gamma_service_repository_name "$service")" \
      "$tag"
    return 0
  fi
  printf '%s\n' "$default_ref"
}

export LOCAL_GAMMA_RECOMMENDATION_SERVICE_IMAGE="${LOCAL_GAMMA_RECOMMENDATION_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref recommendation-service)}"
export LOCAL_GAMMA_CONTENT_SERVICE_IMAGE="${LOCAL_GAMMA_CONTENT_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref content-service)}"
export LOCAL_GAMMA_CHAT_SERVICE_IMAGE="${LOCAL_GAMMA_CHAT_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref chat-service)}"
export LOCAL_GAMMA_USER_SERVICE_IMAGE="${LOCAL_GAMMA_USER_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref user-service)}"
export LOCAL_GAMMA_ASSISTANT_SERVICE_IMAGE="${LOCAL_GAMMA_ASSISTANT_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref assistant-service)}"
export LOCAL_GAMMA_PRODUCT_OPS_SERVICE_IMAGE="${LOCAL_GAMMA_PRODUCT_OPS_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref product-ops-service)}"
export LOCAL_GAMMA_PLATFORM_OPS_SERVICE_IMAGE="${LOCAL_GAMMA_PLATFORM_OPS_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref platform-ops-service)}"
export LOCAL_GAMMA_TAG_SERVICE_IMAGE="${LOCAL_GAMMA_TAG_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref tag-service)}"
export LOCAL_GAMMA_SEARCH_SERVICE_IMAGE="${LOCAL_GAMMA_SEARCH_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref search-service)}"
export LOCAL_GAMMA_ENTITY_SERVICE_IMAGE="${LOCAL_GAMMA_ENTITY_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref entity-service)}"
export LOCAL_GAMMA_CIRCLE_SERVICE_IMAGE="${LOCAL_GAMMA_CIRCLE_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref circle-service)}"
export LOCAL_GAMMA_INTEGRATION_SERVICE_IMAGE="${LOCAL_GAMMA_INTEGRATION_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref integration-service)}"
export LOCAL_GAMMA_NOTIFICATION_SERVICE_IMAGE="${LOCAL_GAMMA_NOTIFICATION_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref notification-service)}"
export LOCAL_GAMMA_RTC_SERVICE_IMAGE="${LOCAL_GAMMA_RTC_SERVICE_IMAGE:-$(resolve_local_gamma_service_image_ref rtc-service)}"

skip_build=0
skip_up=0
build_only=0
build_services_csv=""
print_env=0
down=0
tunnel_pid_file="${LOCAL_GAMMA_PROCESS_ROOT}/colima-tunnels.pids"
stack_report="${LOCAL_GAMMA_STACK_STATUS_REPORT}"
gamma_proxy_ensure_attempts=0
compose_up_timed_out=0
compose_build_timed_out=0

# wait_local_gamma_host_ready() 会在 podman/manual 与 docker compose 两条路径共用。
# docker compose 分支会在后面重载成真实探测逻辑；这里提供默认 noop，
# 避免 podman/manual 路径命中“command not found”。
ensure_docker_gamma_proxy_started() {
  return 0
}

local_gamma_has_existing_stack() {
  export_service_compose_environment
  if docker compose -p "$LOCAL_GAMMA_COMPOSE_PROJECT_NAME" "${COMPOSE_FILE_ARGS[@]}" ps -q 2>/dev/null | awk 'NF {found=1} END {exit found ? 0 : 1}'; then
    return 0
  fi
  if command -v podman >/dev/null 2>&1 && \
    podman ps -a --format '{{.Names}}' 2>/dev/null | awk '/^quwoquan_service_(gamma-proxy|assistant-service|user-service|chat-service|content-service|product-ops-service|platform-ops-service|tag-service|search-service|entity-service|circle-service|integration-service|notification-service|recommendation-service|elasticsearch|redis|mongodb|postgres)_1$/ {found=1} END {exit found ? 0 : 1}'; then
    return 0
  fi
  return 1
}

stop_colima_tunnels() {
  if [[ ! -f "$tunnel_pid_file" ]]; then
    return 0
  fi
  while IFS= read -r pid; do
    if [[ -n "$pid" ]]; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done < "$tunnel_pid_file"
  rm -f "$tunnel_pid_file"
}

LOCAL_GAMMA_MANAGED_CONTAINER_BASE_NAMES=(
  gamma-proxy
  assistant-service
  user-service
  chat-service
  content-service
  product-ops-service
  platform-ops-service
  tag-service
  search-service
  entity-service
  circle-service
  integration-service
  notification-service
  mongo-init
  recommendation-service
  elasticsearch
  redis
  mongodb
  postgres
)

cleanup_stale_named_gamma_containers() {
  local base_name=""
  local container_name=""
  local status=""
  for base_name in "${LOCAL_GAMMA_MANAGED_CONTAINER_BASE_NAMES[@]}"; do
    for container_name in "quwoquan_service_${base_name}_1" "quwoquan_service-${base_name}-1"; do
      status="$(docker inspect --format '{{.State.Status}}' "$container_name" 2>/dev/null || true)"
      if [[ -z "$status" ]]; then
        continue
      fi
      if [[ "$status" == "running" || "$status" == "restarting" || "$status" == "paused" ]]; then
        echo "[local-gamma] FAIL: unmanaged active container blocks canonical compose ownership: ${container_name} status=${status}" >&2
        return 1
      fi
      echo "[local-gamma] removing stale non-running container: ${container_name} status=${status}"
      docker rm "$container_name" >/dev/null
    done
  done
}

cleanup_existing_gamma_runtime() {
  local base_name=""
  local container_name=""
  local image_name=""
  for base_name in "${LOCAL_GAMMA_MANAGED_CONTAINER_BASE_NAMES[@]}"; do
    for container_name in "quwoquan_service_${base_name}_1" "quwoquan_service-${base_name}-1"; do
      docker rm -f "$container_name" >/dev/null 2>&1 || true
      if command -v podman >/dev/null 2>&1; then
        podman rm -f "$container_name" >/dev/null 2>&1 || true
      fi
    done
  done
  if command -v podman >/dev/null 2>&1; then
    podman pod rm -f quwoquan_service >/dev/null 2>&1 || true
    podman pod rm -f quwoquan_service_default >/dev/null 2>&1 || true
    if [[ "${skip_build:-0}" == "1" ]]; then
      return 0
    fi
    for image_name in \
      quwoquan_service_content-service \
      quwoquan_service_chat-service \
      quwoquan_service_user-service \
      quwoquan_service_assistant-service \
      quwoquan_service_product-ops-service \
      quwoquan_service_platform-ops-service \
      quwoquan_service_tag-service \
      quwoquan_service_search-service \
      quwoquan_service_entity-service \
      quwoquan_service_circle-service \
      quwoquan_service_integration-service \
      quwoquan_service_notification-service \
      quwoquan_service_recommendation-service \
      quwoquan_service_rtc-service; do
      podman rmi -f "$image_name" >/dev/null 2>&1 || true
      podman rmi -f "localhost/${image_name}:latest" >/dev/null 2>&1 || true
    done
  fi
}

host_port_open() {
  local port="$1"
  python3 - "$port" <<'PY'
import socket
import sys

port = sys.argv[1]
try:
    with socket.create_connection(("127.0.0.1", int(port)), timeout=2):
        pass
except OSError:
    raise SystemExit(1)
raise SystemExit(0)
PY
}

start_colima_tunnels_if_needed() {
  command -v colima >/dev/null 2>&1 || return 0
  command -v ssh >/dev/null 2>&1 || return 0
  [[ "$(docker context show 2>/dev/null || true)" == "colima" ]] || return 0

  local http_port="${LOCAL_GAMMA_HTTP_PORT:-19000}"
  local product_ops_port="${LOCAL_GAMMA_PRODUCT_OPS_PORT:-19010}"
  local media_edge_port="${LOCAL_GAMMA_MEDIA_EDGE_PORT:-19100}"
  # user-service 直连健康探针（wait_local_gamma_host_ready）使用 user_port，必须同步开隧道，
  # 否则 colima 下 host 无法直达 user-service 发布端口，host 就绪探测会卡死。
  local user_port="${LOCAL_GAMMA_USER_PORT:-19210}"
  local ssh_config="${QWQ_DEPLOY_WORK_ROOT}/gamma-local/runtime/colima-ssh-config"
  mkdir -p \
    "${LOCAL_GAMMA_PROCESS_ROOT}" \
    "${LOCAL_GAMMA_RUNTIME_LOG_ROOT}" \
    "${LOCAL_GAMMA_MODEL_CACHE_ROOT}" \
    "${LOCAL_GAMMA_LEGAL_STATIC_ROOT}" \
    "$(dirname "$ssh_config")"
  stop_colima_tunnels
  colima ssh-config > "$ssh_config"
  : > "$tunnel_pid_file"
  for port in "$http_port" "$product_ops_port" "$media_edge_port" "$user_port"; do
    if host_port_open "$port"; then
      continue
    fi
    nohup python3 "$ROOT/quwoquan_ops/cli/lib/runtime_log_process.py" \
      --log-file "${LOCAL_GAMMA_RUNTIME_LOG_ROOT}/colima-tunnel-${port}/local/runtime.log" \
      --event "colima-tunnel-${port}" -- \
      ssh -F "$ssh_config" -N -L "127.0.0.1:${port}:127.0.0.1:${port}" colima \
      </dev/null >/dev/null 2>&1 &
    echo "$!" >> "$tunnel_pid_file"
  done
  sleep 2
}

verify_public_dns() {
  python3 - "${PUBLIC_HOSTS[@]}" <<'PY'
import socket
import sys

failed = []
for host in sys.argv[1:]:
    resolved = sorted({item[4][0] for item in socket.getaddrinfo(host, None)})
    if not any(address.startswith("127.") or address == "::1" for address in resolved):
        failed.append(f"{host} -> {', '.join(resolved)}")
if failed:
    print("[local-gamma] GATE_BLOCK: gamma public hosts do not resolve to loopback:", file=sys.stderr)
    for item in failed:
        print(f"  - {item}", file=sys.stderr)
    raise SystemExit(1)
PY
}

usage() {
  cat <<'USAGE'
Usage: quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh [options]

Options:
  --skip-build   Do not build Docker images.
  --skip-up      Prepare artifacts only; do not docker compose up.
  --build-only   Build the requested service images without starting Compose.
  --build-services <csv>
                 Comma-separated service names; valid only with --build-only.
  --print-env    Print Flutter dart-defines for the local gamma mirror.
  --down         Stop the local gamma mirror.
  --help         Show this help.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-build) skip_build=1; shift ;;
    --skip-up) skip_up=1; shift ;;
    --build-only) build_only=1; shift ;;
    --build-services)
      [[ $# -ge 2 ]] || {
        echo "--build-services requires a comma-separated service list" >&2
        exit 2
      }
      build_services_csv="$2"
      shift 2
      ;;
    --print-env) print_env=1; shift ;;
    --down) down=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ "$build_only" == "1" && "$skip_build" == "1" ]]; then
  echo "--build-only cannot be combined with --skip-build" >&2
  exit 2
fi
if [[ "$build_only" == "1" && "$skip_up" == "1" ]]; then
  echo "--build-only cannot be combined with --skip-up" >&2
  exit 2
fi
if [[ -n "$build_services_csv" && "$build_only" != "1" ]]; then
  echo "--build-services is valid only with --build-only" >&2
  exit 2
fi
if [[ "$print_env" != "1" && "$skip_up" != "1" && "$build_only" != "1" && "$down" != "1" && "$LOCAL_GAMMA_RTC_SERVICE_IMAGE" == "$LOCAL_GAMMA_RTC_SOURCE_IMAGE_PLACEHOLDER" ]]; then
  echo "[local-gamma] FAIL: LOCAL_GAMMA_RTC_SERVICE_IMAGE must come from stackctl source provenance" >&2
  exit 2
fi
restarted_from_previous=0
if [[ "$print_env" != "1" ]] && local_gamma_has_existing_stack; then
  restarted_from_previous=1
fi

prepare_config_root() {
  local out="${LOCAL_GAMMA_CONFIG_ROOT}"
  local package_root
  package_root="$(PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - "$CONFIG_SOURCE_ENV" <<'PY'
import sys
from quwoquan_ops.cli.lib.output_paths import deployment_package_root

print(deployment_package_root(sys.argv[1]))
PY
)"

  copy_service_package_config() {
    local service="$1"
    local package_dir="${package_root}/services/${service}"
    local config_file="${package_dir}/config/config.yaml"
    local provenance_file="${package_dir}/provenance.json"
    if [[ ! -f "$config_file" || ! -f "$provenance_file" ]]; then
      echo "[local-gamma] FAIL: missing autonomous service package for ${service}: ${package_dir}" >&2
      return 1
    fi
    local config_version
    config_version="$(PYTHONDONTWRITEBYTECODE=1 python3 - "$service" "$CONFIG_SOURCE_ENV" "$config_file" "$provenance_file" <<'PY'
import hashlib
import json
import re
import sys
from pathlib import Path

service, environment, config_value, provenance_value = sys.argv[1:5]
config_path = Path(config_value)
provenance_path = Path(provenance_value)
provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
actual = "sha256:" + hashlib.sha256(config_path.read_bytes()).hexdigest()
if provenance.get("service") != service or provenance.get("environment") != environment:
    raise SystemExit(f"service package identity mismatch: {provenance_path}")
if (provenance.get("digests") or {}).get("config") != actual:
    raise SystemExit(f"service package config digest mismatch: {config_path}")
version = str(provenance.get("configVersion") or "")
if not re.fullmatch(r"sha256:[0-9a-f]{64}", version):
    raise SystemExit(f"invalid derived config version: {provenance_path}")
print(version)
PY
)" || return 1
    cp "$config_file" "$out/${service}.yaml"
    local service_env_key
    service_env_key="$(printf '%s' "$service" | tr '[:lower:]-' '[:upper:]_')"
    local version_var="LOCAL_GAMMA_${service_env_key}_CONFIG_VERSION"
    export "${version_var}=${config_version}"
  }

  rm -rf "$out"
  mkdir -p "$out/quwoquan_service/runtime/reliabletask/resources"
  local service
  for service in \
    assistant-service \
    chat-service \
    circle-service \
    content-service \
    entity-service \
    integration-service \
    notification-service \
    product-ops-service \
    realtime-gateway \
    recommendation-service \
    rtc-service \
    search-service \
    tag-service \
    user-service \
    platform-ops-service; do
    copy_service_package_config "$service"
  done

  local -a report_account_backfill_args=(
    --write-report-account-backfill
    gamma
    gamma-local
    "$out/report-account-backfill.json"
  )
  if [[ "$ENABLE_FIXTURE_SEEDS" != "1" ]]; then
    report_account_backfill_args+=(--empty)
  fi
  PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 \
    python3 -m quwoquan_ops.cli.lib.local_environment_auth \
      "${report_account_backfill_args[@]}" >/dev/null

  if [[ ! -f "$package_root/runtime-shared/module_catalog.yaml" || ! -f "$package_root/runtime-shared/retention_policy.yaml" ]]; then
    echo "[local-gamma] FAIL: missing runtime shared package: $package_root/runtime-shared" >&2
    return 1
  fi
  cp "$package_root/runtime-shared/module_catalog.yaml" "$out/quwoquan_service/runtime/reliabletask/resources/module_catalog.yaml"
  cp "$package_root/runtime-shared/retention_policy.yaml" "$out/quwoquan_service/runtime/reliabletask/resources/retention_policy.yaml"
}

verify_canonical_video_materialization() {
  python3 "$ROOT/quwoquan_ops/cli/lib/local_gamma_media.py" \
    verify --target-root "$LOCAL_GAMMA_MEDIA_ROOT"
}

prepare_media_root() {
  local media="${LOCAL_GAMMA_MEDIA_ROOT}"
  local canonical_media_root="$ROOT/quwoquan_service/contracts/metadata/_shared/test_fixtures/media"
  local required_sample="$media/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png"
  local required_avatar="$media/media/avatar/s/archived-avatar/circle/fixture_circle_coffee_04/v1/avatar.png"
  local required_video="$media/media/video/s/video-primary-0001/post/video-content-0001/source.mp4"
  local media_file_count=0
  if [[ -d "$media/media" ]]; then
    media_file_count="$(find "$media/media" -type f | wc -l | tr -d '[:space:]')"
    if [[ -f "$required_sample" && -f "$required_avatar" && -f "$required_video" && "$media_file_count" -ge 1000 ]]; then
      verify_canonical_video_materialization
      echo "[local-gamma] reuse pre-synced full shared media bundle: $media"
      return 0
    fi
    echo "[local-gamma] gamma media root is incomplete; rebuilding full shared media bundle: $media (files=$media_file_count)" >&2
    rm -rf "$media"
  fi
  if [[ "$ENABLE_FIXTURE_SEEDS" != "1" ]]; then
    echo "[local-gamma] FAIL: STAGE=${STAGE} requires an existing media root at ${media}/media" >&2
    return 1
  fi
  if [[ -d "$canonical_media_root" ]]; then
    python3 "$ROOT/quwoquan_ops/cli/lib/local_gamma_media.py" \
      materialize --target-root "$media"
    return 0
  fi
  echo "[local-gamma] FAIL: curated gamma media bundle is unavailable; sync ${LOCAL_GAMMA_MEDIA_ROOT} first" >&2
  return 1
}

validate_caddyfile_source() {
  if [[ ! -f "$LOCAL_GAMMA_CADDYFILE" ]]; then
    echo "[local-gamma] FAIL: missing Ops-owned Caddyfile: $LOCAL_GAMMA_CADDYFILE" >&2
    return 1
  fi
}

print_defines() {
  if ! python3 - <<'PY' >/dev/null 2>&1; then
import sys
raise SystemExit(0 if sys.version_info >= (3, 7) else 1)
PY
    echo "[local-gamma] skip dart defines: python3 >= 3.7 required" >&2
    return 0
  fi

  python3 "$ROOT/quwoquan_app/scripts/env/print_app_env_dart_defines.py" \
    --env "$LOCAL_GAMMA_APP_ENV" \
    --target gamma-local
}

preflight_local_gamma_inputs() {
  if [[ ! -d "$LOCAL_GAMMA_TAGS_DIR" ]]; then
    echo "[local-gamma] FAIL: missing canonical control-plane taxonomy: $LOCAL_GAMMA_TAGS_DIR" >&2
    return 1
  fi
  if [[ ! -f "$LOCAL_GAMMA_TAG_OBJECTS_FILE" ]]; then
    echo "[local-gamma] FAIL: missing object_tag_index fixture: $LOCAL_GAMMA_TAG_OBJECTS_FILE" >&2
    return 1
  fi
}

run_docker_probe_with_timeout() {
  local probe_pid=""
  local deadline=""
  local timeout_seconds="${LOCAL_GAMMA_DOCKER_PROBE_TIMEOUT_SECONDS:?LOCAL_GAMMA_DOCKER_PROBE_TIMEOUT_SECONDS is required}"
  if ! [[ "$timeout_seconds" =~ ^[1-9][0-9]*$ ]]; then
    echo "[local-gamma] FAIL: LOCAL_GAMMA_DOCKER_PROBE_TIMEOUT_SECONDS must be a positive integer" >&2
    return 2
  fi

  docker info --format '{{.ServerVersion}} {{.Driver}}' >/dev/null 2>&1 &
  probe_pid="$!"
  LOCAL_GAMMA_ACTIVE_CHILD_PID="$probe_pid"
  deadline=$((SECONDS + timeout_seconds))
  while kill -0 "$probe_pid" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      echo "[local-gamma] GATE_BLOCK: Docker daemon did not answer readiness probe within ${timeout_seconds}s" >&2
      kill "$probe_pid" >/dev/null 2>&1 || true
      wait "$probe_pid" >/dev/null 2>&1 || true
      LOCAL_GAMMA_ACTIVE_CHILD_PID=""
      return 124
    fi
    sleep 1
  done
  if wait "$probe_pid"; then
    LOCAL_GAMMA_ACTIVE_CHILD_PID=""
    return 0
  else
    local probe_status=$?
    LOCAL_GAMMA_ACTIVE_CHILD_PID=""
    return "$probe_status"
  fi
}

preflight_docker_daemon() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "[local-gamma] GATE_BLOCK: docker is required for gamma-local" >&2
    return 1
  fi
  echo "[local-gamma] checking Docker daemon readiness before compose build"
  run_docker_probe_with_timeout
}

ensure_local_gamma_base_images() {
  [[ "${podman_compose:-0}" == "1" ]] || return 0
  local image=""
  local -a required_images=(
    "$LOCAL_GAMMA_GO_BOOKWORM_IMAGE"
    "$LOCAL_GAMMA_ALPINE_BASE_IMAGE"
    "$LOCAL_GAMMA_PYTHON_BASE_IMAGE"
    "$LOCAL_GAMMA_POSTGRES_IMAGE"
    "$LOCAL_GAMMA_MONGO_IMAGE"
    "$LOCAL_GAMMA_REDIS_IMAGE"
    "$LOCAL_GAMMA_CADDY_IMAGE"
    "$LOCAL_GAMMA_ELASTICSEARCH_IMAGE"
  )
  for image in "${required_images[@]}"; do
    [[ -n "$image" ]] || continue
    if podman image exists "$image" >/dev/null 2>&1; then
      continue
    fi
    echo "[local-gamma] pulling missing base image: $image"
    podman pull --arch amd64 "$image" || podman pull "$image" || {
      echo "[local-gamma] FAIL: unable to pull required base image: $image" >&2
      return 1
    }
  done
}

expected_local_gamma_built_image_ref() {
  case "$1" in
    recommendation-service) printf '%s\n' "$LOCAL_GAMMA_RECOMMENDATION_SERVICE_IMAGE" ;;
    content-service) printf '%s\n' "$LOCAL_GAMMA_CONTENT_SERVICE_IMAGE" ;;
    chat-service) printf '%s\n' "$LOCAL_GAMMA_CHAT_SERVICE_IMAGE" ;;
    user-service) printf '%s\n' "$LOCAL_GAMMA_USER_SERVICE_IMAGE" ;;
    assistant-service) printf '%s\n' "$LOCAL_GAMMA_ASSISTANT_SERVICE_IMAGE" ;;
    product-ops-service) printf '%s\n' "$LOCAL_GAMMA_PRODUCT_OPS_SERVICE_IMAGE" ;;
    platform-ops-service) printf '%s\n' "$LOCAL_GAMMA_PLATFORM_OPS_SERVICE_IMAGE" ;;
    tag-service) printf '%s\n' "$LOCAL_GAMMA_TAG_SERVICE_IMAGE" ;;
    search-service) printf '%s\n' "$LOCAL_GAMMA_SEARCH_SERVICE_IMAGE" ;;
    entity-service) printf '%s\n' "$LOCAL_GAMMA_ENTITY_SERVICE_IMAGE" ;;
    circle-service) printf '%s\n' "$LOCAL_GAMMA_CIRCLE_SERVICE_IMAGE" ;;
    integration-service) printf '%s\n' "$LOCAL_GAMMA_INTEGRATION_SERVICE_IMAGE" ;;
    notification-service) printf '%s\n' "$LOCAL_GAMMA_NOTIFICATION_SERVICE_IMAGE" ;;
    rtc-service) printf '%s\n' "$LOCAL_GAMMA_RTC_SERVICE_IMAGE" ;;
    *) return 1 ;;
  esac
}

validate_local_gamma_built_images() {
  local service=""
  local image_ref=""
  for service in "${compose_build_services[@]}"; do
    image_ref="$(expected_local_gamma_built_image_ref "$service" || true)"
    [[ -n "$image_ref" ]] || continue
    if [[ "${podman_compose:-0}" == "1" ]]; then
      if podman image exists "$image_ref" >/dev/null 2>&1; then
        continue
      fi
    elif docker image inspect "$image_ref" >/dev/null 2>&1; then
      continue
    fi
    echo "[local-gamma] GATE_BLOCK: packaged image is unavailable: $image_ref" >&2
    echo "[local-gamma] Repair: run stackctl up without --skip-build to build the package-bound image." >&2
    return 1
  done
  return 0
}

podman_build_log_has_nonzero_exit_codes() {
  python3 - "$1" <<'PY'
from pathlib import Path
import re
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
codes = [int(match.group(1)) for match in re.finditer(r"(?m)^exit code:\s*(\d+)\s*$", text)]
raise SystemExit(0 if any(code != 0 for code in codes) else 1)
PY
}

run_compose_build() {
  local build_log="${QWQ_RUN_ROOT}/attachments/docker-build.log"
  local build_status=0
  mkdir -p "$(dirname "$build_log")"
  : >"$build_log"
  if ! preflight_docker_daemon; then
    echo "[local-gamma] FAIL: Docker preflight did not complete; startup aborted." >&2
    return 1
  fi
  ensure_local_gamma_base_images
  echo "[local-gamma] building services: ${compose_build_services[*]}"
  run_compose_build_with_timeout "$build_log" || build_status=$?
  if [[ "$build_status" -eq 0 && "${podman_compose:-0}" == "1" ]]; then
    if podman_build_log_has_nonzero_exit_codes "$build_log"; then
      echo "[local-gamma] FAIL: podman-compose build reported non-zero inner exit codes." >&2
      build_status=1
    fi
  fi
  if [[ "$build_status" -eq 0 ]] && ! validate_local_gamma_built_images; then
    build_status=1
  fi
  if [[ "$build_status" -eq 0 ]]; then
    return 0
  fi
  if python3 - "$build_log" <<'PY'
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace").lower()
raise SystemExit(0 if "no space left on device" in text else 1)
PY
  then
    echo "[local-gamma] FAIL: image build exhausted Docker/Colima disk ('no space left on device')." >&2
    echo "[local-gamma] Reclaim local container storage and rerun:" >&2
    echo "[local-gamma]   docker system df" >&2
    echo "[local-gamma]   docker builder prune -af" >&2
    echo "[local-gamma]   docker image prune -af" >&2
    echo "[local-gamma]   docker volume prune -f" >&2
    echo "[local-gamma]   colima stop && colima start --disk 100" >&2
  fi
  echo "[local-gamma] FAIL: image build failed; startup aborted. Build log: $build_log" >&2
  return 1
}

run_compose_build_with_timeout() {
  local build_log="$1"
  local compose_pid=""
  local deadline=""
  local last_progress_seconds=""
  local last_log_size="0"
  local current_log_size="0"
  local timeout_seconds="${LOCAL_GAMMA_COMPOSE_BUILD_TIMEOUT_SECONDS:?LOCAL_GAMMA_COMPOSE_BUILD_TIMEOUT_SECONDS is required}"
  local no_progress_timeout_seconds="${LOCAL_GAMMA_COMPOSE_BUILD_NO_PROGRESS_TIMEOUT_SECONDS:?LOCAL_GAMMA_COMPOSE_BUILD_NO_PROGRESS_TIMEOUT_SECONDS is required}"
  # Each service build compiles a complete Go module. Limit local Compose
  # concurrency so a onebox cannot exhaust its container filesystem with
  # simultaneous /tmp/go-build directories.
  local compose_parallel_limit="${LOCAL_GAMMA_COMPOSE_BUILD_PARALLEL_LIMIT:-1}"
  if ! [[ "$timeout_seconds" =~ ^[1-9][0-9]*$ ]]; then
    echo "[local-gamma] FAIL: LOCAL_GAMMA_COMPOSE_BUILD_TIMEOUT_SECONDS must be a positive integer" >&2
    return 2
  fi
  if ! [[ "$no_progress_timeout_seconds" =~ ^[1-9][0-9]*$ ]]; then
    echo "[local-gamma] FAIL: LOCAL_GAMMA_COMPOSE_BUILD_NO_PROGRESS_TIMEOUT_SECONDS must be a positive integer" >&2
    return 2
  fi
  if ! [[ "$compose_parallel_limit" =~ ^[1-9][0-9]*$ ]]; then
    echo "[local-gamma] FAIL: LOCAL_GAMMA_COMPOSE_BUILD_PARALLEL_LIMIT must be a positive integer" >&2
    return 2
  fi

  env \
    COMPOSE_PARALLEL_LIMIT="$compose_parallel_limit" \
    "${compose_cmd[@]}" build "${compose_build_services[@]}" >"$build_log" 2>&1 &
  compose_pid="$!"
  LOCAL_GAMMA_ACTIVE_CHILD_PID="$compose_pid"
  deadline=$((SECONDS + timeout_seconds))
  last_progress_seconds="$SECONDS"
  while kill -0 "$compose_pid" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      compose_build_timed_out=1
      echo "[local-gamma] FAIL: compose build exceeded ${timeout_seconds}s; preserving build log for inspection" >&2
      kill "$compose_pid" >/dev/null 2>&1 || true
      wait "$compose_pid" >/dev/null 2>&1 || true
      LOCAL_GAMMA_ACTIVE_CHILD_PID=""
      return 124
    fi
    current_log_size=$(wc -c <"$build_log")
    if [[ "$current_log_size" != "$last_log_size" ]]; then
      last_log_size="$current_log_size"
      last_progress_seconds="$SECONDS"
    elif (( SECONDS - last_progress_seconds >= no_progress_timeout_seconds )); then
      echo "[local-gamma] FAIL: compose build produced no log progress for ${no_progress_timeout_seconds}s; preserving build log for inspection" >&2
      kill "$compose_pid" >/dev/null 2>&1 || true
      wait "$compose_pid" >/dev/null 2>&1 || true
      LOCAL_GAMMA_ACTIVE_CHILD_PID=""
      return 125
    fi
    sleep 1
  done
  if wait "$compose_pid"; then
    LOCAL_GAMMA_ACTIVE_CHILD_PID=""
    return 0
  else
    local compose_status=$?
    LOCAL_GAMMA_ACTIVE_CHILD_PID=""
    return "$compose_status"
  fi
}

prepare_down_compose_environment() {
  # `docker compose down` still interpolates every declared service.  Teardown
  # must therefore be independent from a prior successful config render: these
  # values are parse-only placeholders and are never used to start a process.
  local down_config_version="${LOCAL_GAMMA_CONFIG_VERSION:-local-gamma-down}"
  local service=""
  local service_key=""
  local version_key=""
  for service in \
    assistant-service \
    chat-service \
    circle-service \
    content-service \
    entity-service \
    integration-service \
    notification-service \
    product-ops-service \
    realtime-gateway \
    recommendation-service \
    rtc-service \
    search-service \
    tag-service \
    user-service \
    platform-ops-service; do
    service_key="$(printf '%s' "$service" | tr '[:lower:]-' '[:upper:]_')"
    version_key="LOCAL_GAMMA_${service_key}_CONFIG_VERSION"
    if [[ -z "${!version_key:-}" ]]; then
      printf -v "$version_key" '%s' "$down_config_version"
    fi
    export "$version_key"
  done
  : "${LOCAL_GAMMA_REC_POLICY_SOURCE:=down-not-used}"
  : "${LOCAL_GAMMA_REALTIME_GATEWAY_IMAGE:=localhost/quwoquan_service_realtime_gateway:down}"
  : "${LOCAL_GAMMA_RTC_SERVICE_IMAGE:=localhost/quwoquan_service_rtc_service:down}"
  export \
    LOCAL_GAMMA_CONFIG_ROOT \
    LOCAL_GAMMA_REC_POLICY_SOURCE \
    LOCAL_GAMMA_REALTIME_GATEWAY_IMAGE \
    LOCAL_GAMMA_RTC_SERVICE_IMAGE
  export_service_compose_environment
}

if [[ "$print_env" == "1" ]]; then
  # This is an introspection command. It must not render configuration, create
  # runtime output, touch Docker, or alter the currently running environment.
  print_defines
  exit 0
fi

if [[ "$down" == "1" ]]; then
  stop_colima_tunnels
  prepare_down_compose_environment
  docker compose -p "$LOCAL_GAMMA_COMPOSE_PROJECT_NAME" "${COMPOSE_FILE_ARGS[@]}" down
  cleanup_stale_named_gamma_containers
  rm -f "$stack_report"
  exit 0
fi

prepare_config_root
prepare_media_root
mkdir -p \
  "${LOCAL_GAMMA_DEPLOY_RENDER_ROOT}" \
  "${LOCAL_GAMMA_PROCESS_ROOT}" \
  "${LOCAL_GAMMA_RUNTIME_LOG_ROOT}" \
  "${LOCAL_GAMMA_CACHE_ROOT}" \
  "${LOCAL_GAMMA_MODEL_CACHE_ROOT}" \
  "${GAMMA_RUN_ROOT}" \
  "${LOCAL_GAMMA_LEGAL_STATIC_ROOT}" \
  "${LOCAL_GAMMA_PORTAL_ROOT}" \
  "${QWQ_OUTPUT_ROOT}/env/repo/local/control-plane/process/platform-ops-service"
validate_caddyfile_source

if [[ "$skip_up" == "1" ]]; then
  echo "[local-gamma] prepared artifacts only"
  echo "[local-gamma] configVersion=$CONFIG_VERSION imageVersion=$IMAGE_VERSION"
  exit 0
fi

if [[ "$ENABLE_FIXTURE_SEEDS" == "1" ]]; then
  preflight_local_gamma_inputs
fi

podman_compose=0
export_service_compose_environment
if docker --version 2>/dev/null | grep -qi 'podman' && command -v podman-compose >/dev/null 2>&1; then
  podman_compose=1
  compose_cmd=(podman-compose "${COMPOSE_FILE_ARGS[@]}" --podman-build-args=--pull=never --podman-run-args=--pull=never)
  compose_up_args=(up -d --no-build)
else
  compose_cmd=(docker compose -p "$LOCAL_GAMMA_COMPOSE_PROJECT_NAME" "${COMPOSE_FILE_ARGS[@]}")
  compose_up_args=(up -d --remove-orphans)
  if [[ "$skip_build" == "1" ]]; then
    compose_up_args+=(--no-build)
  fi
fi

prepare_local_gamma_mongosh() {
  local container_cli="$1"
  if command -v mongosh >/dev/null 2>&1; then
    return 0
  fi
  local wrapper_dir="${LOCAL_GAMMA_PROCESS_ROOT}/bin"
  mkdir -p "$wrapper_dir"
  cat > "${wrapper_dir}/mongosh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

container_cli="${LOCAL_GAMMA_CONTAINER_CLI:?LOCAL_GAMMA_CONTAINER_CLI is required}"
container_name=""
for candidate in quwoquan_service-mongodb-1 quwoquan_service_mongodb_1; do
  if "$container_cli" inspect "$candidate" >/dev/null 2>&1; then
    container_name="$candidate"
    break
  fi
done
if [[ -z "$container_name" ]]; then
  echo "local-gamma mongosh wrapper cannot find the MongoDB container" >&2
  exit 1
fi

rewritten=()
for arg in "$@"; do
  case "$arg" in
    mongodb://127.0.0.1:*)
      rewritten+=("mongodb://127.0.0.1:27017/?directConnection=true")
      ;;
    *)
      rewritten+=("$arg")
      ;;
  esac
done
exec "$container_cli" exec -i "$container_name" mongosh "${rewritten[@]}"
SH
  chmod 0755 "${wrapper_dir}/mongosh"
  export LOCAL_GAMMA_CONTAINER_CLI="$container_cli"
  export PATH="${wrapper_dir}:${PATH}"
}

if [[ "$podman_compose" == "1" ]]; then
  prepare_local_gamma_mongosh podman
else
  prepare_local_gamma_mongosh docker
fi

compose_build_services=(
  recommendation-service
  content-service
  chat-service
  user-service
  assistant-service
  product-ops-service
  platform-ops-service
  tag-service
  search-service
  entity-service
  circle-service
  integration-service
  notification-service
)
if [[ "$PRODUCT_TELEMETRY_AVAILABLE" != "1" ]]; then
  filtered_build_services=()
  for service_name in "${compose_build_services[@]}"; do
    [[ "$service_name" == "product-ops-service" ]] || filtered_build_services+=("$service_name")
  done
  compose_build_services=("${filtered_build_services[@]}")
fi
if [[ "$WORKLOAD" == "content-release" ]]; then
  filtered_build_services=()
  for service_name in "${compose_build_services[@]}"; do
    [[ "$service_name" == "assistant-service" ]] || filtered_build_services+=("$service_name")
  done
  compose_build_services=("${filtered_build_services[@]}")
fi
if [[ ",${COMPOSE_PROFILES:-}," == *,edge-media,* ]]; then
  compose_build_services+=(realtime-gateway)
  compose_build_services+=(rtc-service)
fi

if [[ -n "$build_services_csv" ]]; then
  requested_build_services=()
  IFS=',' read -r -a requested_build_services <<< "$build_services_csv"
  selected_build_services=()
  selected_build_service_count=0
  for requested_service in "${requested_build_services[@]}"; do
    requested_service="$(printf '%s' "$requested_service" | tr -d '[:space:]')"
    [[ -n "$requested_service" ]] || continue
    service_allowed=0
    for available_service in "${compose_build_services[@]}"; do
      if [[ "$available_service" == "$requested_service" ]]; then
        service_allowed=1
        break
      fi
    done
    if [[ "$service_allowed" != "1" ]]; then
      echo "[local-gamma] FAIL: --build-services contains unavailable service '$requested_service' for workload=$WORKLOAD" >&2
      exit 2
    fi
    if [[ "$selected_build_service_count" -gt 0 ]]; then
      for selected_service in "${selected_build_services[@]}"; do
        if [[ "$selected_service" == "$requested_service" ]]; then
          echo "[local-gamma] FAIL: --build-services contains duplicate '$requested_service'" >&2
          exit 2
        fi
      done
    fi
    selected_build_services+=("$requested_service")
    selected_build_service_count=$((selected_build_service_count + 1))
  done
  if [[ "$selected_build_service_count" == "0" ]]; then
    echo "[local-gamma] FAIL: --build-services must contain at least one service" >&2
    exit 2
  fi
  compose_build_services=("${selected_build_services[@]}")
fi

if [[ "$FORCE_CLEAN_RECREATE" == "1" ]]; then
  echo "[local-gamma] forcing clean recreate of existing gamma containers"
  cleanup_existing_gamma_runtime
  if [[ "$podman_compose" != "1" ]]; then
    compose_up_args+=(--force-recreate)
  fi
fi

if [[ "$skip_build" == "0" ]]; then
  run_compose_build
elif ! validate_local_gamma_built_images; then
  exit 1
fi
if [[ "$build_only" == "1" ]]; then
  echo "[local-gamma] built services only: ${compose_build_services[*]}"
  exit 0
fi
export LOCAL_GAMMA_CONFIG_VERSION="$CONFIG_VERSION"
export LOCAL_GAMMA_IMAGE_VERSION="$IMAGE_VERSION"
export LOCAL_GAMMA_APP_ENV
export LOCAL_GAMMA_READY_INDEX_STREAM
export LOCAL_GAMMA_READY_INDEX_GROUP
export LOCAL_GAMMA_READY_INDEX_QUEUE
if [[ "$podman_compose" == "1" ]]; then
  echo "[local-gamma] startup mode: podman-manual"
  wait_healthy() {
    local name="$1"
    local status=""
    for _ in $(seq 1 60); do
      status="$(podman inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$name" 2>/dev/null || true)"
      if [[ "$status" == "healthy" || "$status" == "running" ]]; then
        return 0
      fi
      sleep 2
    done
    echo "[local-gamma] container did not become healthy: $name status=$status" >&2
    podman logs --tail 80 "$name" >&2 || true
    return 1
  }

  wait_running() {
    local name="$1"
    local status=""
    for _ in $(seq 1 60); do
      status="$(podman inspect --format '{{.State.Status}}' "$name" 2>/dev/null || true)"
      if [[ "$status" == "running" ]]; then
        return 0
      fi
      sleep 2
    done
    echo "[local-gamma] container did not start: $name status=$status" >&2
    podman logs --tail 80 "$name" >&2 || true
    return 1
  }

  wait_exited_zero() {
    local name="$1"
    local status=""
    local exit_code=""
    for _ in $(seq 1 60); do
      status="$(podman inspect --format '{{.State.Status}}' "$name" 2>/dev/null || true)"
      exit_code="$(podman inspect --format '{{.State.ExitCode}}' "$name" 2>/dev/null || true)"
      if [[ "$status" == "exited" && "$exit_code" == "0" ]]; then
        return 0
      fi
      sleep 2
    done
    echo "[local-gamma] one-shot container failed: $name status=$status exit=$exit_code" >&2
    podman logs --tail 80 "$name" >&2 || true
    return 1
  }

  network_name="quwoquan_service_default"
  for container_name in \
    quwoquan_service_gamma-proxy_1 \
    quwoquan_service_assistant-service_1 \
    quwoquan_service_user-service_1 \
    quwoquan_service_chat-service_1 \
    quwoquan_service_content-service_1 \
    quwoquan_service_product-ops-service_1 \
    quwoquan_service_platform-ops-service_1 \
    quwoquan_service_tag-service_1 \
    quwoquan_service_search-service_1 \
    quwoquan_service_entity-service_1 \
    quwoquan_service_circle-service_1 \
    quwoquan_service_integration-service_1 \
    quwoquan_service_notification-service_1 \
    quwoquan_service_mongo-init_1 \
    quwoquan_service_recommendation-service_1 \
    quwoquan_service_elasticsearch_1 \
    quwoquan_service_redis_1 \
    quwoquan_service_mongodb_1 \
    quwoquan_service_postgres_1; do
    podman rm -f "$container_name" >/dev/null 2>&1 || true
  done
  podman network exists "$network_name" || podman network create "$network_name" >/dev/null
  # Default cold-build path still recreates Postgres for deterministic startup.
  # Restart/rollout mode may preserve the volume to avoid unnecessary full DB bootstrap.
  if [[ "$PRESERVE_POSTGRES_VOLUME" != "1" ]]; then
    podman volume rm -f quwoquan_service_local-gamma-postgres >/dev/null 2>&1 || true
  fi
  podman volume inspect quwoquan_service_local-gamma-postgres >/dev/null 2>&1 || podman volume create quwoquan_service_local-gamma-postgres >/dev/null
  podman volume inspect quwoquan_service_local-gamma-mongo >/dev/null 2>&1 || podman volume create quwoquan_service_local-gamma-mongo >/dev/null
  podman volume inspect quwoquan_service_local-gamma-redis >/dev/null 2>&1 || podman volume create quwoquan_service_local-gamma-redis >/dev/null
  podman volume inspect quwoquan_service_local-gamma-go-cache >/dev/null 2>&1 || podman volume create quwoquan_service_local-gamma-go-cache >/dev/null
  podman volume inspect quwoquan_service_local-gamma-es >/dev/null 2>&1 || podman volume create quwoquan_service_local-gamma-es >/dev/null

  podman run --pull=never --name quwoquan_service_postgres_1 -d \
    --net "$network_name" --network-alias postgres \
    -e POSTGRES_USER=quwoquan -e POSTGRES_PASSWORD=quwoquan -e POSTGRES_DB=quwoquan \
    -v quwoquan_service_local-gamma-postgres:/var/lib/postgresql/data \
    -p "${LOCAL_GAMMA_POSTGRES_PORT:-19400}:5432" \
    --healthcheck-command "pg_isready -U quwoquan" \
    --healthcheck-interval 5s --healthcheck-timeout 3s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_POSTGRES_IMAGE" >/dev/null

  podman run --pull=never --name quwoquan_service_mongodb_1 -d \
    --net "$network_name" --network-alias mongodb \
    -v quwoquan_service_local-gamma-mongo:/data/db \
    -p "${LOCAL_GAMMA_MONGO_PORT:-19410}:27017" \
    "$LOCAL_GAMMA_MONGO_IMAGE" \
    --replSet rs0 \
    --bind_ip_all \
    --wiredTigerCacheSizeGB "${LOCAL_GAMMA_MONGO_CACHE_SIZE_GB}" >/dev/null

  podman run --pull=never --name quwoquan_service_redis_1 -d \
    --net "$network_name" --network-alias redis \
    -v quwoquan_service_local-gamma-redis:/data \
    -p "${LOCAL_GAMMA_REDIS_PORT:-19420}:6379" \
    --healthcheck-command "redis-cli ping" \
    --healthcheck-interval 5s --healthcheck-timeout 3s --healthcheck-retries 20 \
    "$LOCAL_GAMMA_REDIS_IMAGE" redis-server --appendonly yes >/dev/null

  podman run --pull=never --name quwoquan_service_elasticsearch_1 -d \
    --net "$network_name" --network-alias elasticsearch \
    -e discovery.type=single-node \
    -e xpack.security.enabled=false \
    -e xpack.security.http.ssl.enabled=false \
    -e CLI_JAVA_OPTS="$LOCAL_GAMMA_ELASTICSEARCH_CLI_JAVA_OPTS" \
    -e ES_JAVA_OPTS="$LOCAL_GAMMA_ELASTICSEARCH_JAVA_OPTS" \
    -v quwoquan_service_local-gamma-es:/usr/share/elasticsearch/data \
    -p "${LOCAL_GAMMA_ES_PORT:-19430}:9200" \
    --healthcheck-command "curl -fsS 'http://localhost:9200/_cluster/health?wait_for_status=yellow&timeout=1s' || exit 1" \
    --healthcheck-interval 10s --healthcheck-timeout 5s --healthcheck-start-period 120s --healthcheck-retries 30 \
    "$LOCAL_GAMMA_ELASTICSEARCH_IMAGE" >/dev/null

  wait_healthy quwoquan_service_postgres_1
  wait_running quwoquan_service_mongodb_1
  sleep 5
  wait_healthy quwoquan_service_redis_1
  wait_healthy quwoquan_service_elasticsearch_1

  podman run --pull=never --rm --name quwoquan_service_mongo-init_1 \
    --net "$network_name" --network-alias mongo-init \
    "$LOCAL_GAMMA_MONGO_IMAGE" bash -lc "mongosh --host mongodb:27017 --quiet --eval '
      try {
        rs.status().ok
      } catch (e) {
        rs.initiate({_id: \"rs0\", members: [{_id: 0, host: \"mongodb:27017\"}]})
      }
    '" >/dev/null

  podman run --pull=never --name quwoquan_service_recommendation-service_1 -d \
    --net "$network_name" --network-alias recommendation-service --network-alias recommendation-service \
    -e SERVICE_NAME=recommendation-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e PYTHONUNBUFFERED=1 \
    -e MODEL_CACHE_DIR=/app/cache \
    -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
    -v "${LOCAL_GAMMA_MODEL_CACHE_ROOT}:/app/cache" \
    -p "${LOCAL_GAMMA_REC_MODEL_PORT:-19240}:8000" \
    --healthcheck-command "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')\" || exit 1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 5 \
    "$LOCAL_GAMMA_RECOMMENDATION_SERVICE_IMAGE" >/dev/null
  wait_healthy quwoquan_service_recommendation-service_1

  if [[ "$PRODUCT_TELEMETRY_AVAILABLE" == "1" ]]; then
    podman run --pull=never --name quwoquan_service_product-ops-service_1 -d \
      --net "$network_name" --network-alias product-ops-service \
      -e SERVICE_NAME=product-ops-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
      -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
      -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e PRODUCT_OPS_SERVICE_ADDR=:18086 \
      -e MONGO_URI=mongodb://mongodb:27017 \
      -e POSTGRES_DSN='postgres://quwoquan:quwoquan@postgres:5432/quwoquan?sslmode=disable' \
      -e PRODUCT_OPS_REDIS_REC_ADDR=redis:6379 -e PRODUCT_OPS_REDIS_GENERAL_ADDR=redis:6379 \
      -e PRODUCT_OPS_ELASTICSEARCH_ENDPOINT="${PRODUCT_OPS_ELASTICSEARCH_ENDPOINT:-http://elasticsearch:9200}" \
      -e AUTH_JWT_SECRET="${AUTH_JWT_SECRET:?AUTH_JWT_SECRET is required}" \
      -e AUTH_JWT_ISSUER="${AUTH_JWT_ISSUER:?AUTH_JWT_ISSUER is required}" \
      -e AUTH_JWT_AUDIENCE="${AUTH_JWT_AUDIENCE:?AUTH_JWT_AUDIENCE is required}" \
      -e AUTH_JWT_TOKEN_VERSION="${AUTH_JWT_TOKEN_VERSION:?AUTH_JWT_TOKEN_VERSION is required}" \
      -e AUTH_DEVICE_TICKET_SECRET="${AUTH_DEVICE_TICKET_SECRET:?AUTH_DEVICE_TICKET_SECRET is required}" \
      -e AUTH_DEVICE_TICKET_ISSUER="${AUTH_DEVICE_TICKET_ISSUER:?AUTH_DEVICE_TICKET_ISSUER is required}" \
      -e AUTH_DEVICE_TICKET_AUDIENCE="${AUTH_DEVICE_TICKET_AUDIENCE:?AUTH_DEVICE_TICKET_AUDIENCE is required}" \
      -e AUTH_DEVICE_TICKET_TOKEN_VERSION="${AUTH_DEVICE_TICKET_TOKEN_VERSION:?AUTH_DEVICE_TICKET_TOKEN_VERSION is required}" \
      -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
      -p "${LOCAL_GAMMA_PRODUCT_OPS_SERVICE_PORT:-19250}:18086" \
      --healthcheck-command "wget -qO- http://127.0.0.1:18086/healthz >/dev/null 2>&1" \
      --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
      "$LOCAL_GAMMA_PRODUCT_OPS_SERVICE_IMAGE" >/dev/null
    wait_healthy quwoquan_service_product-ops-service_1
  else
    echo "[local-gamma] product telemetry unavailable; skipping product-ops without blocking App startup."
  fi

  podman run --pull=never --name quwoquan_service_platform-ops-service_1 -d \
    --net "$network_name" --network-alias platform-ops-service \
    -e SERVICE_NAME=platform-ops-service -e APP_ENV=gamma-integration \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e PLATFORM_OPS_SERVICE_ADDR=:18088 \
    -e POSTGRES_DSN='postgres://quwoquan:quwoquan@postgres:5432/quwoquan?sslmode=disable' \
    -e AUTH_JWT_SECRET="${AUTH_JWT_SECRET:?AUTH_JWT_SECRET is required}" \
    -e AUTH_JWT_ISSUER="${AUTH_JWT_ISSUER:?AUTH_JWT_ISSUER is required}" \
    -e AUTH_JWT_AUDIENCE="${AUTH_JWT_AUDIENCE:?AUTH_JWT_AUDIENCE is required}" \
    -e AUTH_JWT_TOKEN_VERSION="${AUTH_JWT_TOKEN_VERSION:?AUTH_JWT_TOKEN_VERSION is required}" \
    -e REPO_ROOT=/app \
    -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
    -v "${QWQ_OUTPUT_ROOT}/env/repo/local/control-plane/process/platform-ops-service:/app/.qwq_output/env/repo/local/control-plane/process/platform-ops-service" \
    -p "${LOCAL_GAMMA_PLATFORM_OPS_SERVICE_PORT:-19260}:18088" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18088/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_PLATFORM_OPS_SERVICE_IMAGE" >/dev/null
  wait_healthy quwoquan_service_platform-ops-service_1

  podman run --pull=never --name quwoquan_service_content-service_1 -d \
    --net "$network_name" --network-alias content-service \
    -e SERVICE_NAME=content-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" \
    -e MONGO_URI=mongodb://mongodb:27017 \
    -e REPORT_DATABASE_URL='postgres://quwoquan:quwoquan@postgres:5432/quwoquan?sslmode=disable' \
    -e CONTENT_REDIS_REC_ADDR=redis:6379 -e CONTENT_REDIS_GENERAL_ADDR=redis:6379 -e CONTENT_REDIS_REALTIME_ADDR=redis:6379 \
    -e CONTENT_OSS_ENDPOINT \
    -e CONTENT_OSS_ACCESS_KEY_ID \
    -e CONTENT_OSS_ACCESS_KEY_SECRET \
    -e SEARCH_ES_ENABLED=true -e SEARCH_ES_ENDPOINTS=http://elasticsearch:9200 \
    -e REC_MODEL_SERVICE_ENABLED=true -e REC_MODEL_SERVICE_URL=http://recommendation-service:8000 \
    -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
    -p "${LOCAL_GAMMA_CONTENT_PORT:-19220}:18080" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18080/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_CONTENT_SERVICE_IMAGE" >/dev/null
  wait_healthy quwoquan_service_content-service_1

  podman run --pull=never --name quwoquan_service_chat-service_1 -d \
    --net "$network_name" --network-alias chat-service \
    -e SERVICE_NAME=chat-service -e MODULE_PACKAGE=chat-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e CHAT_SERVICE_ADDR=:18081 \
    -e MONGO_URI=mongodb://mongodb:27017 -e MONGO_DATABASE=quwoquan_chat \
    -e CHAT_REDIS_REALTIME_ADDR=redis:6379 -e CHAT_REDIS_GENERAL_ADDR=redis:6379 \
    -e CHAT_REDIS_RELIABLE_TASK_ADDR=redis:6379 \
    -e RELIABLE_TASK_READY_INDEX_ENABLED=true \
    -e RELIABLE_TASK_READY_INDEX_STREAM="$LOCAL_GAMMA_READY_INDEX_STREAM" \
    -e RELIABLE_TASK_READY_INDEX_GROUP="$LOCAL_GAMMA_READY_INDEX_GROUP" \
    -e RELIABLE_TASK_READY_INDEX_QUEUE="$LOCAL_GAMMA_READY_INDEX_QUEUE" \
    -e CHAT_GROUP_AVATAR_CDN_BASE_URL="$MEDIA_AVATAR_BASE_URL" \
    -e CHAT_GROUP_AVATAR_LOCAL_MEDIA_ROOT=/var/lib/quwoquan/chat-media \
    -e RUNTIME_SYNC_PATCH_TTL_HOURS=720 \
    -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
    -v "${LOCAL_GAMMA_MEDIA_ROOT}:/var/lib/quwoquan/chat-media" \
    -p "${LOCAL_GAMMA_CHAT_PORT:-19200}:18081" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18081/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_CHAT_SERVICE_IMAGE" >/dev/null
  wait_healthy quwoquan_service_chat-service_1

  podman run --pull=never --name quwoquan_service_user-service_1 -d \
    --net "$network_name" --network-alias user-service \
    -e SERVICE_NAME=user-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e USER_SERVICE_ADDR=:18081 \
    -e POSTGRES_DSN='postgres://quwoquan:quwoquan@postgres:5432/quwoquan?sslmode=disable' \
    -e MONGODB_URI=mongodb://mongodb:27017 -e MONGODB_DATABASE=quwoquan_user \
    -e TAG_MONGO_URI=mongodb://mongodb:27017 -e TAG_MONGO_DATABASE=quwoquan_tag \
    -e REDIS_ADDR=redis:6379 \
    -e IDENTITY_ONE_TAP_FIXTURE_ENDPOINT \
    -e IDENTITY_ONE_TAP_FIXTURE_ACCESS_KEY_ID \
    -e IDENTITY_ONE_TAP_FIXTURE_ACCESS_KEY_SECRET \
    -e IDENTITY_SOCIAL_FIXTURE_WECHAT_TOKEN_URL \
    -e IDENTITY_SOCIAL_FIXTURE_WECHAT_USER_INFO_URL \
    -e IDENTITY_SOCIAL_FIXTURE_ALIPAY_TOKEN_URL \
    -e IDENTITY_SOCIAL_FIXTURE_ALIPAY_USER_INFO_URL \
    -e IDENTITY_SOCIAL_FIXTURE_QQ_USER_INFO_URL \
    -e IDENTITY_SOCIAL_FIXTURE_WECHAT_APP_ID \
    -e IDENTITY_SOCIAL_FIXTURE_WECHAT_APP_SECRET \
    -e IDENTITY_SOCIAL_FIXTURE_ALIPAY_APP_ID \
    -e IDENTITY_SOCIAL_FIXTURE_ALIPAY_APP_PRIVATE_KEY_PEM \
    -e IDENTITY_SOCIAL_FIXTURE_ALIPAY_PLATFORM_PUBLIC_KEY_PEM \
    -e IDENTITY_SOCIAL_FIXTURE_ALIPAY_MERCHANT_PID \
    -e IDENTITY_SOCIAL_FIXTURE_QQ_APP_ID \
    -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
    -v "${ROOT}/quwoquan_service/contracts/metadata/user:/contracts/metadata/user:ro" \
    -v "${ROOT}/quwoquan_service/services/user-service/internal/account/user_account/infrastructure/migration:/internal/infrastructure/migration:ro" \
    -p "${LOCAL_GAMMA_USER_PORT:-19210}:18081" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18081/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_USER_SERVICE_IMAGE" >/dev/null
  wait_healthy quwoquan_service_user-service_1

  podman run --pull=never --name quwoquan_service_integration-service_1 -d \
    --net "$network_name" --network-alias integration-service \
    -e SERVICE_NAME=integration-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e INTEGRATION_SERVICE_ADDR=:18086 \
    -e INTEGRATION_MONGO_URI=mongodb://mongodb:27017 -e INTEGRATION_MONGO_DATABASE=quwoquan_integration \
    -e INTEGRATION_PUSH_ENABLED=true \
    -e INTEGRATION_SMS_FIXTURE_ENDPOINT \
    -e INTEGRATION_SMS_FIXTURE_TOKEN \
    -e INTEGRATION_PUSH_FIXTURE_USER_SERVICE_BASE_URL \
    -e INTEGRATION_PUSH_FIXTURE_HMAC_KEY \
    -e INTEGRATION_LOCATION_FIXTURE_BASE_URL \
    -e INTEGRATION_LOCATION_FIXTURE_AK \
    -e AUTH_JWT_SECRET="${AUTH_JWT_SECRET:?AUTH_JWT_SECRET is required}" \
    -e AUTH_JWT_ISSUER="${AUTH_JWT_ISSUER:?AUTH_JWT_ISSUER is required}" \
    -e AUTH_JWT_AUDIENCE="${AUTH_JWT_AUDIENCE:?AUTH_JWT_AUDIENCE is required}" \
    -e AUTH_JWT_TOKEN_VERSION="${AUTH_JWT_TOKEN_VERSION:?AUTH_JWT_TOKEN_VERSION is required}" \
    -e AUTH_DEVICE_TICKET_SECRET="${AUTH_DEVICE_TICKET_SECRET:?AUTH_DEVICE_TICKET_SECRET is required}" \
    -e AUTH_DEVICE_TICKET_ISSUER="${AUTH_DEVICE_TICKET_ISSUER:?AUTH_DEVICE_TICKET_ISSUER is required}" \
    -e AUTH_DEVICE_TICKET_AUDIENCE="${AUTH_DEVICE_TICKET_AUDIENCE:?AUTH_DEVICE_TICKET_AUDIENCE is required}" \
    -e AUTH_DEVICE_TICKET_TOKEN_VERSION="${AUTH_DEVICE_TICKET_TOKEN_VERSION:?AUTH_DEVICE_TICKET_TOKEN_VERSION is required}" \
    -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
    -p "${LOCAL_GAMMA_INTEGRATION_PORT:-19310}:18086" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18086/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_INTEGRATION_SERVICE_IMAGE" >/dev/null
  wait_healthy quwoquan_service_integration-service_1

  podman run --pull=never --name quwoquan_service_notification-service_1 -d \
    --net "$network_name" --network-alias notification-service \
    -e SERVICE_NAME=notification-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e NOTIFICATION_SERVICE_ADDR=:18087 \
    -e 'NOTIFICATION_MONGO_URI=mongodb://mongodb:27017/?replicaSet=rs0' \
    -e NOTIFICATION_MONGO_DATABASE=quwoquan_notification \
    -e NOTIFICATION_INTEGRATION_BASE_URL=http://integration-service:18086 \
    -e NOTIFICATION_INTEGRATION_TIMEOUT_MS=1500 \
    -e NOTIFICATION_USER_BASE_URL=http://user-service:18081 \
    -e NOTIFICATION_REALTIME_BASE_URL=http://realtime-gateway:18090 \
    -e NOTIFICATION_CLAIM_PER_SECOND=100 -e NOTIFICATION_DISPATCH_PER_SECOND=100 -e NOTIFICATION_RETRY_PER_SECOND=20 \
    -e AUTH_JWT_SECRET="${AUTH_JWT_SECRET:?AUTH_JWT_SECRET is required}" \
    -e AUTH_JWT_ISSUER="${AUTH_JWT_ISSUER:?AUTH_JWT_ISSUER is required}" \
    -e AUTH_JWT_AUDIENCE="${AUTH_JWT_AUDIENCE:?AUTH_JWT_AUDIENCE is required}" \
    -e AUTH_JWT_TOKEN_VERSION="${AUTH_JWT_TOKEN_VERSION:?AUTH_JWT_TOKEN_VERSION is required}" \
    -e AUTH_DEVICE_TICKET_SECRET="${AUTH_DEVICE_TICKET_SECRET:?AUTH_DEVICE_TICKET_SECRET is required}" \
    -e AUTH_DEVICE_TICKET_ISSUER="${AUTH_DEVICE_TICKET_ISSUER:?AUTH_DEVICE_TICKET_ISSUER is required}" \
    -e AUTH_DEVICE_TICKET_AUDIENCE="${AUTH_DEVICE_TICKET_AUDIENCE:?AUTH_DEVICE_TICKET_AUDIENCE is required}" \
    -e AUTH_DEVICE_TICKET_TOKEN_VERSION="${AUTH_DEVICE_TICKET_TOKEN_VERSION:?AUTH_DEVICE_TICKET_TOKEN_VERSION is required}" \
    -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
    -p "${LOCAL_GAMMA_NOTIFICATION_PORT:-19320}:18087" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18087/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_NOTIFICATION_SERVICE_IMAGE" >/dev/null
  wait_healthy quwoquan_service_notification-service_1

  if [[ "$WORKLOAD" == "full" ]]; then
    podman run --pull=never --name quwoquan_service_assistant-service_1 -d \
      --net "$network_name" --network-alias assistant-service \
      -e SERVICE_NAME=assistant-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
      -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
      -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e ASSISTANT_SERVICE_ADDR=:18087 \
      -e MONGODB_URI=mongodb://mongodb:27017 -e MONGODB_DATABASE=quwoquan_assistant \
      -e REDIS_GENERAL_ADDR=redis:6379 -e REDIS_REC_ADDR=redis:6379 \
      -e ASSISTANT_MODEL_FIXTURE_ENDPOINT \
      -e ASSISTANT_MODEL_API_KEY \
      -e ASSISTANT_PUBLIC_SEARCH_FIXTURE_URL \
      -e ASSISTANT_WEATHER_FIXTURE_GEOCODING_URL \
      -e ASSISTANT_WEATHER_FIXTURE_FORECAST_URL \
      -e ASSISTANT_FINANCE_FIXTURE_CHART_URL \
      -e ASSISTANT_SCENARIO_SEED_REFS="${ASSISTANT_SCENARIO_SEED_REFS:-}" \
      -e ASSISTANT_NOTIFICATION_BASE_URL=http://notification-service:18087 \
      -e AUTH_JWT_SECRET="${AUTH_JWT_SECRET:?AUTH_JWT_SECRET is required}" \
      -e AUTH_JWT_ISSUER="${AUTH_JWT_ISSUER:?AUTH_JWT_ISSUER is required}" \
      -e AUTH_JWT_AUDIENCE="${AUTH_JWT_AUDIENCE:?AUTH_JWT_AUDIENCE is required}" \
      -e AUTH_JWT_TOKEN_VERSION="${AUTH_JWT_TOKEN_VERSION:?AUTH_JWT_TOKEN_VERSION is required}" \
      -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
      -p "${LOCAL_GAMMA_ASSISTANT_PORT:-19230}:18087" \
      --healthcheck-command "wget -qO- http://127.0.0.1:18087/healthz >/dev/null 2>&1" \
      --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
      "$LOCAL_GAMMA_ASSISTANT_SERVICE_IMAGE" >/dev/null
    wait_healthy quwoquan_service_assistant-service_1
  fi

  podman run --pull=never --name quwoquan_service_tag-service_1 -d \
    --net "$network_name" --network-alias tag-service \
    -e SERVICE_NAME=tag-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e TAG_SERVICE_ADDR=:18092 \
    -e TAG_MONGO_URI=mongodb://mongodb:27017 -e TAG_MONGO_DATABASE=quwoquan_tag \
    -e TAG_REDIS_GENERAL_ADDR=redis:6379 \
    -e AUTH_JWT_SECRET="${AUTH_JWT_SECRET:?AUTH_JWT_SECRET is required}" \
    -e AUTH_JWT_ISSUER="${AUTH_JWT_ISSUER:?AUTH_JWT_ISSUER is required}" \
    -e AUTH_JWT_AUDIENCE="${AUTH_JWT_AUDIENCE:?AUTH_JWT_AUDIENCE is required}" \
    -e AUTH_JWT_TOKEN_VERSION="${AUTH_JWT_TOKEN_VERSION:?AUTH_JWT_TOKEN_VERSION is required}" \
    -e AUTH_DEVICE_TICKET_SECRET="${AUTH_DEVICE_TICKET_SECRET:?AUTH_DEVICE_TICKET_SECRET is required}" \
    -e AUTH_DEVICE_TICKET_ISSUER="${AUTH_DEVICE_TICKET_ISSUER:?AUTH_DEVICE_TICKET_ISSUER is required}" \
    -e AUTH_DEVICE_TICKET_AUDIENCE="${AUTH_DEVICE_TICKET_AUDIENCE:?AUTH_DEVICE_TICKET_AUDIENCE is required}" \
    -e AUTH_DEVICE_TICKET_TOKEN_VERSION="${AUTH_DEVICE_TICKET_TOKEN_VERSION:?AUTH_DEVICE_TICKET_TOKEN_VERSION is required}" \
    -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
    -p "${LOCAL_GAMMA_TAG_PORT:-19270}:18092" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18092/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_TAG_SERVICE_IMAGE" >/dev/null
  wait_healthy quwoquan_service_tag-service_1

  podman run --pull=never --name quwoquan_service_search-service_1 -d \
    --net "$network_name" --network-alias search-service \
    -e SERVICE_NAME=search-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" \
    -e SEARCH_ES_ENABLED=true -e SEARCH_ES_ENDPOINTS=http://elasticsearch:9200 \
    -e SEARCH_MONGO_URI=mongodb://mongodb:27017 -e SEARCH_MONGO_DATABASE=quwoquan_search \
    -e SEARCH_REDIS_GENERAL_MODE=standalone -e SEARCH_REDIS_GENERAL_ADDR=redis:6379 \
    -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
    -p "${LOCAL_GAMMA_SEARCH_PORT:-19280}:18095" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18095/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_SEARCH_SERVICE_IMAGE" >/dev/null
  wait_healthy quwoquan_service_search-service_1

  podman run --pull=never --name quwoquan_service_entity-service_1 -d \
    --net "$network_name" --network-alias entity-service \
    -e SERVICE_NAME=entity-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" \
    -e ENTITY_MONGO_URI=mongodb://mongodb:27017 -e ENTITY_MONGO_DATABASE=quwoquan_entity \
    -e ENTITY_REDIS_ADDR=redis:6379 \
    -e AUTH_JWT_SECRET="${AUTH_JWT_SECRET:?AUTH_JWT_SECRET is required}" \
    -e AUTH_JWT_ISSUER="${AUTH_JWT_ISSUER:?AUTH_JWT_ISSUER is required}" \
    -e AUTH_JWT_AUDIENCE="${AUTH_JWT_AUDIENCE:?AUTH_JWT_AUDIENCE is required}" \
    -e AUTH_JWT_TOKEN_VERSION="${AUTH_JWT_TOKEN_VERSION:?AUTH_JWT_TOKEN_VERSION is required}" \
    -e SEARCH_ES_ENABLED=true -e SEARCH_ES_ENDPOINTS=http://elasticsearch:9200 \
    -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
    -p "${LOCAL_GAMMA_ENTITY_PORT:-19290}:18084" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18084/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_ENTITY_SERVICE_IMAGE" >/dev/null
  wait_healthy quwoquan_service_entity-service_1

  podman run --pull=never --name quwoquan_service_circle-service_1 -d \
    --net "$network_name" --network-alias circle-service \
    -e SERVICE_NAME=circle-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e CIRCLE_SERVICE_ADDR=:18082 \
    -e CIRCLE_MONGO_URI=mongodb://mongodb:27017 -e CIRCLE_MONGO_DATABASE=quwoquan_circle \
    -e CIRCLE_REDIS_ADDR=redis:6379 \
    -e SEARCH_ES_ENABLED=true -e SEARCH_ES_ENDPOINTS=http://elasticsearch:9200 \
    -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
    -p "${LOCAL_GAMMA_CIRCLE_PORT:-19300}:18082" \
    --healthcheck-command "wget -qO- http://127.0.0.1:18082/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 10s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_CIRCLE_SERVICE_IMAGE" >/dev/null
  wait_healthy quwoquan_service_circle-service_1

  podman run --pull=never --name quwoquan_service_gamma-proxy_1 -d \
    --net "$network_name" --network-alias gamma-proxy \
    -e QWQ_PUBLIC_TLS_CERT_FILE=/etc/caddy/tls/fullchain.pem \
    -e QWQ_PUBLIC_TLS_KEY_FILE=/etc/caddy/tls/privkey.pem \
    -e QWQ_PUBLIC_API_HOST="$QWQ_PUBLIC_API_HOST" \
    -e QWQ_PUBLIC_WEB_HOST="$QWQ_PUBLIC_WEB_HOST" \
    -e QWQ_PUBLIC_RTC_HOST="$QWQ_PUBLIC_RTC_HOST" \
    -e QWQ_PUBLIC_OPS_HOST="$QWQ_PUBLIC_OPS_HOST" \
    -e QWQ_PUBLIC_CDN_HOST="$QWQ_PUBLIC_CDN_HOST" \
    -v "${LOCAL_GAMMA_CADDYFILE}:/etc/caddy/Caddyfile:ro" \
    -v "${QWQ_PUBLIC_TLS_CERT_FILE}:/etc/caddy/tls/fullchain.pem:ro" \
    -v "${QWQ_PUBLIC_TLS_KEY_FILE}:/etc/caddy/tls/privkey.pem:ro" \
    -v "${LOCAL_GAMMA_MEDIA_ROOT}:/srv/media:ro" \
    -v "${LOCAL_GAMMA_LEGAL_STATIC_ROOT}:/srv/legal:ro" \
    -v "${LOCAL_GAMMA_CADDY_DATA_VOLUME}:/data" \
    -v "${LOCAL_GAMMA_CADDY_CONFIG_VOLUME}:/config" \
    -p "${LOCAL_GAMMA_HTTP_PORT:-19000}:${LOCAL_GAMMA_HTTP_PORT:-19000}" \
    -p "${LOCAL_GAMMA_PRODUCT_OPS_PORT:-19010}:${LOCAL_GAMMA_PRODUCT_OPS_PORT:-19010}" \
    -p "${LOCAL_GAMMA_MEDIA_EDGE_PORT:-19100}:${LOCAL_GAMMA_MEDIA_EDGE_PORT:-19100}" \
    -p "${LOCAL_GAMMA_ADMIN_PORT:-2019}:2019" \
    --healthcheck-command "wget -qO- https://${QWQ_PUBLIC_API_HOST}:${LOCAL_GAMMA_HTTP_PORT:-19000}/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 5s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_CADDY_IMAGE" >/dev/null
  wait_healthy quwoquan_service_gamma-proxy_1
else
  echo "[local-gamma] startup mode: compose-up"
  # Recreate the local mirror on every gate run so changed host port envs take effect.
  "${compose_cmd[@]}" down --remove-orphans >/dev/null 2>&1 || true
  cleanup_stale_named_gamma_containers
  # 本地进程中断时 Caddy 可能留下半写入的证书锁。此处代理已停止，
  # 可安全清理过期签发锁，同时保留本地 CA 与已签发证书。
  if docker volume inspect quwoquan_service_local-gamma-caddy-data >/dev/null 2>&1; then
    docker run --rm \
      -v quwoquan_service_local-gamma-caddy-data:/data \
      --entrypoint sh \
      "$LOCAL_GAMMA_CADDY_IMAGE" \
      -c 'rm -f /data/caddy/locks/*.lock' >/dev/null
  fi
  if [[ "$PRESERVE_POSTGRES_VOLUME" != "1" ]]; then
    docker volume rm -f quwoquan_service_local-gamma-postgres >/dev/null 2>&1 || true
  fi
  ensure_docker_gamma_proxy_started() {
    local name="quwoquan_service-gamma-proxy-1"
    local status=""
    local health=""
    local deadline=$((SECONDS + 15))
    while (( SECONDS < deadline )); do
      status="$(docker inspect --format '{{.State.Status}}' "$name" 2>/dev/null || true)"
      if [[ -n "$status" ]]; then
        break
      fi
      sleep 1
    done
    if [[ -z "$status" ]]; then
      echo "[local-gamma] WARN: gamma-proxy container missing after compose up" >&2
      return 1
    fi
    health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$name" 2>/dev/null || true)"
    if [[ "$status" == "running" ]]; then
      if [[ "$health" == "healthy" || "$health" == "running" || "$health" == "starting" ]]; then
        return 0
      fi
      echo "[local-gamma] WARN: gamma-proxy running but unhealthy (health=$health)" >&2
      return 1
    fi
    gamma_proxy_ensure_attempts=$((gamma_proxy_ensure_attempts + 1))
    echo "[local-gamma] gamma-proxy status=$status health=${health:-unknown}; starting explicitly (attempt ${gamma_proxy_ensure_attempts})" >&2
    if ! docker start "$name" >/dev/null 2>&1; then
      echo "[local-gamma] WARN: failed to start gamma-proxy explicitly" >&2
      docker ps -a --filter "name=$name" >&2 || true
      docker logs --tail 80 "$name" >&2 || true
      return 1
    fi
    for _ in $(seq 1 30); do
      status="$(docker inspect --format '{{.State.Status}}' "$name" 2>/dev/null || true)"
      health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$name" 2>/dev/null || true)"
      if [[ "$status" == "running" && ( "$health" == "healthy" || "$health" == "running" || "$health" == "starting" ) ]]; then
        return 0
      fi
      sleep 1
    done
    echo "[local-gamma] WARN: gamma-proxy explicit start did not report ready state (status=$status health=$health)" >&2
    docker logs --tail 80 "$name" >&2 || true
    return 1
  }
  retry_compose_up_after_created_only_failure() {
    local created_count=""
    local running_count=""
    local arg=""
    local has_no_build=0
    local -a retry_args=("${compose_up_args[@]}")
    created_count="$(docker ps -aq \
      --filter "label=com.docker.compose.project=${LOCAL_GAMMA_COMPOSE_PROJECT_NAME}" \
      --filter status=created | wc -l | tr -d '[:space:]')"
    running_count="$(docker ps -q \
      --filter "label=com.docker.compose.project=${LOCAL_GAMMA_COMPOSE_PROJECT_NAME}" \
      --filter status=running | wc -l | tr -d '[:space:]')"
    if [[ "${created_count:-0}" == "0" ]]; then
      return 1
    fi
    if [[ "$compose_up_timed_out" != "1" && "${running_count:-0}" != "0" ]]; then
      return 1
    fi
    echo "[local-gamma] compose left ${created_count} created containers; retrying once from the already-built images" >&2
    if ! "${compose_cmd[@]}" down --remove-orphans; then
      echo "[local-gamma] FAIL: failed to remove created-only compose runtime before retry" >&2
      return 1
    fi
    cleanup_stale_named_gamma_containers
    for arg in "${retry_args[@]}"; do
      if [[ "$arg" == "--no-build" ]]; then
        has_no_build=1
        break
      fi
    done
    if [[ "$has_no_build" != "1" ]]; then
      retry_args+=(--no-build)
    fi
    run_compose_up_with_timeout "${retry_args[@]}"
  }
  run_compose_up_with_timeout() {
    local compose_pid=""
    local deadline=""
    # ElasticSearch cold boots on the constrained local Gamma VM can exceed
    # eight minutes while rebuilding Painless lookup data.  The previous
    # timeout tore down a healthy-in-progress stack and retried with images
    # that may not exist locally, so no service ever reached its seed phase.
    local timeout_seconds="${LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS:?LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS is required}"
    if ! [[ "$timeout_seconds" =~ ^[1-9][0-9]*$ ]]; then
      echo "[local-gamma] FAIL: LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS must be a positive integer" >&2
      return 2
    fi

    compose_up_timed_out=0
    "${compose_cmd[@]}" "$@" &
    compose_pid="$!"
    LOCAL_GAMMA_ACTIVE_CHILD_PID="$compose_pid"
    deadline=$((SECONDS + timeout_seconds))
    while kill -0 "$compose_pid" >/dev/null 2>&1; do
      if (( SECONDS >= deadline )); then
        compose_up_timed_out=1
        echo "[local-gamma] FAIL: compose up exceeded ${timeout_seconds}s; preserving the partial runtime for inspection" >&2
        kill "$compose_pid" >/dev/null 2>&1 || true
        wait "$compose_pid" >/dev/null 2>&1 || true
        LOCAL_GAMMA_ACTIVE_CHILD_PID=""
        return 124
      fi
      sleep 1
    done
    if wait "$compose_pid"; then
      LOCAL_GAMMA_ACTIVE_CHILD_PID=""
      return 0
    else
      local compose_status=$?
      LOCAL_GAMMA_ACTIVE_CHILD_PID=""
      return "$compose_status"
    fi
  }
  if ! run_compose_up_with_timeout "${compose_up_args[@]}"; then
    if [[ "$compose_up_timed_out" == "1" ]]; then
      echo "[local-gamma] FAIL: compose start exceeded its bounded timeout; run stackctl inspect before an explicit restart" >&2
      exit 1
    elif retry_compose_up_after_created_only_failure; then
      echo "[local-gamma] compose created-only retry recovered startup"
    else
      echo "[local-gamma] FAIL: compose up failed; runtime readiness cannot be inferred from partial containers" >&2
      exit 1
    fi
  fi
  ensure_docker_gamma_proxy_started
fi
start_colima_tunnels_if_needed
verify_public_dns

# docker compose 分支不会逐项 wait_healthy；在宣告就绪前用主机侧探测避免 T3/T4 撞到端口未监听。
gamma_canonical_video_range_mime_ready() {
  local host="$1"
  local port="$2"
  local probe=""
  local status=""
  local content_type=""
  probe="$(
    curl -fsS \
      -H "Range: bytes=0-1" \
      -o /dev/null \
      -w '%{http_code}|%{content_type}' \
      "https://${host}:${port}/media/video/s/video-primary-0001/post/video-content-0001/source.mp4"
  )" || return 1
  status="${probe%%|*}"
  content_type="${probe#*|}"
  [[ "$status" == "206" && "$content_type" == video/* ]]
}

gamma_product_ops_ready() {
  if [[ "$PRODUCT_TELEMETRY_AVAILABLE" != "1" ]]; then
    return 0
  fi
  curl -fsS "${PRODUCT_OPS_BASE_URL%/}/healthz" >/dev/null 2>&1
}

gamma_platform_ops_ready() {
  # platform-ops belongs to the full operational control-plane. The
  # content-release slice deliberately has no operator OIDC material and its
  # acceptance scope does not include that service.
  if [[ "$WORKLOAD" == "content-release" ]]; then
    return 0
  fi
  curl -fsS "http://127.0.0.1:${LOCAL_GAMMA_PLATFORM_OPS_SERVICE_PORT:-19260}/healthz" >/dev/null 2>&1
}

wait_local_gamma_host_ready() {
  local gw="${GATEWAY_BASE_URL%/}"
  local gw_host="$QWQ_PUBLIC_API_HOST"
  local gw_port="${LOCAL_GAMMA_HTTP_PORT:-19000}"
  local product_ops_host="$QWQ_PUBLIC_OPS_HOST"
  local product_ops_public_port="${LOCAL_GAMMA_PRODUCT_OPS_PORT:-19010}"
  local media_host="$QWQ_PUBLIC_CDN_HOST"
  local video_host="$QWQ_PUBLIC_CDN_HOST"
  local media_edge_port="${LOCAL_GAMMA_MEDIA_EDGE_PORT:-19100}"
  local po_port="${LOCAL_GAMMA_PRODUCT_OPS_SERVICE_PORT:-19250}"
  local user_port="${LOCAL_GAMMA_USER_PORT:-19210}"
  local integration_port="${LOCAL_GAMMA_INTEGRATION_PORT:-19310}"
  local notification_port="${LOCAL_GAMMA_NOTIFICATION_PORT:-19320}"
  local tag_port="${LOCAL_GAMMA_TAG_PORT:-19270}"
  local deadline=$(( $(date +%s) + HOST_READY_TIMEOUT_SECONDS ))
  local last_gamma_proxy_retry=0
  echo "[local-gamma] waiting for host probes (${HOST_READY_TIMEOUT_SECONDS}s): ${gw}/healthz + ${PRODUCT_OPS_BASE_URL%/}/healthz + media health + internal health"
  while (( $(date +%s) < deadline )); do
    if (( $(date +%s) - last_gamma_proxy_retry >= 15 )); then
      ensure_docker_gamma_proxy_started || true
      last_gamma_proxy_retry=$(date +%s)
    fi
    if curl -fsS "https://${gw_host}:${gw_port}/healthz" >/dev/null 2>&1 \
      && gamma_product_ops_ready \
      && curl -fsS "https://${media_host}:${media_edge_port}/healthz" >/dev/null 2>&1 \
      && curl -fsS "https://${video_host}:${media_edge_port}/healthz" >/dev/null 2>&1 \
      && { [[ "$PRODUCT_TELEMETRY_AVAILABLE" != "1" ]] || curl -fsS "http://127.0.0.1:${po_port}/healthz" >/dev/null 2>&1; } \
      && gamma_platform_ops_ready \
      && curl -fsS "http://127.0.0.1:${user_port}/healthz" >/dev/null 2>&1 \
      && curl -fsS "http://127.0.0.1:${integration_port}/healthz" >/dev/null 2>&1 \
      && curl -fsS "http://127.0.0.1:${notification_port}/healthz" >/dev/null 2>&1 \
      && { [[ "$ENABLE_FIXTURE_SEEDS" == "1" ]] || curl -fsS "http://127.0.0.1:${tag_port}/healthz" >/dev/null 2>&1; }
    then
      return 0
    fi
    sleep 2
  done
  echo "[local-gamma] FAIL: host cannot reach required Remote service health probes within ${HOST_READY_TIMEOUT_SECONDS}s" >&2
  curl -fsS "https://${gw_host}:${gw_port}/healthz" >&2 || true
  gamma_product_ops_ready >&2 || true
  curl -fsS "https://${media_host}:${media_edge_port}/healthz" >&2 || true
  curl -fsS "https://${video_host}:${media_edge_port}/healthz" >&2 || true
  docker compose -p "$LOCAL_GAMMA_COMPOSE_PROJECT_NAME" "${COMPOSE_FILE_ARGS[@]}" ps >&2 || true
  curl -fsS "http://127.0.0.1:${integration_port}/healthz" >&2 || true
  curl -fsS "http://127.0.0.1:${notification_port}/healthz" >&2 || true
  docker compose -p "$LOCAL_GAMMA_COMPOSE_PROJECT_NAME" "${COMPOSE_FILE_ARGS[@]}" logs --tail 80 gamma-proxy product-ops-service platform-ops-service user-service integration-service notification-service >&2 || true
  return 1
}
ensure_gamma_filter_catalog_release() {
  echo "[local-gamma] activating canonical FilterCatalogRelease"
  PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/quwoquan_ops/cli/stackctl.py" \
    --output-format json \
    filter-catalog --target gamma-local --action stage-and-activate
}
wait_local_gamma_host_ready
ensure_gamma_filter_catalog_release

seed_integration_location_data() {
  local mongo_port="${LOCAL_GAMMA_MONGO_PORT:-}"
  local fixture="$ROOT/quwoquan_service/services/integration-service/tests/support/contract_fixtures/scenarios/integration_scenarios.json"
  if [[ -z "$mongo_port" || ! -f "$fixture" ]]; then
    echo "[local-gamma] FAIL: Integration Location seed input is unavailable" >&2
    return 1
  fi
  python3 - "$fixture" "$mongo_port" <<'PY'
import json
import os
import subprocess
import sys
from pathlib import Path

fixture_path, mongo_port = sys.argv[1:3]
payload = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
raw_items = payload.get("seedSets", {}).get("location_poi_core", {}).get("pois", [])
documents = []
for raw in raw_items:
    poi_id = str(raw.get("poiId", "")).strip()
    name = str(raw.get("name", "")).strip()
    latitude = raw.get("lat")
    longitude = raw.get("lng")
    if not poi_id or not name or not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        raise SystemExit("Integration Location fixture contains an incomplete POI")
    documents.append(
        {
            "poiId": poi_id,
            "name": name,
            "address": str(raw.get("address", "")),
            "cityCode": str(raw.get("cityCode", "")),
            "adCode": str(raw.get("adCode", "")),
            "distanceMeters": int(raw.get("distanceMeters", 0) or 0),
            "location": {
                "type": "Point",
                "coordinates": [float(longitude), float(latitude)],
            },
        }
    )
if not documents:
    raise SystemExit("Integration Location fixture is empty")
encoded = json.dumps(documents, ensure_ascii=False)
script = f"""
const collection = db.getSiblingDB('quwoquan_integration').location_pois;
collection.deleteMany({{}});
collection.insertMany({encoded});
printjson({{inserted: collection.countDocuments({{}})}});
"""
result = subprocess.run(
    [
        "mongosh",
        f"mongodb://127.0.0.1:{mongo_port}/?directConnection=true",
        "--quiet",
    ],
    input=script,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    check=False,
)
if result.returncode != 0:
    print(result.stdout)
    print(result.stderr, file=sys.stderr)
    raise SystemExit(result.returncode)
print(result.stdout.strip())
PY
}
if [[ "$ENABLE_FIXTURE_SEEDS" == "1" ]]; then
  seed_integration_location_data
else
  echo "[local-gamma] skip Integration Location seed because STAGE=${STAGE} uses persisted/host data"
fi

# tag-service 数据在 local-gamma 启动时按当前真相源重建：
#  - tag_nodes ← control_plane/governance/taxonomy（路径制 taxonomy 唯一真相源）
#  - object_tag_index ← app_gamma_seed_manifest 声明的 ref 子集
# local-gamma 尚未上线；这里直接清库重建，拒绝保留任何旧索引名、旧数据或兼容路径。
seed_tag_service_data() {
  local mongo_port="${LOCAL_GAMMA_MONGO_PORT:-}"
  if [[ -z "$mongo_port" ]]; then
    echo "[local-gamma] FAIL: LOCAL_GAMMA_MONGO_PORT is required for tag data seed" >&2
    return 1
  fi
  local mongo_uri="mongodb://127.0.0.1:${mongo_port}/?directConnection=true"
  local data_release_id="${LOCAL_GAMMA_DATA_RELEASE_ID:-tag-taxonomy-20260723-001}"
  echo "[local-gamma] rebuilding ${LOCAL_GAMMA_TAG_DB} from current tag sources ..."
  mongosh "$mongo_uri" --quiet --eval "db.getSiblingDB(\"${LOCAL_GAMMA_TAG_DB}\").dropDatabase()"
  echo "[local-gamma] seeding tag_nodes (${LOCAL_GAMMA_TAGS_DIR} -> ${LOCAL_GAMMA_TAG_DB}.tag_nodes) ..."
  ( cd "$ROOT/quwoquan_service" && go run ./services/tag-service/cmd/import \
      --tags-dir "$LOCAL_GAMMA_TAGS_DIR" \
      --mongo-uri "$mongo_uri" --db "$LOCAL_GAMMA_TAG_DB" \
      --release-id "$data_release_id" --source-owner qwq_data )
  echo "[local-gamma] seeding object_tag_index (${LOCAL_GAMMA_TAG_OBJECTS_FILE} -> ${LOCAL_GAMMA_TAG_DB}.object_tag_index) ..."
  ( cd "$ROOT/quwoquan_service" && go run ./services/tag-service/cmd/import-objects \
      --objects-file "$LOCAL_GAMMA_TAG_OBJECTS_FILE" \
      --seed-refs "$LOCAL_GAMMA_TAG_SEED_REFS" \
      --mongo-uri "$mongo_uri" --db "$LOCAL_GAMMA_TAG_DB" \
      --release-id "$data_release_id" --source-owner gamma_seed_manifest )
}

wait_tag_service_taxonomy_ready() {
  local tag_port="${LOCAL_GAMMA_TAG_PORT:-19270}"
  local deadline=$(( $(date +%s) + HOST_READY_TIMEOUT_SECONDS ))
  while (( $(date +%s) < deadline )); do
    if curl -fsS "http://127.0.0.1:${tag_port}/healthz" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "[local-gamma] FAIL: tag-service taxonomy projection did not become healthy after canonical import" >&2
  curl -fsS "http://127.0.0.1:${tag_port}/healthz" >&2 || true
  return 1
}

if [[ "$ENABLE_FIXTURE_SEEDS" == "1" ]]; then
  seed_tag_service_data
  wait_tag_service_taxonomy_ready
else
  echo "[local-gamma] skip tag seed because STAGE=${STAGE} uses persisted/host data"
fi

seed_gamma_intersection_data() {
  local mongo_port="${LOCAL_GAMMA_MONGO_PORT:-}"
  local gateway="${GATEWAY_BASE_URL%/}"
  local report="${GAMMA_RUN_ROOT}/intersection-seed-report.json"
  if [[ -z "$mongo_port" ]]; then
    echo "[local-gamma] GATE_BLOCK: intersection seed requires LOCAL_GAMMA_MONGO_PORT" >&2
    return 1
  fi
  echo "[local-gamma] seeding intersection viewer relationships and read model ..."
  if ! python3 - "$ROOT" "$mongo_port" "$gateway" "$report" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

root, mongo_port, gateway, report_path = sys.argv[1:5]
sys.path.insert(0, root)

from quwoquan_ops.cli.lib.local_environment_auth import (
    open_local_acceptance_session,
    request_local_environment_json,
)

session = open_local_acceptance_session(
    gateway,
    environment="gamma",
    target_name="gamma-local",
)
viewer = session.persona_id
person = "sys_travel_9003_sub_01"
third_a = "sys_travel_9004_sub_01"
third_b = "sys_travel_9005_sub_01"
circle = "fixture_circle_photo"
entity = "fixture_homepage_travel_photo_west_lake"
shared_post = "gamma_intersection_shared_post"
profile_post = "gamma_intersection_profile_post"
avatar = (
    os.environ["MEDIA_AVATAR_BASE_URL"] + "/s/"
    "archived-avatar/user/fixture_user_photo/v1/avatar.png"
)

seed_js = f"""
const db = db.getSiblingDB('quwoquan_content');
const viewer = '{viewer}';
const person = '{person}';
const thirdA = '{third_a}';
const thirdB = '{third_b}';
const circle = '{circle}';
const entity = '{entity}';
const sharedPost = '{shared_post}';
const profilePost = '{profile_post}';
const avatar = '{avatar}';
const now = new Date();
db.follow_edges.deleteMany({{$or:[{{followerId: {{$in:[viewer, person]}}}}, {{followeeId: {{$in:[viewer, person]}}}}]}});
db.circle_members.deleteMany({{userId: {{$in:[viewer, person]}}}});
db.rm_behavior_events.deleteMany({{userId: {{$in:[viewer, person, thirdA]}}}});
db.entity_wishlist_events.deleteMany({{userId: {{$in:[viewer, person]}}}});
db.rec_learning_events.deleteMany({{userId: {{$in:[thirdA, thirdB]}}, contentId: sharedPost}});
db.rm_recommend_feature.deleteMany({{userId: {{$in:[thirdA, thirdB]}}}});
db.circle_tag_aggregates.deleteMany({{circleId: circle}});
db.posts.deleteMany({{postId: {{$in:[sharedPost, profilePost]}}}});
db.rm_viewer_object_intersection.deleteMany({{_id: viewer}});
db.follow_edges.insertMany([
  {{followerId: viewer, followeeId: thirdA, createdAt: now}},
  {{followerId: viewer, followeeId: thirdB, createdAt: now}},
  {{followerId: viewer, followeeId: person, createdAt: now}},
  {{followerId: person, followeeId: thirdA, createdAt: now}},
  {{followerId: person, followeeId: thirdB, createdAt: now}},
  {{followerId: thirdA, followeeId: person, createdAt: now}}
]);
db.circle_members.insertMany([
  {{circleId: circle, userId: viewer, role: 'member', joinedAt: now, lastActiveAt: now}},
  {{circleId: circle, userId: person, role: 'member', joinedAt: now, lastActiveAt: now}}
]);
db.rm_behavior_events.insertMany([
  {{userId: viewer, action: 'comment', contentId: sharedPost, entityRefs: [], createdAt: now}},
  {{userId: person, action: 'comment', contentId: sharedPost, entityRefs: [], createdAt: now}},
  {{userId: viewer, action: 'entity_page_view', contentId: '', entityRefs: [entity], createdAt: now}},
  {{userId: person, action: 'entity_page_view', contentId: '', entityRefs: [entity], createdAt: now}},
  {{userId: thirdA, action: 'entity_page_view', contentId: '', entityRefs: [entity], createdAt: now}}
]);
db.entity_wishlist_events.insertMany([
  {{userId: viewer, entityId: entity, objectType: 'sight', displayName: '西湖旅行摄影线', status: 'active', createdAt: now}},
  {{userId: person, entityId: entity, objectType: 'sight', displayName: '西湖旅行摄影线', status: 'active', createdAt: now}}
]);
db.rec_learning_events.insertMany([
  {{userId: thirdA, eventType: 'rec_engagement', contentId: sharedPost, labels: {{action: 'like'}}, createdAt: now}},
  {{userId: thirdB, eventType: 'rec_engagement', contentId: sharedPost, labels: {{action: 'share'}}, createdAt: now}}
]);
db.rm_recommend_feature.insertMany([
  {{userId: thirdA, userFeatures: {{tagInteraction: {{'Topic/摄影': 2, 'Topic/旅行/玩法/摄影旅拍': 1}}}}, updatedAt: now}},
  {{userId: thirdB, userFeatures: {{tagInteraction: {{'Topic/摄影': 3, 'Topic/旅行/玩法/摄影旅拍': 1}}}}, updatedAt: now}}
]);
db.circle_tag_aggregates.insertOne({{
  circleId: circle,
  tags: {{'Topic/摄影': 4.5, 'Topic/旅行/玩法/摄影旅拍': 3.5, 'Topic/城市漫步': 2.5}},
  updatedAt: now
}});
db.posts.insertMany([
  {{_id: profilePost, postId: profilePost, id: profilePost, authorId: person, status: 'published', authorDisplayNameSnapshot: '交集约伴体验号', authorAvatarUrlSnapshot: avatar, updatedAt: now, publishedAt: now}},
  {{_id: sharedPost, postId: sharedPost, id: sharedPost, authorId: person, status: 'published', title: '交集真实证据共享内容', contentType: 'article', authorDisplayNameSnapshot: '交集约伴体验号', authorAvatarUrlSnapshot: avatar, updatedAt: now, publishedAt: now}}
]);
printjson({{viewer, person, circle, entity}});
"""
seed = subprocess.run(
    [
        "mongosh",
        f"mongodb://127.0.0.1:{mongo_port}/?directConnection=true",
        "--quiet",
    ],
    input=seed_js,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    check=False,
)
if seed.returncode != 0:
    print(seed.stdout)
    print(seed.stderr, file=sys.stderr)
    raise SystemExit(seed.returncode)

def request_json(path: str) -> dict:
    return request_local_environment_json(
        gateway,
        path=path,
        session=session,
    )

object_body = request_json(
    f"/content/intersections/object?objectId={person}&objectType=user&limit=8"
)
reasons = object_body.get("items") or []
if not reasons:
    raise SystemExit("object intersection seed probe returned no items")

# SVO displayBinding 适配：对象页响应是 host_plain 投影（宿主 span 已去链接），
# 直接塞进收件箱快照会被 explicit_link 严格校验淘汰（summary/list 恒空）。
# 物化前重置为 canonical explicit 形态，由服务端 hydrate 按收件箱语境重建 spans。
for reason in reasons:
    reason.pop("displayBinding", None)
    reason.pop("primarySpans", None)

materialize_js = f"""
const viewer = '{viewer}';
const reasons = {json.dumps(reasons, ensure_ascii=False)};
db.getSiblingDB('quwoquan_content').rm_viewer_object_intersection.updateOne(
  {{_id: viewer}},
  {{$set: {{computedAt: new Date(), reasonsJson: JSON.stringify(reasons)}}}},
  {{upsert: true}}
);
printjson({{viewer, reasonCount: reasons.length}});
"""
materialize = subprocess.run(
    [
        "mongosh",
        f"mongodb://127.0.0.1:{mongo_port}/?directConnection=true",
        "--quiet",
    ],
    input=materialize_js,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    check=False,
)
if materialize.returncode != 0:
    print(materialize.stdout)
    print(materialize.stderr, file=sys.stderr)
    raise SystemExit(materialize.returncode)

summary = request_json("/content/intersections/summary")
listing = request_json("/content/intersections?limit=8")
if int(summary.get("totalCount") or 0) <= 0:
    raise SystemExit(f"intersection summary remains empty: {summary}")
if len(listing.get("items") or []) <= 0:
    raise SystemExit(f"intersection list remains empty: {listing}")

report = {
    "authenticatedProbe": True,
    "personObjectId": person,
    "entityObjectId": entity,
    "summaryTotalCount": summary.get("totalCount"),
    "summaryDimensions": [
        item.get("dimension")
        for item in summary.get("dimensions", [])
        if isinstance(item, dict)
    ],
    "listItemCount": len(listing.get("items") or []),
    "objectPointSources": [
        point.get("sourceRef")
        for item in reasons
        for point in item.get("intersectionPoints", [])
        if isinstance(point, dict)
    ],
}
Path(report_path).parent.mkdir(parents=True, exist_ok=True)
Path(report_path).write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(report, ensure_ascii=False))
PY
  then
    echo "[local-gamma] GATE_BLOCK: intersection seed failed; /content/intersections is unproven" >&2
    return 1
  fi
  echo "[local-gamma] intersection seed completed (${report})"
}
if [[ "$ENABLE_FIXTURE_SEEDS" == "1" ]]; then
  seed_gamma_intersection_data
else
  echo "[local-gamma] skip intersection seed because STAGE=${STAGE} uses persisted/host data"
fi

seed_gamma_premium_pool_data() {
  local mongo_port="${LOCAL_GAMMA_MONGO_PORT:-}"
  local redis_port="${LOCAL_GAMMA_REDIS_PORT:-}"
  local gateway="${GATEWAY_BASE_URL%/}"
  local report="${GAMMA_RUN_ROOT}/premium-pool-seed-report.json"
  if [[ -z "$mongo_port" ]]; then
    echo "[local-gamma] GATE_BLOCK: premium pool seed requires LOCAL_GAMMA_MONGO_PORT" >&2
    return 1
  fi
  if [[ -z "$redis_port" ]]; then
    echo "[local-gamma] GATE_BLOCK: premium pool seed requires LOCAL_GAMMA_REDIS_PORT" >&2
    return 1
  fi
  echo "[local-gamma] seeding premium pool projection and recall proof ..."
  if ! python3 - "$ROOT" "$mongo_port" "$redis_port" "$gateway" "$report" <<'PY'
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

root, mongo_port, redis_port, gateway, report_path = sys.argv[1:6]
sys.path.insert(0, root)

from quwoquan_ops.cli.lib.local_environment_auth import (
    open_local_acceptance_session,
    request_local_environment_json,
)

session = open_local_acceptance_session(
    gateway,
    environment="gamma",
    target_name="gamma-local",
)
eligible = "gamma_premium_pool_eligible_post"
expired = "gamma_premium_pool_expired_post"
rolled_back = "gamma_premium_pool_rolled_back_post"
takedown = "gamma_premium_pool_takedown_post"
all_ids = [eligible, expired, rolled_back, takedown]
cover = (
    os.environ["MEDIA_IMAGE_BASE_URL"] + "/s/"
    "archived-image/post/fixture_photo_001/v1/cover.png"
)

seed_js = f"""
const db = db.getSiblingDB('quwoquan_content');
const now = new Date();
const future = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);
const past = new Date(now.getTime() - 60 * 60 * 1000);
const ids = {json.dumps(all_ids)};
db.posts.deleteMany({{_id: {{$in: ids}}}});
db.rm_discovery_feed.deleteMany({{postId: {{$in: ids}}}});
db.rm_premium_pool.deleteMany({{contentId: {{$in: ids}}}});
for (const id of ids) {{
  db.posts.insertOne({{
    _id: id,
    postId: id,
    id: id,
    contentType: 'image',
    contentIdentity: 'work',
    title: id === '{eligible}' ? 'Gamma 精品池真实召回样例' : `Gamma 精品池不可召回样例 ${{id}}`,
    body: 'premium pool gamma seed',
    mediaUrls: ['{cover}'],
    coverUrl: '{cover}',
    thumbnailUrl: '{cover}',
    authorId: 'sys_travel_9003_sub_01',
    authorDisplayNameSnapshot: '交集约伴体验号',
    status: 'published',
    visibility: 'public',
    moderationStatus: 'approved',
    likeCount: 12,
    commentCount: 3,
    shareCount: 1,
    createdAt: now,
    updatedAt: now,
    publishedAt: now
  }});
  db.rm_discovery_feed.insertOne({{
    postId: id,
    contentType: 'image',
    authorId: 'sys_travel_9003_sub_01',
    title: id,
    tagRefs: ['Topic/旅行', 'Topic/摄影'],
    entityRefs: ['fixture_homepage_travel_photo_west_lake'],
    coverUrl: '{cover}',
    likeCount: 12,
    commentCount: 3,
    shareCount: 1,
    viewCount: 180,
    publishedAt: now,
    recScore: id === '{eligible}' ? 0.96 : 0.2,
    qualityScore: id === '{eligible}' ? 0.96 : 0.2,
    contentVertical: 'travel_photography',
    supplySource: 'product_ops'
  }});
}}
db.rm_premium_pool.insertMany([
  {{
    contentId: '{eligible}',
    scope: 'global',
    status: 'active',
    eligibilityState: 'eligible',
    ineligibleReasons: [],
    qualityAdmission: 'approved',
    qualityScore: 0.96,
    supplySource: 'product_ops',
    sourceTaskId: 'gamma_premium_pool_seed',
    auditId: 'audit_gamma_premium_eligible',
    rollbackToken: 'rbk_gamma_premium_eligible',
    featuredAt: now,
    expiresAt: future,
    takedownEjected: false,
    projectionVersion: 'premium_pool_projection_v1',
    updatedAt: now
  }},
  {{
    contentId: '{expired}',
    scope: 'global',
    status: 'active',
    eligibilityState: 'ineligible',
    ineligibleReasons: ['expired'],
    qualityAdmission: 'approved',
    qualityScore: 0.95,
    supplySource: 'product_ops',
    featuredAt: now,
    expiresAt: past,
    takedownEjected: false,
    projectionVersion: 'premium_pool_projection_v1',
    updatedAt: now
  }},
  {{
    contentId: '{rolled_back}',
    scope: 'global',
    status: 'rolled_back',
    eligibilityState: 'ineligible',
    ineligibleReasons: ['inactive_status'],
    qualityAdmission: 'approved',
    qualityScore: 0.94,
    supplySource: 'product_ops',
    featuredAt: now,
    expiresAt: future,
    takedownEjected: false,
    projectionVersion: 'premium_pool_projection_v1',
    updatedAt: now
  }},
  {{
    contentId: '{takedown}',
    scope: 'global',
    status: 'takedown_ejected',
    eligibilityState: 'ineligible',
    ineligibleReasons: ['takedown_ejected'],
    qualityAdmission: 'approved',
    qualityScore: 0.93,
    supplySource: 'product_ops',
    featuredAt: now,
    expiresAt: future,
    takedownEjected: true,
    projectionVersion: 'premium_pool_projection_v1',
    updatedAt: now
  }}
]);
printjson({{eligible: '{eligible}', ineligible: ['{expired}', '{rolled_back}', '{takedown}']}});
"""
seed = subprocess.run(
    [
        "mongosh",
        f"mongodb://127.0.0.1:{mongo_port}/?directConnection=true",
        "--quiet",
    ],
    input=seed_js,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    check=False,
)
if seed.returncode != 0:
    print(seed.stdout)
    print(seed.stderr, file=sys.stderr)
    raise SystemExit(seed.returncode)

# 精品池证明使用固定验收 actor 和内容 ID，以便 Gamma 多次运行的报告可比。每次
# 发起新请求前，只删除本证明历史的 served/impressed/negative membership；
# 否则上一次有效运行会由重复曝光门禁隐藏本次自身的证据。
acceptance_actor = "fixture_user_current"
today = datetime.now(timezone.utc).date()
reset_keys = [f"rec:negative:{{{acceptance_actor}}}"]
reset_keys.extend(
    f"rec:served:{{{acceptance_actor}}}:{(today - timedelta(days=offset)).strftime('%Y%m%d')}"
    for offset in range(2)
)
reset_keys.extend(
    f"rec:impressed:{{{acceptance_actor}}}:{(today - timedelta(days=offset)).strftime('%Y%m%d')}"
    for offset in range(7)
)
for key in reset_keys:
    reset = subprocess.run(
        [
            "redis-cli",
            "-h",
            "127.0.0.1",
            "-p",
            redis_port,
            "SREM",
            key,
            *all_ids,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if reset.returncode != 0:
        print(reset.stderr, file=sys.stderr)
        raise SystemExit("reset premium proof recommendation state failed")

body = request_local_environment_json(
    gateway,
    path="/content/feed?type=premium&limit=5",
    session=session,
)
items = body.get("items") or []
ids = [item.get("id") or item.get("postId") for item in items if isinstance(item, dict)]
if eligible not in ids:
    raise SystemExit(f"premium pool eligible item missing from feed: ids={ids}")
blocked = [item for item in (expired, rolled_back, takedown) if item in ids]
if blocked:
    raise SystemExit(f"ineligible premium pool items leaked into feed: {blocked}")
recall_paths = {
    (item.get("id") or item.get("postId")): item.get("recallPath")
    for item in items
    if isinstance(item, dict)
}
if recall_paths.get(eligible) != "premium_pool":
    raise SystemExit(f"eligible recallPath must be premium_pool, got {recall_paths.get(eligible)!r}")

report = {
    "authenticatedProbe": True,
    "eligibleContentId": eligible,
    "ineligibleContentIds": [expired, rolled_back, takedown],
    "feedItemIds": ids,
    "eligibleRecallPath": recall_paths.get(eligible),
}
Path(report_path).parent.mkdir(parents=True, exist_ok=True)
Path(report_path).write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(report, ensure_ascii=False))
PY
  then
    echo "[local-gamma] GATE_BLOCK: premium pool seed failed; premium stream recall is unproven" >&2
    return 1
  fi
  echo "[local-gamma] premium pool seed completed (${report})"
}
if [[ "$ENABLE_FIXTURE_SEEDS" == "1" ]]; then
  seed_gamma_premium_pool_data
else
  echo "[local-gamma] skip premium pool seed because STAGE=${STAGE} uses persisted/host data"
fi

# search-service 的 ES 召回读模型 cold-start：把已 seed 的内容（quwoquan_content.posts）
# 经统一投影回填进共享 ES 索引 quwoquan_objects（与 search-service 查询同一索引）。
# 这是检索读模型的环境 seed，与 tag/content seed 同级，保证 /search 返回真实 hit。
seed_search_index() {
  local es_port="${LOCAL_GAMMA_ES_PORT:-}"
  local mongo_port="${LOCAL_GAMMA_MONGO_PORT:-}"
  local postgres_port="${LOCAL_GAMMA_POSTGRES_PORT:-}"
  if [[ -z "$es_port" || -z "$mongo_port" || -z "$postgres_port" ]]; then
    echo "[local-gamma] FAIL: search backfill requires LOCAL_GAMMA_ES_PORT, LOCAL_GAMMA_MONGO_PORT and LOCAL_GAMMA_POSTGRES_PORT" >&2
    return 1
  fi
  echo "[local-gamma] waiting for ES host port ${es_port} (yellow) before search backfill ..."
  if ! python3 - "$es_port" <<'PY'
import sys
import time
import urllib.request

port = sys.argv[1]
deadline = time.time() + 120
last = None
ok = False
while time.time() < deadline:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/_cluster/health?wait_for_status=yellow&timeout=2s",
            timeout=4,
        ) as resp:
            if 200 <= int(resp.status) < 300:
                ok = True
                break
            last = f"http {resp.status}"
    except Exception as exc:  # noqa: BLE001
        last = str(exc)
    time.sleep(2)
raise SystemExit(0 if ok else (last or "es not ready"))
PY
  then
    echo "[local-gamma] FAIL: ES host port ${es_port} is not ready for search backfill" >&2
    return 1
  fi
  echo "[local-gamma] backfilling all search projections into ES quwoquan_objects ..."
  # batch-size 100：本地 ES 跑在 linux/amd64 模拟（Apple Silicon 无原生 8.x JDK），
  # 单节点写入吞吐受限；ES client RequestTimeout 默认 5s，500-doc 默认批的单次 _bulk
  # 会超时（服务端仍写入但 client 报 context deadline exceeded）。按 100/批切分后每个
  # _bulk 都在 5s 内返回，回填稳定干净成功（这是 backfill 暴露 --batch-size 的用途，
  # 非 shim：换原生 ES 集群时该值不影响正确性，只影响往返次数）。
  if ! ( cd "$ROOT/quwoquan_service" && SEARCH_ES_ENDPOINTS="http://127.0.0.1:${es_port}" \
      go run ./services/content-service/cmd/search-backfill \
      --mongo-uri "mongodb://127.0.0.1:${mongo_port}/?directConnection=true" \
      --posts-db quwoquan_content --env gamma --batch-size 100 \
      --request-timeout "$LOCAL_GAMMA_SEARCH_BACKFILL_REQUEST_TIMEOUT" ); then
    echo "[local-gamma] FAIL: content/place search backfill failed; gamma startup is blocked because /search would be incomplete" >&2
    return 1
  fi
  if ! ( cd "$ROOT/quwoquan_service" && SEARCH_ES_ENDPOINTS="http://127.0.0.1:${es_port}" \
      go run ./services/entity-service/cmd/search-backfill \
      --mongo-uri "mongodb://127.0.0.1:${mongo_port}/?directConnection=true" \
      --entity-db quwoquan_entity --env gamma --batch-size 100 ); then
    echo "[local-gamma] FAIL: entity homepage search backfill failed; gamma startup is blocked because /search would be incomplete" >&2
    return 1
  fi
  if ! ( cd "$ROOT/quwoquan_service" && SEARCH_ES_ENDPOINTS="http://127.0.0.1:${es_port}" \
      go run ./services/circle-service/cmd/search-backfill \
      --mongo-uri "mongodb://127.0.0.1:${mongo_port}/?directConnection=true" \
      --circle-db quwoquan_circle --env gamma --batch-size 100 ); then
    echo "[local-gamma] FAIL: circle/group search backfill failed; gamma startup is blocked because /search would be incomplete" >&2
    return 1
  fi
  if ! ( cd "$ROOT/quwoquan_service" && SEARCH_ES_ENDPOINTS="http://127.0.0.1:${es_port}" \
      go run ./services/user-service/cmd/search-backfill \
      --postgres-dsn "postgres://quwoquan:quwoquan@127.0.0.1:${postgres_port}/quwoquan?sslmode=disable" \
      --env gamma --batch-size 100 ); then
    echo "[local-gamma] FAIL: user profile search backfill failed; gamma startup is blocked because /search would be incomplete" >&2
    return 1
  fi
  echo "[local-gamma] all search index backfills completed (content/place, entity, circle/group, user)"
}
if [[ "$ENABLE_FIXTURE_SEEDS" == "1" ]]; then
  seed_search_index
  write_local_gamma_data_plane_watermark "$(compute_local_gamma_data_plane_digest)"
  echo "[local-gamma] wrote data-plane watermark: ${LOCAL_GAMMA_DATA_PLANE_WATERMARK}"
else
  echo "[local-gamma] skip search backfill because STAGE=${STAGE} uses persisted/host data"
fi

python3 - "$stack_report" "$CONFIG_VERSION" "$IMAGE_VERSION" "$PREVIOUS_IMAGE_VERSION" "$STAGE" "$LOCAL_GAMMA_APP_ENV" "$CONFIG_SOURCE_ENV" "$GATEWAY_BASE_URL" "$PRODUCT_OPS_BASE_URL" "$MEDIA_IMAGE_BASE_URL" "$restarted_from_previous" "$WORKLOAD" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

(
    report_path,
    config_version,
    image_version,
    previous_image_version,
    stage,
    runtime_env,
    config_env,
    gateway,
    product_ops,
    media,
    restarted,
    workload,
) = sys.argv[1:13]
payload = {
    "status": "passed",
    "workload": workload,
    "serviceMode": "single-stack",
    "restartedFromPrevious": restarted == "1",
    "stage": stage,
    "configVersion": config_version,
    "imageVersion": image_version,
    "previousImageVersion": previous_image_version or None,
    "runtimeEnv": runtime_env,
    "configEnv": config_env,
    "gatewayBaseUrl": gateway,
    "productOpsBaseUrl": product_ops,
    "mediaEdgeBaseUrl": media,
    "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
}
path = Path(report_path)
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

echo "[local-gamma] service mode: single-stack"
echo "[local-gamma] mirror started"
echo "[local-gamma] gateway: $GATEWAY_BASE_URL"
echo "[local-gamma] product-ops: $PRODUCT_OPS_BASE_URL"
echo "[local-gamma] media-image: $MEDIA_IMAGE_BASE_URL"
echo "[local-gamma] dart defines:"
print_defines
