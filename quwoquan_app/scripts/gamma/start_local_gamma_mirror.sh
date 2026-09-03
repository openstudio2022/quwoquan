#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
LOCAL_GAMMA_ACTIVE_CHILD_PID=""
STARTUP_ATTEMPT_PREPARED=0
STARTUP_ATTEMPT_PARTIAL=0
STARTUP_ATTEMPT_RUNNING=0

cleanup_active_child() {
  local exit_status="$?"
  local cleanup_status=0
  local cleanup_failure=""
  set +e
  if [[ -n "$LOCAL_GAMMA_ACTIVE_CHILD_PID" ]] \
    && kill -0 "$LOCAL_GAMMA_ACTIVE_CHILD_PID" >/dev/null 2>&1; then
    echo "[local-gamma] stopping active child before exit" >&2
    kill "$LOCAL_GAMMA_ACTIVE_CHILD_PID" >/dev/null 2>&1 || true
    wait "$LOCAL_GAMMA_ACTIVE_CHILD_PID" >/dev/null 2>&1 || true
  fi
  LOCAL_GAMMA_ACTIVE_CHILD_PID=""
  if [[ "$exit_status" != "0" \
     && "$STARTUP_ATTEMPT_PREPARED" == "1" \
     && "$STARTUP_ATTEMPT_PARTIAL" != "1" \
     && "$STARTUP_ATTEMPT_RUNNING" != "1" \
     && "${formal_release:-0}" != "1" ]]; then
    echo "[local-gamma] startup failed before runtime mutation; closing prepared attempt" >&2
    write_startup_attempt \
      stopped \
      "startup exited with status ${exit_status} before runtime mutation" \
      "" || true
  fi
  if [[ "$exit_status" != "0" \
     && "$STARTUP_ATTEMPT_PARTIAL" == "1" \
     && "$STARTUP_ATTEMPT_RUNNING" != "1" \
     && "${formal_release:-0}" != "1" ]]; then
    echo "[local-gamma] startup failed after partial mutation; tearing down attempt resources" >&2
    if declare -F capture_content_startup_health_failure >/dev/null 2>&1; then
      capture_content_startup_health_failure || true
    fi
    if declare -F stop_colima_tunnels >/dev/null 2>&1; then
      stop_colima_tunnels || cleanup_status=$?
    fi
    if declare -p compose_cmd >/dev/null 2>&1; then
      "${compose_cmd[@]}" ps -a >&2 || true
      # candidate topology 投影后一方服务收敛为 service-core,dev topology 仍是
      # 每服务 compose;`docker compose logs` 对任一未知服务名整体拒绝执行,
      # 一次性多服务名单会把唯一的失败证据全部丢掉(no such service)。
      # 以 config --services 为服务名真相源,逐服务 dump。
      teardown_available_services="$("${compose_cmd[@]}" config --services 2>/dev/null || true)"
      for teardown_log_service in \
        service-core api-edge content-service user-service entity-service \
        integration-service recommendation-service product-ops-service \
        platform-ops-service realtime-gateway rtc-service gamma-proxy; do
        if [[ -n "$teardown_available_services" ]] \
          && ! grep -qx "$teardown_log_service" <<<"$teardown_available_services"; then
          continue
        fi
        "${compose_cmd[@]}" logs --tail 120 "$teardown_log_service" >&2 || true
      done
      "${compose_cmd[@]}" down --remove-orphans || cleanup_status=$?
    else
      cleanup_status=1
    fi
    if [[ "$cleanup_status" == "0" ]]; then
      write_startup_attempt \
        stopped \
        "startup exited with status ${exit_status}" \
        "" || true
    else
      cleanup_failure="partial runtime teardown failed with status ${cleanup_status}"
      write_startup_attempt \
        partial \
        "startup exited with status ${exit_status}" \
        "$cleanup_failure" || true
    fi
  fi
  trap - EXIT INT TERM HUP
  exit "$exit_status"
}
trap cleanup_active_child EXIT INT TERM HUP

QWQ_OUTPUT_ROOT="${QWQ_OUTPUT_ROOT:-$ROOT/.qwq_output}"
QWQ_DEPLOY_WORK_ROOT="${QWQ_DEPLOY_WORK_ROOT:-${XDG_CACHE_HOME:-$HOME/.cache}/quwoquan/deploy}"
if [[ ! -d "$QWQ_DEPLOY_WORK_ROOT" ]]; then
  echo "[local-release] GATE_BLOCK: deploy work root is unavailable" >&2
  exit 2
fi
# macOS exposes /var through /private/var. Package descriptors are emitted
# with the physical path, so normalize the configured root before enforcing
# candidate containment.
QWQ_DEPLOY_WORK_ROOT="$(cd "$QWQ_DEPLOY_WORK_ROOT" && pwd -P)"
QWQ_LOCAL_RELEASE_ENV="${QWQ_LOCAL_RELEASE_ENV:-gamma}"
QWQ_LOCAL_RELEASE_TARGET="${QWQ_LOCAL_RELEASE_TARGET:-${QWQ_LOCAL_RELEASE_ENV}-local}"
if [[ "$QWQ_LOCAL_RELEASE_ENV" != "alpha" \
   && "$QWQ_LOCAL_RELEASE_ENV" != "beta" \
   && "$QWQ_LOCAL_RELEASE_ENV" != "gamma" ]]; then
  echo "[local-release] GATE_BLOCK: unsupported environment $QWQ_LOCAL_RELEASE_ENV" >&2
  exit 2
fi
if [[ "$QWQ_LOCAL_RELEASE_TARGET" != "${QWQ_LOCAL_RELEASE_ENV}-local" ]]; then
  echo "[local-release] GATE_BLOCK: target does not belong to environment" >&2
  exit 2
fi
if [[ "${QWQ_PREPARED_ATTEMPT_ONLY:-0}" == "1" ]]; then
  prepared_down=0
  for arg in "$@"; do
    if [[ "$arg" == "--down" ]]; then prepared_down=1; fi
  done
  if [[ "$prepared_down" != "1" ]]; then
    echo "[local-release] GATE_BLOCK: prepared-attempt recovery is teardown-only" >&2
    exit 2
  fi
  echo "[local-gamma] prepared attempt has no runtime resources; skipping runtime materialization"
  exit 0
fi
export QWQ_LOCAL_RELEASE_ENV QWQ_LOCAL_RELEASE_TARGET
EARLY_BUILD_ONLY=0
for early_arg in "$@"; do
  if [[ "$early_arg" == "--build-only" ]]; then
    EARLY_BUILD_ONLY=1
  fi
done
PRODUCT_TELEMETRY_AVAILABLE="${QWQ_PRODUCT_TELEMETRY_AVAILABLE:-1}"
PRODUCT_OPS_REQUIRED=1
WORKLOAD="${QWQ_WORKLOAD:-full}"
PROVIDER_RUNTIME_DIGEST="${QWQ_PROVIDER_RUNTIME_DIGEST:-}"
if [[ ! "$PROVIDER_RUNTIME_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "[local-release] GATE_BLOCK: package-bound Provider runtime digest is required" >&2
  exit 2
fi
OBSERVABILITY_LOG_SINK_COMPOSE_FILE="${QWQ_OBSERVABILITY_LOG_SINK_COMPOSE_FILE:-}"
OBSERVABILITY_LOG_SINK_DIGEST="${QWQ_OBSERVABILITY_LOG_SINK_DIGEST:-}"
case "$WORKLOAD" in
  content-release)
    # Content import/API/media are intentionally independent from commercial
    # telemetry.  The release profile validates telemetry separately.
    PRODUCT_TELEMETRY_AVAILABLE=0
    PRODUCT_OPS_REQUIRED=0
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
  content-commercial)
    # This is the bounded content consumer + Product Ops premium command/event
    # plane. It must not silently enable Assistant, RTC or other full-workload
    # profiles, and it does not claim the full telemetry/trace/SLO gate.
    PRODUCT_TELEMETRY_AVAILABLE=0
    PRODUCT_OPS_REQUIRED=1
    COMPOSE_PROFILES="commercial-observability"
    export COMPOSE_PROFILES
    ;;
  full)
    if [[ "$PRODUCT_TELEMETRY_AVAILABLE" != "1" ]]; then
      echo "[local-gamma] GATE_BLOCK: full workload requires product telemetry" >&2
      exit 2
    fi
    if [[ -z "${QWQ_PROVIDER_RUNTIME_COMPOSE_FILES:-}" \
       || -z "${QWQ_PROVIDER_RUNTIME_COMPOSE_PROFILES:-}" ]]; then
      echo "[local-gamma] GATE_BLOCK: full workload requires package-bound Provider workloads" >&2
      exit 2
    fi
    # full workload 无条件加载 platform-ops fragment，而 base compose 把该服务
    # 挂在 control-plane profile 上（bounded content workload 靠这个 profile 整份
    # 排除它）。不激活该 profile，Compose 会在 full 下也排除 platform-ops，而
    # gamma_platform_ops_ready 仍要求它就绪，等价于必然超时。
    export COMPOSE_PROFILES="${COMPOSE_PROFILES:+${COMPOSE_PROFILES},}commercial-observability,assistant-runtime,edge-media,control-plane,${QWQ_PROVIDER_RUNTIME_COMPOSE_PROFILES}"
    ;;
  *)
    echo "[local-gamma] FAIL: QWQ_WORKLOAD must be content-release, content-commercial or full" >&2
    exit 2
    ;;
esac
if [[ "$WORKLOAD" == "full" || "$WORKLOAD" == "content-commercial" ]]; then
  if [[ ! "$OBSERVABILITY_LOG_SINK_DIGEST" =~ ^sha256:[0-9a-f]{64}$ \
     || -z "$OBSERVABILITY_LOG_SINK_COMPOSE_FILE" \
     || -z "${PRODUCT_OPS_ELASTICSEARCH_ENDPOINT:-}" ]]; then
    echo "[local-release] GATE_BLOCK: candidate-bound Elasticsearch runtime is required" >&2
    exit 2
  fi
fi
LOCAL_RUN_ACTION="up"
for arg in "$@"; do
  if [[ "$arg" == "--down" ]]; then LOCAL_RUN_ACTION="down"; fi
done
eval "$(python3 "$ROOT/quwoquan_ops/cli/lib/local_run.py" \
  --env "$QWQ_LOCAL_RELEASE_ENV" --target "$QWQ_LOCAL_RELEASE_TARGET" \
  --action "$LOCAL_RUN_ACTION" --output-root "$QWQ_OUTPUT_ROOT")"
export QWQ_OUTPUT_ROOT QWQ_DEPLOY_WORK_ROOT QWQ_OBSERVABILITY_RUN_ROOT QWQ_RUN_ROOT
write_startup_attempt() {
  local status="$1"
  local failure="${2:-}"
  local cleanup_failure="${3:-}"
  local -a receipt_args=(
    --env "$QWQ_LOCAL_RELEASE_ENV" \
    --target "$QWQ_LOCAL_RELEASE_TARGET" \
    --attempt-id "$QWQ_LOCAL_RUN_ID" \
    --status "$status" \
    --failure "$failure" \
    --cleanup-failure "$cleanup_failure"
  )
  if [[ "$status" == "prepared" ]]; then
    local startup_image_file="${QWQ_STARTUP_IMAGE_COMPOSITION_FILE:-}"
    local startup_image_tag="${QWQ_STARTUP_IMAGE_TRANSPORT_TAG:-}"
    if [[ "$startup_image_file" != /* \
       || ! -f "$startup_image_file" \
       || -L "$startup_image_file" \
       || ! "$startup_image_tag" =~ ^sha256:[0-9a-f]{64}$ ]]; then
      echo "[local-release] GATE_BLOCK: active-candidate full OCI startup identity is required" >&2
      return 2
    fi
    receipt_args+=(
      --workload "$WORKLOAD"
      --compose-project "${LOCAL_GAMMA_COMPOSE_PROJECT_NAME:-}"
      --candidate-digest "${QWQ_RELEASE_CANDIDATE_DIGEST:-}"
      --configuration-digest "${CONFIG_VERSION:-}"
      --provider-runtime-digest "$PROVIDER_RUNTIME_DIGEST"
      --observability-log-sink-digest "$OBSERVABILITY_LOG_SINK_DIGEST"
      --image-transport-tag "$startup_image_tag"
      --image-composition-file "$startup_image_file"
      --run-root "$QWQ_RUN_ROOT"
    )
  fi
  PYTHONDONTWRITEBYTECODE=1 python3 \
    "$ROOT/quwoquan_ops/cli/lib/startup_attempt_receipt/startup_attempt_receipt.py" \
    "${receipt_args[@]}"
}
COMPOSE_FILES=()
QWQ_RUNTIME_TOPOLOGY_POLICY_FILE=""
QWQ_RUNTIME_TOPOLOGY_DIGEST=""
if [[ "$EARLY_BUILD_ONLY" == "1" ]]; then
  # Package creation is the only phase allowed to read source Compose.  The
  # resulting candidate seals transformed, image-only topology bytes below
  # packages/runtime-shared/runtime-topology.
  COMPOSE_FILE="$ROOT/quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
  COMPOSE_FILES=("$COMPOSE_FILE")
  if [[ "$WORKLOAD" == "content-release" || "$WORKLOAD" == "content-commercial" ]]; then
    content_slice_services=(
      api-edge
      recommendation-service
      content-service
      user-service
      entity-service
      search-service
    )
    if [[ "$WORKLOAD" == "content-commercial" ]]; then
      content_slice_services+=(product-ops-service)
    fi
    if [[ "$WORKLOAD" == "content-release" ]]; then
      bounded_search_elasticsearch_compose="$QWQ_RUN_ROOT/attachments/bounded-search-elasticsearch.compose.yaml"
      if ! PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - \
        "$bounded_search_elasticsearch_compose" "$ROOT" <<'PY_BOUNDED_SEARCH_ES'
import sys
from pathlib import Path

from quwoquan_ops.cli.lib.runtime_topology_package import (
    materialize_bounded_search_elasticsearch_compose,
)

materialize_bounded_search_elasticsearch_compose(
    Path(sys.argv[1]),
    repo_root=Path(sys.argv[2]),
)
PY_BOUNDED_SEARCH_ES
      then
        echo "[local-release] GATE_BLOCK: bounded Search Elasticsearch execution copy failed" >&2
        exit 2
      fi
      COMPOSE_FILES+=("$bounded_search_elasticsearch_compose")
    fi
    for content_slice_service in "${content_slice_services[@]}"; do
      service_compose_file="$ROOT/quwoquan_service/services/${content_slice_service}/deploy/compose.yaml"
      if [[ ! -f "$service_compose_file" ]]; then
        echo "[local-release] GATE_BLOCK: missing bounded content compose file $service_compose_file" >&2
        exit 2
      fi
      COMPOSE_FILES+=("$service_compose_file")
      service_environment_compose_file="$ROOT/quwoquan_service/services/${content_slice_service}/environments/${QWQ_LOCAL_RELEASE_ENV}/deploy/compose.yaml"
      if [[ -f "$service_environment_compose_file" ]]; then
        COMPOSE_FILES+=("$service_environment_compose_file")
      fi
    done
  else
    # 只纳入 runtime topology ∩ 自治服务根（与 compose_layout.first_party 同源）。
    # 禁止 find 扫入已退役服务目录内残留的 compose，否则
    # docker compose 会因缺失 QWQ_COMPOSE_*_CONFIG_VERSION 直接 GATE_BLOCK。
    while IFS= read -r service_compose_file; do
      [[ -n "$service_compose_file" ]] || continue
      COMPOSE_FILES+=("$service_compose_file")
    done < <(
      ROOT="$ROOT" QWQ_LOCAL_RELEASE_ENV="$QWQ_LOCAL_RELEASE_ENV" \
        PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import os
from pathlib import Path

from quwoquan_ops.cli.lib.immutable_image_composition import first_party_service_names

root = Path(os.environ["ROOT"])
env_name = os.environ["QWQ_LOCAL_RELEASE_ENV"]
active = set(first_party_service_names(root))
services_root = root / "quwoquan_service" / "services"
for path in sorted(services_root.glob("*/deploy/compose.yaml")):
    if path.parents[1].name in active:
        print(path)
for path in sorted(
    services_root.glob(f"*/environments/{env_name}/deploy/compose.yaml")
):
    if path.parents[3].name in active:
        print(path)
PY
    )
    COMPOSE_FILES+=("$ROOT/quwoquan_service/control-plane/platform-ops/deploy/compose.yaml")
  fi
else
  RUNTIME_CANDIDATE_ROOT="${QWQ_RUNTIME_CANDIDATE_ROOT:-}"
  expected_candidate_leaf="${QWQ_RELEASE_CANDIDATE_DIGEST/:/-}"
  case "$RUNTIME_CANDIDATE_ROOT" in
    "$QWQ_DEPLOY_WORK_ROOT/$QWQ_LOCAL_RELEASE_TARGET/candidates/runtime-full/$expected_candidate_leaf") ;;
    *)
      echo "[local-release] GATE_BLOCK: exact runtime candidate root is required" >&2
      exit 2
      ;;
  esac
  if [[ ! -d "$RUNTIME_CANDIDATE_ROOT" || -L "$RUNTIME_CANDIDATE_ROOT" ]]; then
    echo "[local-release] GATE_BLOCK: runtime candidate root is unsafe" >&2
    exit 2
  fi
  if ! topology_environment="$({
    PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 \
      "$ROOT/quwoquan_ops/cli/lib/runtime_topology_package.py" \
      --candidate-root "$RUNTIME_CANDIDATE_ROOT" \
      --environment "$QWQ_LOCAL_RELEASE_ENV" \
      --target "$QWQ_LOCAL_RELEASE_TARGET" \
      --workload "$WORKLOAD" \
      --format shell
  } 2>&1)"; then
    echo "[local-release] $topology_environment" >&2
    exit 2
  fi
  eval "$topology_environment"
  if [[ ! "$QWQ_RUNTIME_TOPOLOGY_DIGEST" =~ ^sha256:[0-9a-f]{64}$ \
     || -z "$QWQ_RUNTIME_TOPOLOGY_COMPOSE_FILES" \
     || -z "$QWQ_RUNTIME_TOPOLOGY_POLICY_FILE" ]]; then
    echo "[local-release] GATE_BLOCK: candidate runtime topology identity is incomplete" >&2
    exit 2
  fi
  # stackctl clears any inherited override before launch.  Reintroduce only
  # the exact no-follow validated candidate package root so later config/legal
  # helpers cannot re-resolve a newly activated pointer.
  QWQ_DEPLOY_PACKAGE_ROOT_OVERRIDE="$RUNTIME_CANDIDATE_ROOT/packages"
  export QWQ_DEPLOY_PACKAGE_ROOT_OVERRIDE
  while IFS= read -r candidate_compose_file; do
    [[ -n "$candidate_compose_file" ]] || continue
    COMPOSE_FILES+=("$candidate_compose_file")
  done <<< "$QWQ_RUNTIME_TOPOLOGY_COMPOSE_FILES"
fi
if [[ "$WORKLOAD" == "full" ]]; then
  provider_compose_files=()
  provider_compose_digests=()
  while IFS= read -r provider_compose_file; do
    [[ -n "$provider_compose_file" ]] || continue
    provider_compose_files+=("$provider_compose_file")
  done <<< "$QWQ_PROVIDER_RUNTIME_COMPOSE_FILES"
  while IFS= read -r provider_compose_digest; do
    [[ -n "$provider_compose_digest" ]] || continue
    provider_compose_digests+=("$provider_compose_digest")
  done <<< "${QWQ_PROVIDER_RUNTIME_COMPOSE_DIGESTS:-}"
  if [[ "${#provider_compose_files[@]}" -eq 0 \
     || "${#provider_compose_files[@]}" -ne "${#provider_compose_digests[@]}" ]]; then
    echo "[local-release] GATE_BLOCK: Provider Compose digest closure is incomplete" >&2
    exit 2
  fi
  for ((provider_index = 0; provider_index < ${#provider_compose_files[@]}; provider_index++)); do
    provider_compose_file="${provider_compose_files[$provider_index]}"
    provider_compose_digest="${provider_compose_digests[$provider_index]}"
    if [[ "$EARLY_BUILD_ONLY" == "1" ]]; then
      case "$provider_compose_file" in
        "$QWQ_DEPLOY_WORK_ROOT/$QWQ_LOCAL_RELEASE_TARGET/candidates/runtime-full/"*) ;;
        *)
          echo "[local-release] GATE_BLOCK: Provider Compose is outside candidate staging" >&2
          exit 2
          ;;
      esac
    else
      case "$provider_compose_file" in
        "$RUNTIME_CANDIDATE_ROOT/"*) ;;
        *)
          echo "[local-release] GATE_BLOCK: Provider Compose is outside the exact runtime candidate" >&2
          exit 2
          ;;
      esac
    fi
    if [[ ! -f "$provider_compose_file" || -L "$provider_compose_file" \
       || ! "$provider_compose_digest" =~ ^sha256:[0-9a-f]{64}$ ]]; then
      echo "[local-release] GATE_BLOCK: packaged Provider Compose identity is unavailable" >&2
      exit 2
    fi
    actual_provider_compose_digest="sha256:$(shasum -a 256 "$provider_compose_file" | awk '{print $1}')"
    if [[ "$actual_provider_compose_digest" != "$provider_compose_digest" ]]; then
      echo "[local-release] GATE_BLOCK: packaged Provider Compose digest drifted" >&2
      exit 2
    fi
    COMPOSE_FILES+=("$provider_compose_file")
  done
fi
if [[ "$WORKLOAD" == "full" || "$WORKLOAD" == "content-commercial" ]]; then
  if [[ "$EARLY_BUILD_ONLY" == "1" ]]; then
    case "$OBSERVABILITY_LOG_SINK_COMPOSE_FILE" in
      "$QWQ_DEPLOY_WORK_ROOT/$QWQ_LOCAL_RELEASE_TARGET/candidates/runtime-full/"*) ;;
      *)
        echo "[local-release] GATE_BLOCK: Elasticsearch Compose is outside candidate staging" >&2
        exit 2
        ;;
    esac
  else
    case "$OBSERVABILITY_LOG_SINK_COMPOSE_FILE" in
      "$RUNTIME_CANDIDATE_ROOT/"*) ;;
      *)
        echo "[local-release] GATE_BLOCK: Elasticsearch Compose is outside the exact runtime candidate" >&2
        exit 2
        ;;
    esac
  fi
  if [[ ! -f "$OBSERVABILITY_LOG_SINK_COMPOSE_FILE" \
     || -L "$OBSERVABILITY_LOG_SINK_COMPOSE_FILE" ]]; then
    echo "[local-release] GATE_BLOCK: packaged Elasticsearch Compose is unavailable" >&2
    exit 2
  fi
  actual_log_sink_digest="sha256:$(shasum -a 256 "$OBSERVABILITY_LOG_SINK_COMPOSE_FILE" | awk '{print $1}')"
  if [[ "$actual_log_sink_digest" != "$OBSERVABILITY_LOG_SINK_DIGEST" ]]; then
    echo "[local-release] GATE_BLOCK: packaged Elasticsearch Compose digest drifted" >&2
    exit 2
  fi
  COMPOSE_FILES+=("$OBSERVABILITY_LOG_SINK_COMPOSE_FILE")
fi
COMPOSE_FILE_ARGS=()
for service_compose_file in "${COMPOSE_FILES[@]}"; do
  COMPOSE_FILE_ARGS+=(-f "$service_compose_file")
done
default_compose_project="quwoquan_${QWQ_LOCAL_RELEASE_ENV}_release"
LOCAL_GAMMA_COMPOSE_PROJECT_NAME="${LOCAL_GAMMA_COMPOSE_PROJECT_NAME:-$default_compose_project}"
LOCAL_GAMMA_RESOURCE_PREFIX="$(
  printf '%s' "$LOCAL_GAMMA_COMPOSE_PROJECT_NAME" |
    tr -c '[:alnum:]_.-' '-' |
    sed 's/^-*//; s/-*$//'
)"
if [[ -z "$LOCAL_GAMMA_RESOURCE_PREFIX" ]]; then
  echo "[local-gamma] GATE_BLOCK: Compose project has no safe resource prefix." >&2
  exit 2
fi
if [[ "$EARLY_BUILD_ONLY" == "1" ]]; then
  LOCAL_GAMMA_REC_POLICY_SOURCE="$ROOT/quwoquan_service/services/content-service/resources/policies/content/post/recommendation_policy.yaml"
else
  LOCAL_GAMMA_REC_POLICY_SOURCE="$QWQ_RUNTIME_TOPOLOGY_POLICY_FILE"
fi
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
   || -z "${LOCAL_GAMMA_SMS_SUBSTITUTE_PORT:-}" \
   || -z "${LOCAL_GAMMA_NOTIFICATION_PORT:-}" \
   || -z "${LOCAL_GAMMA_POSTGRES_PORT:-}" \
   || -z "${LOCAL_GAMMA_MONGO_PORT:-}" \
   || -z "${LOCAL_GAMMA_REDIS_PORT:-}" \
   || -z "${LOCAL_GAMMA_ES_PORT:-}" \
   || -z "${LOCAL_GAMMA_ADMIN_PORT:-}" ]]; then
  eval "$(python3 "$ROOT/quwoquan_ops/cli/print_local_port_profile.py" --profile "$QWQ_LOCAL_RELEASE_TARGET" --format shell-defaults)"
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
  LOCAL_GAMMA_SMS_SUBSTITUTE_PORT \
  LOCAL_GAMMA_NOTIFICATION_PORT \
  LOCAL_GAMMA_POSTGRES_PORT \
  LOCAL_GAMMA_MONGO_PORT \
  LOCAL_GAMMA_MONGO_CACHE_SIZE_GB \
  LOCAL_GAMMA_REDIS_PORT \
  LOCAL_GAMMA_ES_PORT \
  LOCAL_GAMMA_ADMIN_PORT

export_service_compose_environment() {
  local source_name target_name
  export QWQ_COMPOSE_ENV="$QWQ_LOCAL_RELEASE_ENV"
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
first_party_image_owners() {
  # 镜像 env 校验必须与 stackctl 注入的部署镜像集合同源:核心服务模块
  # 已合并为单一 service-core 镜像,不能再按逻辑服务全集要求每服务镜像。
  PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from quwoquan_ops.cli.lib.immutable_image_composition import runtime_image_owner_names

print("\n".join(runtime_image_owner_names()))
PY
}
first_party_config_package_owners() {
  # 服务配置包仍按逻辑服务自治打包(packages/services/<service>),
  # 与镜像 owner 集合(service-core 合并)是两个不同的集合。
  PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from quwoquan_ops.cli.lib.immutable_image_composition import first_party_service_names

print("\n".join(first_party_service_names()))
PY
}
CONFIG_VERSION="${LOCAL_GAMMA_CONFIG_VERSION:-}"
if [[ ! "$CONFIG_VERSION" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "[local-release] GATE_BLOCK: LOCAL_GAMMA_CONFIG_VERSION must be the canonical sha256 runtime configuration digest" >&2
  exit 2
fi
IMAGE_VERSION="${LOCAL_GAMMA_IMAGE_VERSION:-}"
eval "$(
  PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import shlex
from urllib.parse import urlsplit

from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
)

import os

bases = get_target(
    load_environment_topology(), os.environ["QWQ_LOCAL_RELEASE_TARGET"]
)["publicBases"]
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
    ("QWQ_PUBLIC_UPLOAD_HOST", "mediaUpload"),
):
    print(f"{name}={shlex.quote(str(urlsplit(str(bases[role])).hostname))}")
PY
)"
PUBLIC_HOSTS=(
  "$QWQ_PUBLIC_API_HOST"
  "$QWQ_PUBLIC_WEB_HOST"
  "$QWQ_PUBLIC_OPS_HOST"
  "$QWQ_PUBLIC_CDN_HOST"
  "$QWQ_PUBLIC_UPLOAD_HOST"
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
LOCAL_GAMMA_DEPLOY_RENDER_ROOT="${QWQ_DEPLOY_WORK_ROOT}/${QWQ_LOCAL_RELEASE_TARGET}/rendered"
LOCAL_GAMMA_CACHE_ROOT="${QWQ_OUTPUT_ROOT}/env/${QWQ_LOCAL_RELEASE_ENV}/local/${QWQ_LOCAL_RELEASE_TARGET}/cache"
LOCAL_GAMMA_PROCESS_ROOT="${QWQ_OUTPUT_ROOT}/env/${QWQ_LOCAL_RELEASE_ENV}/local/${QWQ_LOCAL_RELEASE_TARGET}/process"
LOCAL_GAMMA_RUNTIME_LOG_ROOT="${QWQ_OBSERVABILITY_RUN_ROOT}/logs/service"
GAMMA_RUN_ROOT="${QWQ_RUN_ROOT}"
# 渲染配置是部署过程临时输入，真相源始终在 Ops/服务的 deploy 与 configs 目录。
LOCAL_GAMMA_CONFIG_ROOT="${LOCAL_GAMMA_DEPLOY_RENDER_ROOT}/config-root"
LOCAL_GAMMA_MEDIA_ROOT="${LOCAL_GAMMA_CACHE_ROOT}/media"
LOCAL_GAMMA_CADDY_DATA_VOLUME="${LOCAL_GAMMA_CADDY_DATA_VOLUME:-local-gamma-caddy-data}"
LOCAL_GAMMA_CADDY_CONFIG_VOLUME="${LOCAL_GAMMA_CADDY_CONFIG_VOLUME:-local-gamma-caddy-config}"
tls_exports="$(
  PYTHONDONTWRITEBYTECODE=1 python3 \
    "$ROOT/quwoquan_ops/cli/lib/public_domain_tls.py" paths \
    --target "$QWQ_LOCAL_RELEASE_TARGET" \
    --format shell \
    --allow-missing
)" || exit $?
eval "$tls_exports"
# Host-side readiness probes must validate the same local-managed CA that
# stackctl issued for this target.  Relying on the macOS system trust store
# makes a correct canonical certificate fail with curl (60).
if [[ -n "${QWQ_LOCAL_MANAGED_CA_FILE:-}" ]]; then
  export CURL_CA_BUNDLE="${CURL_CA_BUNDLE:-$QWQ_LOCAL_MANAGED_CA_FILE}"
fi
LOCAL_GAMMA_MODEL_CACHE_ROOT="${LOCAL_GAMMA_CACHE_ROOT}/model"
LOCAL_GAMMA_PORTAL_ROOT="${LOCAL_GAMMA_PORTAL_ROOT:-${QWQ_DEPLOY_WORK_ROOT}/${QWQ_LOCAL_RELEASE_TARGET}/build/ops-portal}"
STAGE="${STAGE:-$QWQ_LOCAL_RELEASE_ENV}"
LOCAL_GAMMA_APP_ENV="${LOCAL_GAMMA_APP_ENV:-}"
CONFIG_SOURCE_ENV="${CONFIG_SOURCE_ENV:-}"
LOCAL_GAMMA_READY_INDEX_SUFFIX="${LOCAL_GAMMA_READY_INDEX_SUFFIX:-}"
case "$STAGE" in
  alpha|beta|gamma)
    if [[ "$STAGE" != "$QWQ_LOCAL_RELEASE_ENV" ]]; then
      echo "[local-release] GATE_BLOCK: stage does not match environment" >&2
      exit 2
    fi
    LOCAL_GAMMA_APP_ENV="${LOCAL_GAMMA_APP_ENV:-$QWQ_LOCAL_RELEASE_ENV}"
    CONFIG_SOURCE_ENV="${CONFIG_SOURCE_ENV:-$QWQ_LOCAL_RELEASE_ENV}"
    LOCAL_GAMMA_READY_INDEX_SUFFIX="${LOCAL_GAMMA_READY_INDEX_SUFFIX:-local-${QWQ_LOCAL_RELEASE_ENV}}"
    # 三个本地环境保持 production Remote composition 与完整第一方拓扑；
    # required Provider 材料由 stackctl 从受保护环境注入。
    ;;
  prod)
    LOCAL_GAMMA_APP_ENV="${LOCAL_GAMMA_APP_ENV:-prod}"
    CONFIG_SOURCE_ENV="${CONFIG_SOURCE_ENV:-prod}"
    LOCAL_GAMMA_READY_INDEX_SUFFIX="${LOCAL_GAMMA_READY_INDEX_SUFFIX:-prod-onebox}"
    # prod 只消费 environments/prod 的正式 Provider Binding，缺凭据必须 fail-fast。
    ;;
  *)
    echo "[local-release] FAIL: unsupported STAGE=$STAGE" >&2
    exit 2
    ;;
esac
# Ops owns these immutable runtime files. stackctl package projects their exact
# bytes into runtime-shared; up must never bind-mount the mutable source tree.
if [[ "$EARLY_BUILD_ONLY" == "1" ]]; then
  LOCAL_GAMMA_RUNTIME_SHARED_ROOT="$(
    PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - "$CONFIG_SOURCE_ENV" <<'PY'
import sys
from quwoquan_ops.cli.lib.output_paths import deployment_package_root

print(deployment_package_root(sys.argv[1]) / "runtime-shared")
PY
  )"
else
  LOCAL_GAMMA_RUNTIME_SHARED_ROOT="$RUNTIME_CANDIDATE_ROOT/packages/runtime-shared"
fi
LOCAL_GAMMA_CADDYFILE="${LOCAL_GAMMA_RUNTIME_SHARED_ROOT}/Caddyfile"
LOCAL_GAMMA_LIVEKIT_CONFIG_FILE="${LOCAL_GAMMA_RUNTIME_SHARED_ROOT}/livekit.yaml"
LOCAL_GAMMA_OBJECT_STORAGE_LIFECYCLE_FILE="${LOCAL_GAMMA_RUNTIME_SHARED_ROOT}/object-storage-lifecycle.json"
if [[ "$EARLY_BUILD_ONLY" == "1" ]]; then
  default_legal_static_root="$(PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - "$CONFIG_SOURCE_ENV" <<'PY'
import sys
from quwoquan_ops.cli.lib.output_paths import legal_static_deployment_package_dir

print(legal_static_deployment_package_dir(sys.argv[1]) / "current" / "public")
PY
)"
else
  default_legal_static_root="$RUNTIME_CANDIDATE_ROOT/packages/legal-static/current/public"
fi
LOCAL_GAMMA_LEGAL_STATIC_ROOT="${LOCAL_GAMMA_LEGAL_STATIC_ROOT:-$default_legal_static_root}"
# gamma-proxy 把 /srv/web 挂成 immutable 公网 Web 包，并把内容摘要写进响应头。
# 该包由 `stackctl package --kind web` 产出、`current` 指向唯一激活版本，
# 因此 root 与 digest 必须一起从同一次读取派生：只绑其一会让代理端的证据头
# 与实际挂载的包脱钩。
if [[ -z "${LOCAL_GAMMA_PUBLIC_WEB_ROOT:-}" || -z "${QWQ_PUBLIC_WEB_CONTENT_DIGEST:-}" ]]; then
  public_web_binding="$(PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - "$QWQ_LOCAL_RELEASE_TARGET" "$CONFIG_SOURCE_ENV" "$ROOT" <<'PY'
import sys
from pathlib import Path

from quwoquan_ops.cli.lib.local_release_web_hosting import (
    materialize_local_release_web_hosting,
)

# hosting 根 = immutable 包 + 物化后的 runtime-config trust/package（配置外置，
# Caddy 从 /srv/web serve 这两个文件，包本体按契约不携带）。
hosting_root, digest = materialize_local_release_web_hosting(
    repo_root=Path(sys.argv[3]),
    environment=sys.argv[2],
    target=sys.argv[1],
)
print(hosting_root.resolve())
print(digest)
PY
)" || {
    echo "[local-release] FAIL: immutable public Web package is unavailable; run stackctl package --env ${CONFIG_SOURCE_ENV} --kind web" >&2
    exit 1
  }
  LOCAL_GAMMA_PUBLIC_WEB_ROOT="${LOCAL_GAMMA_PUBLIC_WEB_ROOT:-$(sed -n 1p <<<"$public_web_binding")}"
  QWQ_PUBLIC_WEB_CONTENT_DIGEST="${QWQ_PUBLIC_WEB_CONTENT_DIGEST:-$(sed -n 2p <<<"$public_web_binding")}"
fi
LOCAL_GAMMA_READY_INDEX_STREAM="${LOCAL_GAMMA_READY_INDEX_STREAM:-reliabletask:chat:avatar:ready:${LOCAL_GAMMA_READY_INDEX_SUFFIX}}"
LOCAL_GAMMA_READY_INDEX_GROUP="${LOCAL_GAMMA_READY_INDEX_GROUP:-chat.group_avatar_worker.${LOCAL_GAMMA_READY_INDEX_SUFFIX}}"
LOCAL_GAMMA_READY_INDEX_QUEUE="${LOCAL_GAMMA_READY_INDEX_QUEUE:-reliabletask.chat.avatar}"
export \
  STAGE \
  LOCAL_GAMMA_APP_ENV \
  CONFIG_SOURCE_ENV \
  LOCAL_GAMMA_READY_INDEX_STREAM \
  LOCAL_GAMMA_READY_INDEX_GROUP \
  LOCAL_GAMMA_READY_INDEX_QUEUE \
  LOCAL_GAMMA_CADDY_DATA_VOLUME \
  LOCAL_GAMMA_CADDY_CONFIG_VOLUME \
  LOCAL_GAMMA_COMPOSE_PROJECT_NAME \
  QWQ_PUBLIC_TLS_CERT_FILE \
  QWQ_PUBLIC_TLS_KEY_FILE \
  QWQ_PUBLIC_API_HOST \
  QWQ_PUBLIC_WEB_HOST \
  QWQ_PUBLIC_RTC_HOST \
  QWQ_PUBLIC_OPS_HOST \
  QWQ_PUBLIC_CDN_HOST \
  QWQ_PUBLIC_UPLOAD_HOST \
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
  LOCAL_GAMMA_PUBLIC_WEB_ROOT \
  QWQ_PUBLIC_WEB_CONTENT_DIGEST
export QWQ_LOCAL_RELEASE_ENV QWQ_LOCAL_RELEASE_TARGET

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
export LOCAL_GAMMA_GO_BASE_IMAGE="${LOCAL_GAMMA_GO_BASE_IMAGE:?LOCAL_GAMMA_GO_BASE_IMAGE is required}"
export LOCAL_GAMMA_ALPINE_BASE_IMAGE="${LOCAL_GAMMA_ALPINE_BASE_IMAGE:?LOCAL_GAMMA_ALPINE_BASE_IMAGE is required}"
export LOCAL_GAMMA_PYTHON_BASE_IMAGE="${LOCAL_GAMMA_PYTHON_BASE_IMAGE:-$(library_image python:3.11-slim)}"

validate_local_gamma_image_composition() {
  local expected_version="${LOCAL_GAMMA_IMAGE_VERSION:-}"
  local service=""
  local service_key=""
  local image_key=""
  local image_ref=""
  local -a composition_args=("$expected_version")
  while IFS= read -r service; do
    service_key="$(printf '%s' "$service" | tr '[:lower:]-' '[:upper:]_')"
    image_key="LOCAL_GAMMA_${service_key}_IMAGE"
    image_ref="${!image_key:-}"
    if [[ -z "$image_ref" ]]; then
      echo "[local-release] GATE_BLOCK: ${image_key} is required from canonical image composition" >&2
      return 2
    fi
    export "$image_key"
    composition_args+=("$service" "$image_ref")
  done < <(first_party_image_owners)
  PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - "${composition_args[@]}" <<'PY'
import sys

from quwoquan_ops.cli.lib.immutable_image_composition import immutable_image_digest

expected = sys.argv[1]
bindings = dict(zip(sys.argv[2::2], sys.argv[3::2], strict=True))
actual = immutable_image_digest(bindings)
if expected != actual:
    raise SystemExit(
        "[local-release] GATE_BLOCK: image composition version does not match exact refs"
    )
PY
  IMAGE_VERSION="$expected_version"
  export LOCAL_GAMMA_IMAGE_VERSION IMAGE_VERSION
}

skip_build=0
skip_up=0
build_only=0
build_services_csv=""
formal_release=0
formal_release_teardown=0
purge_rebuildable_state=0
print_env=0
down=0
tunnel_pid_file="${LOCAL_GAMMA_PROCESS_ROOT}/colima-tunnels.pids"
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
  local ssh_config="${QWQ_DEPLOY_WORK_ROOT}/${QWQ_LOCAL_RELEASE_TARGET}/runtime/colima-ssh-config"
  local port_variable=""
  local port=""
  local cancelled_ports=" "
  while IFS= read -r port_variable; do
    [[ "$port_variable" == LOCAL_GAMMA_*_PORT ]] || continue
    port="${!port_variable:-}"
    [[ -n "$port" ]] || continue
    [[ "$cancelled_ports" != *" $port "* ]] || continue
    if [[ -f "$ssh_config" ]]; then
      ssh -F "$ssh_config" -O cancel \
        -L "127.0.0.1:${port}:127.0.0.1:${port}" \
        colima >/dev/null 2>&1 || true
    fi
    cancelled_ports="${cancelled_ports}${port} "
  done < <(compgen -A variable LOCAL_GAMMA_ | sort)
  [[ -f "$tunnel_pid_file" ]] || return 0
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
    for container_name in "${LOCAL_GAMMA_RESOURCE_PREFIX}_${base_name}_1" "${LOCAL_GAMMA_RESOURCE_PREFIX}-${base_name}-1"; do
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
    for container_name in "${LOCAL_GAMMA_RESOURCE_PREFIX}_${base_name}_1" "${LOCAL_GAMMA_RESOURCE_PREFIX}-${base_name}-1"; do
      docker rm -f "$container_name" >/dev/null 2>&1 || true
      if command -v podman >/dev/null 2>&1; then
        podman rm -f "$container_name" >/dev/null 2>&1 || true
      fi
    done
  done
  if command -v podman >/dev/null 2>&1; then
    podman pod rm -f "$LOCAL_GAMMA_RESOURCE_PREFIX" >/dev/null 2>&1 || true
    podman pod rm -f "${LOCAL_GAMMA_RESOURCE_PREFIX}_default" >/dev/null 2>&1 || true
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

capture_content_startup_health_failure() {
  local evidence_path="${QWQ_RUN_ROOT:?QWQ_RUN_ROOT is required}/startup-health-failure.json"
  if [[ -e "$evidence_path" ]]; then
    echo "[local-gamma] startup health failure evidence already exists: ${evidence_path}" >&2
    return 1
  fi
  start_colima_tunnels_if_needed || true
  if PYTHONDONTWRITEBYTECODE=1 python3 -B \
    "$ROOT/quwoquan_ops/cli/lib/startup_health_failure_evidence.py" \
    --target "$QWQ_LOCAL_RELEASE_TARGET" \
    --candidate-digest "${QWQ_RELEASE_CANDIDATE_DIGEST:?candidate digest is required}" \
    --service content-service \
    --url "http://127.0.0.1:${LOCAL_GAMMA_CONTENT_PORT:?content port is required}/healthz" \
    --output "$evidence_path"; then
    echo "[local-gamma] captured managed content-service startup health failure: ${evidence_path}" >&2
    return 0
  fi
  echo "[local-gamma] content-service startup health failure evidence unavailable" >&2
  return 1
}

start_colima_tunnels_if_needed() {
  command -v colima >/dev/null 2>&1 || return 0
  command -v ssh >/dev/null 2>&1 || return 0
  [[ "$(docker context show 2>/dev/null || true)" == "colima" ]] || return 0

  local http_port="${LOCAL_GAMMA_HTTP_PORT:-19000}"
  local product_ops_port="${LOCAL_GAMMA_PRODUCT_OPS_PORT:-19010}"
  local media_edge_port="${LOCAL_GAMMA_MEDIA_EDGE_PORT:-19100}"
  # Direct service health probes (stackctl up + ship content-import readiness)
  # need Colima tunnels; otherwise host curl to 127.0.0.1:<service-port> fails.
  local user_port="${LOCAL_GAMMA_USER_PORT:-19210}"
  local product_ops_service_port="${LOCAL_GAMMA_PRODUCT_OPS_SERVICE_PORT:-19250}"
  local content_port="${LOCAL_GAMMA_CONTENT_PORT:-19220}"
  local entity_port="${LOCAL_GAMMA_ENTITY_PORT:-19290}"
  local recommendation_port="${LOCAL_GAMMA_REC_MODEL_PORT:-19240}"
  local search_port="${LOCAL_GAMMA_SEARCH_PORT:-19280}"
  # Data CLI ship import uses host-side Postgres/Mongo/Redis/ES topology ports.
  local postgres_port="${LOCAL_GAMMA_POSTGRES_PORT:-19400}"
  local mongo_port="${LOCAL_GAMMA_MONGO_PORT:-19410}"
  local redis_port="${LOCAL_GAMMA_REDIS_PORT:-19420}"
  local elasticsearch_port="${LOCAL_GAMMA_ES_PORT:-${QWQ_COMPOSE_ELASTICSEARCH_PORT:-19430}}"
  local ssh_config="${QWQ_DEPLOY_WORK_ROOT}/${QWQ_LOCAL_RELEASE_TARGET}/runtime/colima-ssh-config"
  mkdir -p \
    "${LOCAL_GAMMA_PROCESS_ROOT}" \
    "${LOCAL_GAMMA_RUNTIME_LOG_ROOT}" \
    "${LOCAL_GAMMA_MODEL_CACHE_ROOT}" \
    "${LOCAL_GAMMA_LEGAL_STATIC_ROOT}" \
    "$(dirname "$ssh_config")"
  stop_colima_tunnels
  colima ssh-config > "$ssh_config"
  : > "$tunnel_pid_file"
  for port in \
    "$http_port" \
    "$product_ops_port" \
    "$media_edge_port" \
    "$user_port" \
    "$product_ops_service_port" \
    "$content_port" \
    "$entity_port" \
    "$recommendation_port" \
    "$search_port" \
    "$postgres_port" \
    "$mongo_port" \
    "$redis_port" \
    "$elasticsearch_port"
  do
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
  --formal-release
                 Reuse exact prebuilt candidate images and preserve the running data plane.
  --formal-release-teardown
                 Stop only the candidate-scoped Compose project; never repair or wipe.
  --purge-rebuildable-state
                 With --down, delete only this receipt-bound Compose project's volumes.
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
    --formal-release) formal_release=1; shift ;;
    --formal-release-teardown) formal_release_teardown=1; shift ;;
    --purge-rebuildable-state) purge_rebuildable_state=1; shift ;;
    --print-env) print_env=1; shift ;;
    --down) down=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ "$formal_release_teardown" == "1" && "$down" != "1" ]]; then
  echo "[local-release] GATE_BLOCK: --formal-release-teardown requires --down" >&2
  exit 2
fi
if [[ "$purge_rebuildable_state" == "1" && "$down" != "1" ]]; then
  echo "[local-release] GATE_BLOCK: --purge-rebuildable-state requires --down" >&2
  exit 2
fi
if [[ "$purge_rebuildable_state" == "1" && "$formal_release_teardown" == "1" ]]; then
  echo "[local-release] GATE_BLOCK: formal teardown cannot purge rebuildable state" >&2
  exit 2
fi

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
if [[ "$formal_release" == "1" ]]; then
  if [[ "$skip_build" != "1" || "$build_only" == "1" || "$down" == "1" ]]; then
    echo "[local-gamma] GATE_BLOCK: --formal-release requires --skip-build and cannot build/down" >&2
    exit 2
  fi
  FORCE_CLEAN_RECREATE=0
  PRESERVE_POSTGRES_VOLUME=1
fi
if [[ "$print_env" != "1" ]]; then
  validate_local_gamma_image_composition || exit $?
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
  local packaged_configuration_digest
  packaged_configuration_digest="$(
    PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - "$CONFIG_SOURCE_ENV" "$QWQ_LOCAL_RELEASE_TARGET" <<'PY'
import sys

from quwoquan_ops.cli.lib.immutable_configuration_composition import (
    packaged_configuration_digest,
)

print(packaged_configuration_digest(sys.argv[1], target=sys.argv[2]))
PY
  )" || return 1
  if [[ "$packaged_configuration_digest" != "$CONFIG_VERSION" ]]; then
    echo "[local-release] GATE_BLOCK: LOCAL_GAMMA_CONFIG_VERSION does not match the packaged runtime configuration" >&2
    return 1
  fi

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
    if [[ "$service" == "api-edge" ]]; then
      PYTHONDONTWRITEBYTECODE=1 python3 -B - \
        "$package_dir" "$out" \
        "${QWQ_RELEASE_CANDIDATE_DIGEST:?candidate digest is required}" \
        "$CONFIG_SOURCE_ENV" "$QWQ_LOCAL_RELEASE_TARGET" <<'PY'
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

package_dir, output_dir, candidate_digest, environment, target = sys.argv[1:6]
package_root = Path(package_dir)
output_root = Path(output_dir)
descriptor_path = package_root / "config/graphql-read-package.json"
descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
if (
    descriptor.get("schema") != "stackctl-graphql-read-registry-package"
    or descriptor.get("candidateDigest") != candidate_digest
    or descriptor.get("environment") != environment
    or descriptor.get("target") != target
):
    raise SystemExit("GraphQL registry package candidate identity mismatch")
bindings = (
    ("schemaRef", "schemaDigest", "graphql-read-schema.graphqls"),
    ("envelopeRef", "envelopeDigest", "graphql-read-registry.json"),
    (
        "trustedPublicKeysRef",
        "trustedPublicKeysDigest",
        "graphql-read-trusted-public-keys.json",
    ),
)
for ref_field, digest_field, filename in bindings:
    ref = str(descriptor.get(ref_field) or "")
    digest = str(descriptor.get(digest_field) or "")
    if Path(ref).name != filename or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise SystemExit(f"GraphQL registry package {ref_field} mismatch")
    source = package_root / "config" / filename
    encoded = source.read_bytes()
    if "sha256:" + hashlib.sha256(encoded).hexdigest() != digest:
        raise SystemExit(f"GraphQL registry package {filename} digest mismatch")
    shutil.copyfile(source, output_root / filename)
    if (output_root / filename).read_bytes() != encoded:
        raise SystemExit(f"GraphQL registry runtime copy drifted: {filename}")
PY
    fi
    if [[ "$service" == "assistant-service" ]]; then
      # 官方 Skill package publication 随服务包封装;复制进 config-root
      # 供 assistant 模块空环境自举(PrepareMigration)读取。缺失时不在
      # 此处失败:运行时自举会给出更精确的 fail-closed 指引。
      local skill_package_dir="${package_dir}/skill-packages"
      if [[ -d "$skill_package_dir" ]]; then
        # 目标路径与 config override `skill_package.asset_root =
        # /etc/qwq-config/skill-packages/official` 对齐。
        rm -rf "$out/skill-packages"
        mkdir -p "$out/skill-packages"
        cp -R "$skill_package_dir" "$out/skill-packages/official"
      fi
    fi
    local service_env_key
    service_env_key="$(printf '%s' "$service" | tr '[:lower:]-' '[:upper:]_')"
    local version_var="LOCAL_GAMMA_${service_env_key}_CONFIG_VERSION"
    export "${version_var}=${config_version}"
  }

  rm -rf "$out"
  mkdir -p "$out/quwoquan_service/runtime/reliabletask/resources"
  local service
  while IFS= read -r service; do
    copy_service_package_config "$service" || return $?
  done < <(first_party_config_package_owners)

  if [[ ! -f "$package_root/runtime-shared/module_catalog.yaml" \
     || ! -f "$package_root/runtime-shared/retention_policy.yaml" \
     || ! -f "$package_root/runtime-shared/object-storage-lifecycle.json" \
     || ! -f "$package_root/runtime-shared/livekit.yaml" \
     || ! -f "$package_root/runtime-shared/Caddyfile" ]]; then
    echo "[local-gamma] FAIL: missing runtime shared package: $package_root/runtime-shared" >&2
    return 1
  fi
  cp "$package_root/runtime-shared/module_catalog.yaml" "$out/quwoquan_service/runtime/reliabletask/resources/module_catalog.yaml"
  cp "$package_root/runtime-shared/retention_policy.yaml" "$out/quwoquan_service/runtime/reliabletask/resources/retention_policy.yaml"
}

prepare_media_root() {
  local media="${LOCAL_GAMMA_MEDIA_ROOT}"
  mkdir -p \
    "$media/media/avatar/s" \
    "$media/media/image/s" \
    "$media/media/video/s"
  local forbidden_media=""
  forbidden_media="$(
    find "$media/media" -type f \
      \( -path '*fixture*' -o -path '*test_fixtures*' -o -path '*mock*' -o -path '*seed*' \) \
      -print -quit
  )"
  if [[ -n "$forbidden_media" ]]; then
    echo "[local-gamma] GATE_BLOCK: environment media root contains fixture/mock/seed business media: $forbidden_media" >&2
    echo "[local-release] run immutable release full-sync before exposing $QWQ_LOCAL_RELEASE_TARGET media" >&2
    return 2
  fi
  echo "[local-gamma] release media root ready; Data CLI ship apply --full-sync owns public slices: $media"
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
    --target "$QWQ_LOCAL_RELEASE_TARGET"
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
    echo "[local-release] GATE_BLOCK: docker is required for $QWQ_LOCAL_RELEASE_TARGET" >&2
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
  # service-core 合并后部分逻辑服务不再有独立镜像 env;set -u 下必须用
  # 默认空展开,由调用方对空值跳过。
  case "$1" in
    service-core) printf '%s\n' "${LOCAL_GAMMA_SERVICE_CORE_IMAGE:-}" ;;
    api-edge) printf '%s\n' "${LOCAL_GAMMA_API_EDGE_IMAGE:-}" ;;
    recommendation-service) printf '%s\n' "${LOCAL_GAMMA_RECOMMENDATION_SERVICE_IMAGE:-}" ;;
    content-service) printf '%s\n' "${LOCAL_GAMMA_CONTENT_SERVICE_IMAGE:-}" ;;
    chat-service) printf '%s\n' "${LOCAL_GAMMA_CHAT_SERVICE_IMAGE:-}" ;;
    user-service) printf '%s\n' "${LOCAL_GAMMA_USER_SERVICE_IMAGE:-}" ;;
    assistant-service) printf '%s\n' "${LOCAL_GAMMA_ASSISTANT_SERVICE_IMAGE:-}" ;;
    product-ops-service) printf '%s\n' "${LOCAL_GAMMA_PRODUCT_OPS_SERVICE_IMAGE:-}" ;;
    platform-ops-service) printf '%s\n' "${LOCAL_GAMMA_PLATFORM_OPS_SERVICE_IMAGE:-}" ;;
    tag-service) printf '%s\n' "${LOCAL_GAMMA_TAG_SERVICE_IMAGE:-}" ;;
    search-service) printf '%s\n' "${LOCAL_GAMMA_SEARCH_SERVICE_IMAGE:-}" ;;
    entity-service) printf '%s\n' "${LOCAL_GAMMA_ENTITY_SERVICE_IMAGE:-}" ;;
    circle-service) printf '%s\n' "${LOCAL_GAMMA_CIRCLE_SERVICE_IMAGE:-}" ;;
    integration-service) printf '%s\n' "${LOCAL_GAMMA_INTEGRATION_SERVICE_IMAGE:-}" ;;
    notification-service) printf '%s\n' "${LOCAL_GAMMA_NOTIFICATION_SERVICE_IMAGE:-}" ;;
    realtime-gateway) printf '%s\n' "${LOCAL_GAMMA_REALTIME_GATEWAY_IMAGE:-}" ;;
    rtc-service) printf '%s\n' "${LOCAL_GAMMA_RTC_SERVICE_IMAGE:-}" ;;
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
    echo "[local-gamma] Reclaim only unused local BuildKit cache through the managed global repair after other package/UAT operations stop:" >&2
    echo "[local-gamma]   PYTHONDONTWRITEBYTECODE=1 python3 -B quwoquan_ops/cli/stackctl.py --output-format json repair --target ${QWQ_LOCAL_RELEASE_TARGET} --fix reclaim-build-cache --confirm-global-build-cache-reclaim" >&2
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
  # uses the already-validated exact image composition and only fills non-image
  # parse inputs that Compose requires without starting a process.
  local down_config_version="$CONFIG_VERSION"
  local service=""
  local service_key=""
  local version_key=""
  while IFS= read -r service; do
    service_key="$(printf '%s' "$service" | tr '[:lower:]-' '[:upper:]_')"
    version_key="LOCAL_GAMMA_${service_key}_CONFIG_VERSION"
    if [[ -z "${!version_key:-}" ]]; then
      printf -v "$version_key" '%s' "$down_config_version"
    fi
    export "$version_key"
  done < <(first_party_image_owners)
  : "${LOCAL_GAMMA_REC_POLICY_SOURCE:=down-not-used}"
  export \
    LOCAL_GAMMA_CONFIG_ROOT \
    LOCAL_GAMMA_REC_POLICY_SOURCE
  export_service_compose_environment
}

if [[ "$print_env" == "1" ]]; then
  # This is an introspection command. It must not render configuration, create
  # runtime output, touch Docker, or alter the currently running environment.
  print_defines
  exit 0
fi

if [[ "$down" == "1" ]]; then
  if [[ "${QWQ_PREPARED_ATTEMPT_ONLY:-0}" == "1" ]]; then
    echo "[local-gamma] prepared attempt has no runtime resources; skipping Compose teardown"
    exit 0
  fi
  stop_colima_tunnels
  prepare_down_compose_environment
  down_args=(down)
  if [[ "$purge_rebuildable_state" == "1" ]]; then
    down_args+=(--volumes --remove-orphans)
  fi
  docker compose -p "$LOCAL_GAMMA_COMPOSE_PROJECT_NAME" "${COMPOSE_FILE_ARGS[@]}" "${down_args[@]}"
  if [[ "$formal_release_teardown" != "1" ]]; then
    cleanup_stale_named_gamma_containers
  fi
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
# OCI build-only and prepare-only paths must not mutate the runtime startup
# attempt receipt. Only a real compose/podman up owns prepared/partial/running.
if [[ "$build_only" != "1" && "$skip_up" != "1" ]]; then
  if [[ -f "${LOCAL_GAMMA_PROCESS_ROOT}/startup_attempt.json" ]]; then
    leftover_status="$(
      PYTHONDONTWRITEBYTECODE=1 python3 - "${LOCAL_GAMMA_PROCESS_ROOT}/startup_attempt.json" <<'PY'
import json
import sys
payload = json.loads(open(sys.argv[1], encoding="utf-8").read())
print(str(payload.get("status") or "").strip())
PY
    )"
    if [[ "$leftover_status" != "stopped" && -n "$leftover_status" ]]; then
      echo "[local-gamma] GATE_BLOCK: leftover startup attempt status=${leftover_status}; run stackctl down --target ${QWQ_LOCAL_RELEASE_TARGET} before retrying." >&2
      exit 2
    fi
  fi
  write_startup_attempt prepared
  STARTUP_ATTEMPT_PREPARED=1
fi

if [[ "$skip_up" == "1" ]]; then
  echo "[local-gamma] prepared artifacts only"
  echo "[local-release] configurationDigest=$CONFIG_VERSION imageTransportTag=$IMAGE_VERSION"
  exit 0
fi

podman_compose=0
export_service_compose_environment
if docker --version 2>/dev/null | grep -qi 'podman' && command -v podman-compose >/dev/null 2>&1; then
  echo "[local-release] GATE_BLOCK: the retired manual Podman compatibility runtime is forbidden; use canonical Docker Compose through stackctl" >&2
  exit 2
fi
compose_cmd=(docker compose -p "$LOCAL_GAMMA_COMPOSE_PROJECT_NAME" "${COMPOSE_FILE_ARGS[@]}")
# candidate topology 投影后 core 逻辑服务合并为 service-core；显式服务名单必须
# 映射到当前 compose 拓扑的真实服务名，否则 docker compose 对任一未知服务名
# 整体拒绝执行（no such service）。core 模块集合以
# quwoquan_ops.cli.lib.service_core_composition 为唯一真相源。
SERVICE_CORE_MODULE_NAMES="$(
  PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from quwoquan_ops.cli.lib.service_core_composition import SERVICE_CORE_MODULE_SET

print("\n".join(sorted(SERVICE_CORE_MODULE_SET)))
PY
)"
AVAILABLE_COMPOSE_SERVICES="$("${compose_cmd[@]}" config --services 2>/dev/null || true)"

project_first_party_service_selection() {
  # 入参：逻辑服务名列表；输出：当前拓扑下的真实服务名（core 模块在投影
  # 形态映射为 service-core，去重保序）。不存在且不可映射的名字原样保留，
  # 交由 compose 显式报错，避免静默吞掉真实配置缺陷。
  local requested=""
  local resolved=""
  local emitted=" "
  for requested in "$@"; do
    resolved="$requested"
    if [[ -n "$AVAILABLE_COMPOSE_SERVICES" ]] \
      && ! grep -qx "$requested" <<<"$AVAILABLE_COMPOSE_SERVICES" \
      && grep -qx "$requested" <<<"$SERVICE_CORE_MODULE_NAMES" \
      && grep -qx "service-core" <<<"$AVAILABLE_COMPOSE_SERVICES"; then
      resolved="service-core"
    fi
    if [[ "$emitted" == *" $resolved "* ]]; then
      continue
    fi
    emitted="${emitted}${resolved} "
    printf '%s\n' "$resolved"
  done
}
compose_up_args=(up -d --remove-orphans)
if [[ "$skip_build" == "1" ]]; then
  compose_up_args+=(--no-build)
fi
if [[ "$formal_release" == "1" && "$podman_compose" == "1" ]]; then
  echo "[local-gamma] GATE_BLOCK: formal release forbids the destructive podman compatibility path" >&2
  exit 2
fi
if [[ "$podman_compose" == "1" && "$WORKLOAD" != "full" ]]; then
  echo "[local-gamma] GATE_BLOCK: bounded content workloads require canonical Docker Compose service slicing" >&2
  exit 2
fi
if [[ "$formal_release" == "1" ]]; then
  compose_up_args=(up -d --no-build)
fi
if [[ "$WORKLOAD" == "content-release" || "$WORKLOAD" == "content-commercial" ]]; then
  # Start only the canonical import/public-read role set. Compose adds the
  # declared Mongo, Redis, Postgres, object-storage and bounded Search
  # Elasticsearch dependencies; unrelated full-workload services and their
  # Providers remain outside this diagnostic runtime. 名单按逻辑服务表达，经投影映射得到当前
  # 拓扑（dev 每服务 / candidate service-core 合并）的真实服务名。
  content_slice_up_services=(
    recommendation-service
    content-service
    user-service
    entity-service
    search-service
  )
  if [[ "$WORKLOAD" == "content-commercial" ]]; then
    content_slice_up_services+=(product-ops-service)
  fi
  content_slice_up_services+=(api-edge gamma-proxy)
  while IFS= read -r projected_up_service; do
    [[ -n "$projected_up_service" ]] || continue
    compose_up_args+=("$projected_up_service")
  done < <(project_first_party_service_selection "${content_slice_up_services[@]}")
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
compose_project="${LOCAL_GAMMA_COMPOSE_PROJECT_NAME:?LOCAL_GAMMA_COMPOSE_PROJECT_NAME is required}"
container_name=""
for candidate in "${compose_project}-mongodb-1" "${compose_project}_mongodb_1"; do
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
  api-edge
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
if [[ "$PRODUCT_OPS_REQUIRED" != "1" ]]; then
  filtered_build_services=()
  for service_name in "${compose_build_services[@]}"; do
    [[ "$service_name" == "product-ops-service" ]] || filtered_build_services+=("$service_name")
  done
  compose_build_services=("${filtered_build_services[@]}")
fi
if [[ "$WORKLOAD" == "content-release" || "$WORKLOAD" == "content-commercial" ]]; then
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
# 名单以逻辑服务表达；candidate 投影拓扑中 core 模块必须映射为 service-core，
# 否则 compose build / 镜像校验对未知服务名整体失败（no such service）。
projected_build_services=()
while IFS= read -r projected_build_service; do
  [[ -n "$projected_build_service" ]] || continue
  projected_build_services+=("$projected_build_service")
done < <(project_first_party_service_selection "${compose_build_services[@]}")
compose_build_services=("${projected_build_services[@]}")

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
write_startup_attempt partial
STARTUP_ATTEMPT_PARTIAL=1
export LOCAL_GAMMA_CONFIG_VERSION="$CONFIG_VERSION"
export LOCAL_GAMMA_IMAGE_VERSION="$IMAGE_VERSION"
export LOCAL_GAMMA_APP_ENV
export LOCAL_GAMMA_READY_INDEX_STREAM
export LOCAL_GAMMA_READY_INDEX_GROUP
export LOCAL_GAMMA_READY_INDEX_QUEUE
if [[ "$podman_compose" == "1" ]]; then
  echo "[local-gamma] startup mode: podman-manual"
  # The manual Podman path historically reused quwoquan_service_* resources
  # for every environment. Keep service network aliases stable, but rewrite
  # every owned container/network/volume argument into the target's Compose
  # namespace before invoking Podman.
  podman() {
    local -a isolated_args=()
    local value=""
    for value in "$@"; do
      case "$value" in
        quwoquan_service_local-gamma-*)
          value="${LOCAL_GAMMA_RESOURCE_PREFIX}_local-${QWQ_LOCAL_RELEASE_ENV}-${value#quwoquan_service_local-gamma-}"
          ;;
        quwoquan_service_*)
          value="${LOCAL_GAMMA_RESOURCE_PREFIX}_${value#quwoquan_service_}"
          ;;
      esac
      isolated_args+=("$value")
    done
    command podman "${isolated_args[@]}"
  }
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

  wait_healthy quwoquan_service_postgres_1
  wait_running quwoquan_service_mongodb_1
  sleep 5
  wait_healthy quwoquan_service_redis_1

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

  if [[ "$PRODUCT_OPS_REQUIRED" == "1" ]]; then
    podman run --pull=never --name quwoquan_service_product-ops-service_1 -d \
      --net "$network_name" --network-alias product-ops-service \
      -e SERVICE_NAME=product-ops-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
      -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
      -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e PRODUCT_OPS_SERVICE_ADDR=:18086 \
      -e MONGO_URI=mongodb://mongodb:27017 \
      -e POSTGRES_DSN='postgres://quwoquan:quwoquan@postgres:5432/quwoquan?sslmode=disable' \
      -e PRODUCT_OPS_REDIS_REC_ADDR=redis:6379 -e PRODUCT_OPS_REDIS_GENERAL_ADDR=redis:6379 \
      -e PRODUCT_OPS_ELASTICSEARCH_ENDPOINT \
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
    echo "[local-gamma] workload does not require product-ops; skipping it."
  fi

  podman run --pull=never --name quwoquan_service_platform-ops-service_1 -d \
    --net "$network_name" --network-alias platform-ops-service \
    -e SERVICE_NAME=platform-ops-service -e APP_ENV="$LOCAL_GAMMA_APP_ENV" \
    -e CONFIG_ROOT=/etc/qwq-config -e CONFIG_VERSION="$CONFIG_VERSION" \
    -e IMAGE_VERSION="$LOCAL_GAMMA_IMAGE_VERSION" -e PLATFORM_OPS_SERVICE_ADDR=:18088 \
    -e PLATFORM_OPS_POSTGRES_DSN='postgres://quwoquan:quwoquan@postgres:5432/quwoquan?sslmode=disable' \
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
    -e CONTENT_MONGO_URI=mongodb://mongodb:27017 \
    -e CONTENT_POSTGRES_REPORT_DSN='postgres://quwoquan:quwoquan@postgres:5432/quwoquan?sslmode=disable' \
    -e CONTENT_REDIS_REC_ADDR=redis:6379 -e CONTENT_REDIS_GENERAL_ADDR=redis:6379 -e CONTENT_REDIS_REALTIME_ADDR=redis:6379 \
    -e CONTENT_OSS_ENDPOINT \
    -e CONTENT_OSS_ACCESS_KEY_ID \
    -e CONTENT_OSS_ACCESS_KEY_SECRET \
    -e CONTENT_EMBEDDING_ENDPOINT \
    -e CONTENT_EMBEDDING_API_KEY \
    -e SEARCH_ES_ENABLED=true -e SEARCH_ES_ENDPOINTS=http://elasticsearch:9200 \
    -e CONTENT_REC_MODEL_SERVICE_ENABLED=true -e CONTENT_REC_MODEL_SERVICE_URL=http://recommendation-service:8000 \
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
    -e CHAT_MONGO_URI=mongodb://mongodb:27017 -e CHAT_MONGO_DATABASE=quwoquan_chat \
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
    -e USER_POSTGRES_DSN='postgres://quwoquan:quwoquan@postgres:5432/quwoquan?sslmode=disable' \
    -e USER_MONGO_URI=mongodb://mongodb:27017 -e USER_MONGO_DATABASE=quwoquan_user \
    -e TAG_MONGO_URI=mongodb://mongodb:27017 -e TAG_MONGO_DATABASE=quwoquan_tag \
    -e USER_REDIS_GENERAL_ADDR=redis:6379 \
    -e USER_CARRIER_ONE_TAP_SUBSTITUTE_ENDPOINT \
    -e USER_FEDERATED_IDENTITY_SUBSTITUTE_ENDPOINT \
    -e ALIYUN_DYPNS_ENDPOINT \
    -e ALIYUN_DYPNS_ACCESS_KEY_ID \
    -e ALIYUN_DYPNS_ACCESS_KEY_SECRET \
    -e WECHAT_OAUTH_TOKEN_URL \
    -e WECHAT_OAUTH_USER_INFO_URL \
    -e WECHAT_OAUTH_APP_ID \
    -e WECHAT_OAUTH_APP_SECRET \
    -e ALIPAY_OAUTH_TOKEN_URL \
    -e ALIPAY_OAUTH_USER_INFO_URL \
    -e ALIPAY_OAUTH_APP_ID \
    -e ALIPAY_OAUTH_APP_PRIVATE_KEY_PEM \
    -e ALIPAY_OAUTH_PLATFORM_PUBLIC_KEY_PEM \
    -e ALIPAY_OAUTH_MERCHANT_PID \
    -e QQ_OAUTH_USER_INFO_URL \
    -e QQ_OAUTH_APP_ID \
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
    -e INTEGRATION_SMS_ENDPOINT \
    -e INTEGRATION_SMS_TOKEN \
    -e INTEGRATION_PUSH_SUBSTITUTE_ENDPOINT \
    -e INTEGRATION_LOCATION_FIXTURE_BASE_URL \
    -e OTP_CODE_REF_KEYS_JSON \
    -e INTEGRATION_SERVICE_MTLS_CA_FILE \
    -e INTEGRATION_SERVICE_MTLS_CLIENT_CERT_FILE \
    -e INTEGRATION_SERVICE_MTLS_CLIENT_KEY_FILE \
    -e INTEGRATION_PUSH_USER_SERVICE_BASE_URL \
    -e INTEGRATION_PUSH_APNS_ENVIRONMENT \
    -e INTEGRATION_PUSH_APNS_KEY_ID \
    -e INTEGRATION_PUSH_APNS_TEAM_ID \
    -e INTEGRATION_PUSH_APNS_TOPIC \
    -e INTEGRATION_PUSH_APNS_KEY_FILE \
    -e INTEGRATION_PUSH_FCM_PROJECT_ID \
    -e INTEGRATION_PUSH_FCM_SERVICE_ACCOUNT_FILE \
    -e INTEGRATION_LOCATION_BAIDU_BASE_URL \
    -e INTEGRATION_LOCATION_BAIDU_AK \
    -e AUTH_JWT_SECRET="${AUTH_JWT_SECRET:?AUTH_JWT_SECRET is required}" \
    -e AUTH_JWT_ISSUER="${AUTH_JWT_ISSUER:?AUTH_JWT_ISSUER is required}" \
    -e AUTH_JWT_AUDIENCE="${AUTH_JWT_AUDIENCE:?AUTH_JWT_AUDIENCE is required}" \
    -e AUTH_JWT_TOKEN_VERSION="${AUTH_JWT_TOKEN_VERSION:?AUTH_JWT_TOKEN_VERSION is required}" \
    -e AUTH_DEVICE_TICKET_SECRET="${AUTH_DEVICE_TICKET_SECRET:?AUTH_DEVICE_TICKET_SECRET is required}" \
    -e AUTH_DEVICE_TICKET_ISSUER="${AUTH_DEVICE_TICKET_ISSUER:?AUTH_DEVICE_TICKET_ISSUER is required}" \
    -e AUTH_DEVICE_TICKET_AUDIENCE="${AUTH_DEVICE_TICKET_AUDIENCE:?AUTH_DEVICE_TICKET_AUDIENCE is required}" \
    -e AUTH_DEVICE_TICKET_TOKEN_VERSION="${AUTH_DEVICE_TICKET_TOKEN_VERSION:?AUTH_DEVICE_TICKET_TOKEN_VERSION is required}" \
    -v "${LOCAL_GAMMA_CONFIG_ROOT}:/etc/qwq-config:ro" \
    -v "${INTEGRATION_SERVICE_MTLS_CA_FILE}:${INTEGRATION_SERVICE_MTLS_CA_FILE}:ro" \
    -v "${INTEGRATION_SERVICE_MTLS_CLIENT_CERT_FILE}:${INTEGRATION_SERVICE_MTLS_CLIENT_CERT_FILE}:ro" \
    -v "${INTEGRATION_SERVICE_MTLS_CLIENT_KEY_FILE}:${INTEGRATION_SERVICE_MTLS_CLIENT_KEY_FILE}:ro" \
    -v "${INTEGRATION_PUSH_APNS_KEY_FILE}:${INTEGRATION_PUSH_APNS_KEY_FILE}:ro" \
    -v "${INTEGRATION_PUSH_FCM_SERVICE_ACCOUNT_FILE}:${INTEGRATION_PUSH_FCM_SERVICE_ACCOUNT_FILE}:ro" \
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
      -e ASSISTANT_REDIS_GENERAL_ADDR=redis:6379 -e ASSISTANT_REDIS_REC_ADDR=redis:6379 \
      -e ASSISTANT_MODEL_COMPLETION_URL \
      -e ASSISTANT_MODEL_API_KEY \
      -e ASSISTANT_PUBLIC_SEARCH_URL \
      -e ASSISTANT_WEATHER_GEOCODING_URL \
      -e ASSISTANT_WEATHER_FORECAST_URL \
      -e ASSISTANT_FINANCE_CHART_URL \
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
    -e SEARCH_REDIS_REC_MODE=standalone -e SEARCH_REDIS_REC_ADDR=redis:6379 \
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
    -e ENTITY_REDIS_GENERAL_ADDR=redis:6379 \
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
    -e CIRCLE_REDIS_GENERAL_ADDR=redis:6379 \
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
    -p "${LOCAL_GAMMA_HTTP_PORT:?LOCAL_GAMMA_HTTP_PORT is required}:${LOCAL_GAMMA_HTTP_PORT}" \
    -p "${LOCAL_GAMMA_PRODUCT_OPS_PORT:?LOCAL_GAMMA_PRODUCT_OPS_PORT is required}:${LOCAL_GAMMA_PRODUCT_OPS_PORT}" \
    -p "${LOCAL_GAMMA_MEDIA_EDGE_PORT:?LOCAL_GAMMA_MEDIA_EDGE_PORT is required}:${LOCAL_GAMMA_MEDIA_EDGE_PORT}" \
    -p "127.0.0.1:${LOCAL_GAMMA_ADMIN_PORT:?LOCAL_GAMMA_ADMIN_PORT is required}:2019" \
    --healthcheck-command "wget --no-check-certificate -qO- https://${QWQ_PUBLIC_API_HOST}:${LOCAL_GAMMA_HTTP_PORT}/healthz >/dev/null 2>&1" \
    --healthcheck-interval 10s --healthcheck-timeout 3s --healthcheck-start-period 5s --healthcheck-retries 10 \
    "$LOCAL_GAMMA_CADDY_IMAGE" >/dev/null
  wait_healthy quwoquan_service_gamma-proxy_1
else
  echo "[local-gamma] startup mode: compose-up"
  if [[ "$formal_release" != "1" ]]; then
    # Explicit local-development startup may recreate and repair its disposable mirror.
    "${compose_cmd[@]}" down --remove-orphans >/dev/null 2>&1 || true
    cleanup_stale_named_gamma_containers
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
  else
    echo "[local-gamma] formal release preserves images and data"
  fi
  ensure_docker_gamma_proxy_started() {
    local name=""
    local status=""
    local health=""
    local deadline=$((SECONDS + 15))
    while (( SECONDS < deadline )); do
      name="$(docker ps -aq \
        --filter "label=com.docker.compose.project=${LOCAL_GAMMA_COMPOSE_PROJECT_NAME}" \
        --filter "label=com.docker.compose.service=gamma-proxy" | head -n 1)"
      if [[ -z "$name" ]]; then
        sleep 1
        continue
      fi
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
    # that may not exist locally, so no service ever reached its readiness phase.
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
        echo "[local-gamma] FAIL: compose up exceeded ${timeout_seconds}s; transactional teardown will preserve the receipt" >&2
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
  bootstrap_experiment_policy_owner() {
    # Gamma 冷启动存在两段 readiness 环：service-core 内 Search 等待
    # ExperimentPolicyActivated；Product Ops 又通过 AccountSecurityAuthority
    # 等待 service-core 内 UserAccount。UserAccount 已声明精确内部
    # pre-admission 健康面，因此全栈 up 前先起基础设施和 service-core 进程。
    # service-core 容器 healthcheck 仅探 /healthz，可安全证明全部 module 已完成
    # Build/Bind/Start；不能等待的是会拉起依赖图的 Compose aggregate readiness。
    # 随后再起 Product Ops，经原公开 command 激活策略，最后进行 full up。
    # 禁止放宽 Product Ops 公共 admission、直写 Mongo/Redis 或注入 fixture。
    local bootstrap_services=""
    local bootstrap_service=""
    local cid=""
    local state=""
    local deadline=0
    bootstrap_services="$("${compose_cmd[@]}" config --services 2>/dev/null || true)"
    for bootstrap_service in service-core product-ops-service; do
      if [[ -z "$bootstrap_services" ]] \
        || ! grep -qx "$bootstrap_service" <<<"$bootstrap_services"; then
        echo "[local-gamma] FAIL: policy owner bootstrap requires $bootstrap_service in the compose topology" >&2
        return 1
      fi
    done
    # product-ops 构造期 fail-fast 的网络依赖闭包：Postgres/Redis/Mongo(+init)
    # 与 Elasticsearch（telemetry ILM/index 初始化重试耗尽后 exit 1）。
    # AccountSecurityAuthority 属于 readiness；它的 owner service-core 在基础
    # 设施健康后单独拉起，不能误归为降级路径。
    local -a bootstrap_infra=()
    for bootstrap_service in mongodb mongo-init postgres redis elasticsearch; do
      if grep -qx "$bootstrap_service" <<<"$bootstrap_services"; then
        bootstrap_infra+=("$bootstrap_service")
      fi
    done
    echo "[local-gamma] policy owner bootstrap: starting infrastructure (${bootstrap_infra[*]})"
    if ! "${compose_cmd[@]}" up -d --no-build "${bootstrap_infra[@]}"; then
      echo "[local-gamma] FAIL: policy owner bootstrap infrastructure up failed" >&2
      return 1
    fi
    # product-ops 需要可写 replica-set primary；等待 mongo-init one-shot 完成。
    deadline=$((SECONDS + 180))
    while true; do
      cid="$("${compose_cmd[@]}" ps -aq mongo-init 2>/dev/null | head -n 1)"
      state="$(docker inspect --format '{{.State.Status}} {{.State.ExitCode}}' "$cid" 2>/dev/null || true)"
      if [[ "$state" == "exited 0" ]]; then
        break
      fi
      if [[ "$state" == exited* ]]; then
        echo "[local-gamma] FAIL: mongo-init exited abnormally during policy owner bootstrap ($state)" >&2
        docker logs --tail 40 "$cid" >&2 || true
        return 1
      fi
      if (( SECONDS >= deadline )); then
        echo "[local-gamma] FAIL: mongo-init did not complete within the policy owner bootstrap deadline" >&2
        return 1
      fi
      sleep 2
    done
    # product-ops 进程启动即探 Postgres schema、Redis ping 与 Elasticsearch
    # telemetry 索引初始化，failure 是 fatal；必须等全部 healthy 再启动 owner。
    # Elasticsearch 冷启动在受限本地 VM 可超 8 分钟，等待期限沿用 compose up
    # 的有界超时而不是通用 180s。
    for bootstrap_service in postgres redis elasticsearch; do
      if ! grep -qx "$bootstrap_service" <<<"$bootstrap_services"; then
        continue
      fi
      if [[ "$bootstrap_service" == "elasticsearch" ]]; then
        deadline=$((SECONDS + ${LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS:?LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS is required}))
      else
        deadline=$((SECONDS + 180))
      fi
      while true; do
        cid="$("${compose_cmd[@]}" ps -q "$bootstrap_service" 2>/dev/null | head -n 1)"
        state="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" 2>/dev/null || true)"
        if [[ "$state" == "healthy" ]]; then
          break
        fi
        if (( SECONDS >= deadline )); then
          echo "[local-gamma] FAIL: $bootstrap_service did not become healthy during policy owner bootstrap (state=${state:-missing})" >&2
          return 1
        fi
        sleep 2
      done
    done
    # --no-deps 绕过会拉起 Recommendation/Search 的 Compose dependency graph；
    # 随后等待的 container health 只探 /healthz（shallow liveness），不等待
    # aggregate /readyz 或尚未激活的实验策略。这样既破环，也不会把 module
    # 构造失败误记为 Product Ops admission 的短暂竞态。
    echo "[local-gamma] policy owner bootstrap: starting service-core authority owner (--no-deps)"
    if ! "${compose_cmd[@]}" up -d --no-build --no-deps service-core; then
      echo "[local-gamma] FAIL: policy owner bootstrap could not start service-core authority owner" >&2
      return 1
    fi
    deadline=$((SECONDS + 180))
    while true; do
      # `compose ps -q` only returns running containers.  A constructor crash
      # therefore used to erase the container from this probe and turn an
      # immediate typed exit into a three-minute `state=missing` timeout.
      # Include stopped containers so the first runtime failure is preserved.
      cid="$("${compose_cmd[@]}" ps -a -q service-core 2>/dev/null | head -n 1)"
      if [[ -z "$cid" ]]; then
        echo "[local-gamma] FAIL: service-core container is missing during policy owner bootstrap" >&2
        "${compose_cmd[@]}" logs --tail 80 service-core >&2 || true
        return 1
      fi
      state="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing-healthcheck{{end}} {{.State.Status}}' "$cid" 2>/dev/null || true)"
      if [[ "$state" == "healthy running" ]]; then
        break
      fi
      if [[ "$state" == *" exited" || "$state" == *" dead" ]]; then
        echo "[local-gamma] FAIL: service-core exited before shallow health during policy owner bootstrap (state=${state:-missing})" >&2
        "${compose_cmd[@]}" logs --tail 80 service-core >&2 || true
        return 1
      fi
      if (( SECONDS >= deadline )); then
        echo "[local-gamma] FAIL: service-core did not reach shallow health during policy owner bootstrap (state=${state:-missing})" >&2
        "${compose_cmd[@]}" logs --tail 80 service-core >&2 || true
        return 1
      fi
      sleep 2
    done
    # --no-deps：candidate 拓扑把 product-ops 依赖投影为 service-core healthy，
    # 但 bootstrap 此时只需已完成 Build/Bind/Start 的 UserAccount 内部健康面。operator 凭据的公开
    # command 不经过 AccountSecurityAuthority，但仍完整经过验签、scope、
    # idempotency 与 owner handler。
    echo "[local-gamma] policy owner bootstrap: starting product-ops-service (--no-deps)"
    if ! "${compose_cmd[@]}" up -d --no-build --no-deps product-ops-service; then
      echo "[local-gamma] FAIL: policy owner bootstrap could not start product-ops-service" >&2
      return 1
    fi
    local bootstrap_receipt="${QWQ_RUN_ROOT}/attachments/experiment-policy-owner-bootstrap.json"
    mkdir -p "$(dirname "$bootstrap_receipt")"
    if ! QWQ_BOOTSTRAP_RECEIPT_PATH="$bootstrap_receipt" \
      PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import json
import os
from pathlib import Path

from quwoquan_ops.cli.lib.experiment_policy_activation import (
    activate_search_experiment_policy_via_published_port,
)

receipt = activate_search_experiment_policy_via_published_port(
    environment=os.environ["QWQ_LOCAL_RELEASE_ENV"],
    target=os.environ["QWQ_LOCAL_RELEASE_TARGET"],
)
path = Path(os.environ["QWQ_BOOTSTRAP_RECEIPT_PATH"])
path.write_text(
    json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(
    "[local-gamma] policy owner bootstrap: "
    f"{receipt['operation']} (receipt={path})"
)
PY
    then
      echo "[local-gamma] FAIL: policy owner bootstrap activation failed" >&2
      "${compose_cmd[@]}" logs --tail 80 product-ops-service >&2 || true
      return 1
    fi
  }
  if [[ "$PRODUCT_OPS_REQUIRED" == "1" ]]; then
    if ! bootstrap_experiment_policy_owner; then
      echo "[local-gamma] FAIL: experiment policy owner bootstrap failed; a cold full-stack startup would deadlock on the authored policy" >&2
      exit 1
    fi
  fi
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

# docker compose 分支不会逐项 wait_healthy；在宣告就绪前用主机侧探测避免 release-consumer/device-UAT 撞到端口未监听。
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
      "https://${host}:${port}/media/video/s/video-primary-0001/post/video-content-0001/v1/source.mp4"
  )" || return 1
  status="${probe%%|*}"
  content_type="${probe#*|}"
  [[ "$status" == "206" && "$content_type" == video/* ]]
}

gamma_product_ops_ready() {
  if [[ "$PRODUCT_OPS_REQUIRED" != "1" ]]; then
    return 0
  fi
  curl -fsS "${PRODUCT_OPS_BASE_URL%/}/healthz" >/dev/null 2>&1
}

gamma_platform_ops_ready() {
  # platform-ops belongs to the full operational control-plane. The
  # content-release slice deliberately has no operator OIDC material and its
  # acceptance scope does not include that service.
  if [[ "$WORKLOAD" == "content-release" || "$WORKLOAD" == "content-commercial" ]]; then
    return 0
  fi
  # 环境编排的「就绪等待」取深层 /readyz：容器 healthcheck 只回答浅层存活
  # （避免 depends_on 级联阻塞），用它当就绪门会让 Postgres/Redis/事实树未连上
  # 时后续 UAT 步骤照样开跑。
  curl -fsS "http://127.0.0.1:${LOCAL_GAMMA_PLATFORM_OPS_SERVICE_PORT:-19260}/readyz" >/dev/null 2>&1
}

gamma_bounded_search_ready() {
  if [[ "$WORKLOAD" != "content-release" && "$WORKLOAD" != "content-commercial" ]]; then
    return 0
  fi
  curl -fsS -H "Host: search-service" \
    "http://127.0.0.1:${LOCAL_GAMMA_SEARCH_PORT:-19280}/healthz" >/dev/null 2>&1
}

gamma_full_workload_dependencies_ready() {
  if [[ "$WORKLOAD" == "content-release" || "$WORKLOAD" == "content-commercial" ]]; then
    return 0
  fi
  # service-core 共享端口经 VirtualHTTPRouter 按 Host 头分流，必须携带模块主机名。
  curl -fsS -H "Host: integration-service" "http://127.0.0.1:${LOCAL_GAMMA_INTEGRATION_PORT:-19310}/healthz" >/dev/null 2>&1 \
    && curl -fsS -H "Host: notification-service" "http://127.0.0.1:${LOCAL_GAMMA_NOTIFICATION_PORT:-19320}/healthz" >/dev/null 2>&1 \
    && curl -fsS -H "Host: tag-service" "http://127.0.0.1:${LOCAL_GAMMA_TAG_PORT:-19270}/healthz" >/dev/null 2>&1
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
      && { [[ "$PRODUCT_OPS_REQUIRED" != "1" ]] || curl -fsS "http://127.0.0.1:${po_port}/healthz" >/dev/null 2>&1; } \
      && gamma_platform_ops_ready \
      && curl -fsS -H "Host: user-service" "http://127.0.0.1:${user_port}/healthz" >/dev/null 2>&1 \
      && gamma_bounded_search_ready \
      && gamma_full_workload_dependencies_ready
    then
      return 0
    fi
    sleep 2
  done
  echo "[local-gamma] FAIL: host cannot reach required Remote service health probes within ${HOST_READY_TIMEOUT_SECONDS}s" >&2
  probe_one() {
    local name="$1"
    shift
    local body=""
    if body="$("$@" 2>/dev/null)"; then
      echo "[local-gamma] probe ${name}: OK ${body}" >&2
      return 0
    fi
    echo "[local-gamma] probe ${name}: FAIL" >&2
    return 1
  }
  probe_one gateway curl -fsS "https://${gw_host}:${gw_port}/healthz" || true
  if [[ "$PRODUCT_OPS_REQUIRED" == "1" ]]; then
    probe_one product-ops-public curl -fsS "${PRODUCT_OPS_BASE_URL%/}/healthz" || true
  else
    echo "[local-gamma] probe product-ops-public: SKIP" >&2
  fi
  probe_one media-image curl -fsS "https://${media_host}:${media_edge_port}/healthz" || true
  probe_one media-video curl -fsS "https://${video_host}:${media_edge_port}/healthz" || true
  if [[ "$PRODUCT_OPS_REQUIRED" == "1" ]]; then
    probe_one product-ops-service curl -fsS "http://127.0.0.1:${po_port}/healthz" || true
  else
    echo "[local-gamma] probe product-ops-service: SKIP" >&2
  fi
  if [[ "$WORKLOAD" == "content-release" || "$WORKLOAD" == "content-commercial" ]]; then
    echo "[local-gamma] probe platform-ops-service: SKIP" >&2
  else
    probe_one platform-ops-service curl -fsS "http://127.0.0.1:${LOCAL_GAMMA_PLATFORM_OPS_SERVICE_PORT:-19260}/healthz" || true
  fi
  # service-core 的共享端口经 VirtualHTTPRouter 按 Host 头分流；裸 IP 直连
  # 会命中 421 misdirected_request，探测必须携带模块逻辑主机名。
  probe_one user-service curl -fsS -H "Host: user-service" "http://127.0.0.1:${user_port}/healthz" || true
  if [[ "$WORKLOAD" == "content-release" || "$WORKLOAD" == "content-commercial" ]]; then
    probe_one search-service curl -fsS -H "Host: search-service" \
      "http://127.0.0.1:${LOCAL_GAMMA_SEARCH_PORT:-19280}/healthz" || true
    echo "[local-gamma] probe integration/notification/tag: SKIP" >&2
  else
    probe_one integration-service curl -fsS -H "Host: integration-service" "http://127.0.0.1:${integration_port}/healthz" || true
    probe_one notification-service curl -fsS -H "Host: notification-service" "http://127.0.0.1:${notification_port}/healthz" || true
    probe_one tag-service curl -fsS -H "Host: tag-service" "http://127.0.0.1:${tag_port}/healthz" || true
  fi
  docker compose -p "$LOCAL_GAMMA_COMPOSE_PROJECT_NAME" "${COMPOSE_FILE_ARGS[@]}" ps >&2 || true
  # Dump failed-first-party services before transactional teardown so deep
  # /readyz and crash exits remain inspectable in the up receipt.
  # candidate topology 投影后一方服务收敛为 service-core;一次性多服务名单会因
  # 任一未知服务名让 `docker compose logs` 整体拒绝执行并丢掉全部证据,
  # 因此以 config --services 为真相源逐服务 dump。
  diagnostic_available_services="$(docker compose -p "$LOCAL_GAMMA_COMPOSE_PROJECT_NAME" "${COMPOSE_FILE_ARGS[@]}" config --services 2>/dev/null || true)"
  for diagnostic_log_service in \
    gamma-proxy service-core api-edge content-service entity-service product-ops-service \
    platform-ops-service user-service integration-service notification-service search-service \
    assistant-service chat-service recommendation-service realtime-gateway rtc-service tag-service; do
    if [[ -n "$diagnostic_available_services" ]] \
      && ! grep -qx "$diagnostic_log_service" <<<"$diagnostic_available_services"; then
      continue
    fi
    docker compose -p "$LOCAL_GAMMA_COMPOSE_PROJECT_NAME" "${COMPOSE_FILE_ARGS[@]}" logs --tail 120 "$diagnostic_log_service" >&2 || true
  done
  for svc in service-core recommendation-service realtime-gateway rtc-service search-service assistant-service user-service integration-service notification-service tag-service platform-ops-service product-ops-service; do
    cname=$(docker compose -p "$LOCAL_GAMMA_COMPOSE_PROJECT_NAME" "${COMPOSE_FILE_ARGS[@]}" ps -q "$svc" 2>/dev/null | head -1 || true)
    if [[ -n "$cname" ]]; then
      echo "[local-gamma] inspect Health ${svc}:" >&2
      docker inspect --format 'status={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} exit={{.State.ExitCode}}' "$cname" >&2 || true
      docker inspect --format '{{json .State.Health}}' "$cname" >&2 || true
      docker inspect --format 'networks={{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}} bindings={{json .HostConfig.PortBindings}} published={{json .NetworkSettings.Ports}}' "$cname" >&2 || true
    fi
  done
  return 1
}
wait_local_gamma_host_ready
echo "[local-gamma] FilterCatalog release is an explicit post-start release gate"





echo "[local-gamma] immutable release activation owns business data and search projections; no environment seed path is available"

write_startup_attempt running
STARTUP_ATTEMPT_RUNNING=1

echo "[local-gamma] service mode: single-stack"
echo "[local-gamma] mirror started"
echo "[local-gamma] gateway: $GATEWAY_BASE_URL"
echo "[local-gamma] product-ops: $PRODUCT_OPS_BASE_URL"
echo "[local-gamma] media-image: $MEDIA_IMAGE_BASE_URL"
echo "[local-gamma] dart defines:"
print_defines
