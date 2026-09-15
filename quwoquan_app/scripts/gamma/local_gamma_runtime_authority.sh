#!/usr/bin/env bash

# start_local_gamma_mirror.sh 的 runtime authority 辅助边界；仅由该入口 source。

prepare_runtime_security_projection() {
  # Redis ACL 材料由 deployment owner create-once；Compose 只消费 locator。
  redis_acl_projection="$(
    PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 "$QWQ_STACKCTL_PYTHON" -B - <<'PY'
import shlex
from quwoquan_ops.cli.commands.source_allocation import prepare_gamma_local_redis_acl
value = prepare_gamma_local_redis_acl()
print("export LOCAL_GAMMA_REDIS_ACL_FILE=" + shlex.quote(value["aclFile"]))
print("export LOCAL_GAMMA_REDIS_RUNTIME_PASSWORD_FILE=" + shlex.quote(str(__import__("pathlib").Path(value["aclFile"]).with_name("redis-runtime.key"))))
PY
  )" || { echo "[local-gamma] GATE_BLOCK: managed Redis ACL material unavailable" >&2; exit 2; }
  eval "$redis_acl_projection"
  export LOCAL_GAMMA_REDIS_ACL_FILE LOCAL_GAMMA_REDIS_RUNTIME_PASSWORD_FILE

  compose_cmd=(docker compose -p "$LOCAL_GAMMA_COMPOSE_PROJECT_NAME" "${COMPOSE_FILE_ARGS[@]}")
  if [[ "$EARLY_BUILD_ONLY" != "1" && "$LOCAL_RUN_ACTION" == "up" ]]; then
    provider_runtime_secret_env_file="${QWQ_PROVIDER_RUNTIME_SECRET_ENV_FILE:-}"
    if [[ "$provider_runtime_secret_env_file" != /* || ! -f "$provider_runtime_secret_env_file" || -L "$provider_runtime_secret_env_file" ]]; then
      echo "[local-release] GATE_BLOCK: protected Provider runtime env file is unavailable" >&2
      exit 2
    fi
    provider_runtime_secret_mode="$(stat -f '%Lp' "$provider_runtime_secret_env_file" 2>/dev/null || stat -c '%a' "$provider_runtime_secret_env_file" 2>/dev/null || true)"
    if [[ "$provider_runtime_secret_mode" != "600" ]]; then
      echo "[local-release] GATE_BLOCK: protected Provider runtime env file must use mode 0600" >&2
      exit 2
    fi
    compose_cmd=(docker compose --env-file "$provider_runtime_secret_env_file" -p "$LOCAL_GAMMA_COMPOSE_PROJECT_NAME" "${COMPOSE_FILE_ARGS[@]}")
  fi
  # 所有普通 runtime Redis scene 使用单独受管 principal；source admin/probe
  # 凭据仅留在 deployment owner 内存与0600材料，不进入该 Compose override。
  runtime_redis_override="${LOCAL_GAMMA_DEPLOY_RENDER_ROOT}/redis-runtime.compose.json"
  QWQ_RUNTIME_REDIS_PASSWORD="$(cat "$LOCAL_GAMMA_REDIS_RUNTIME_PASSWORD_FILE")"
  export QWQ_RUNTIME_REDIS_PASSWORD
  PYTHONDONTWRITEBYTECODE=1 python3 - "$runtime_redis_override" "${compose_cmd[@]}" <<'PY'
import json, subprocess, sys
from pathlib import Path
out, *command = sys.argv[1:]
document = json.loads(subprocess.run([*command, "config", "--format", "json"], check=True, capture_output=True, text=True).stdout)
services = {}
for name, definition in document.get("services", {}).items():
    environment = definition.get("environment") or {}
    additions = {}
    for key in environment:
        if "_REDIS_" in key and key.endswith("_ADDR"):
            prefix = key[:-5]
            additions[prefix + "_USERNAME"] = "qwq_runtime"
            additions[prefix + "_PASSWORD"] = "${QWQ_RUNTIME_REDIS_PASSWORD:?managed Redis runtime password is required}"
    # api-edge admission Redis 地址属于配置快照、密码属于 secretRef，因此 Compose
    # 模板没有可供上面 scene 扫描的 *_ADDR 键；service-core 仍须按其声明式 env
    # 契约显式注入同一 runtime principal，不能依赖不存在的模板键触发特判。
    if name == "api-edge" or name == "service-core":
        additions["API_EDGE_REDIS_USERNAME"] = "qwq_runtime"
        additions["API_EDGE_REDIS_PASSWORD"] = "${QWQ_RUNTIME_REDIS_PASSWORD:?managed Redis runtime password is required}"
    if additions:
        services[name] = {"environment": additions}
Path(out).write_text(json.dumps({"services": services}, sort_keys=True, separators=(",", ":")))
Path(out).chmod(0o600)
PY
  compose_cmd+=(-f "$runtime_redis_override")
}

prepare_service_core_runtime_authorities() {
  # User schema/runtime 身份由 source allocator 同轨创建。source owner 已完成
  # migration；service-core 只消费独立最小权限 runtime DSN。
  local user_postgres_projection=""
  if [[ "$QWQ_LOCAL_RELEASE_TARGET" == "gamma-local" ]]; then
    if ! user_postgres_projection="$(
    PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 "$QWQ_STACKCTL_PYTHON" -B - <<'PY_RUNTIME_PG'
import shlex
from quwoquan_ops.cli.commands.source_allocation import gamma_local_user_runtime_postgres_dsn
print("export QWQ_USER_RUNTIME_POSTGRES_DSN=" + shlex.quote(gamma_local_user_runtime_postgres_dsn()))
PY_RUNTIME_PG
    )"; then
      echo "[local-gamma] GATE_BLOCK: managed User runtime PostgreSQL binding unavailable" >&2
      return 1
    fi
    eval "$user_postgres_projection"
    export QWQ_USER_RUNTIME_POSTGRES_DSN
    local user_postgres_override="${LOCAL_GAMMA_DEPLOY_RENDER_ROOT}/user-postgres-runtime.compose.json"
    PYTHONDONTWRITEBYTECODE=1 python3 - "$user_postgres_override" <<'PY_RUNTIME_PG_OVERRIDE'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
path.write_text(json.dumps({"services":{"service-core":{"environment":{
"USER_POSTGRES_DSN":"${QWQ_USER_RUNTIME_POSTGRES_DSN:?managed User runtime PostgreSQL DSN is required}"
}}}}, sort_keys=True, separators=(",", ":")), encoding="utf-8")
path.chmod(0o600)
PY_RUNTIME_PG_OVERRIDE
    compose_cmd+=(-f "$user_postgres_override")
    echo "[local-gamma] User schema owner/runtime PostgreSQL binding verified before service-core"
  fi

  # Post safety 必须在 Mongo 与 init healthy 后、任何 service-core 进程前完成。
  # 外层 stackctl up 已持有 target operation lock；这里直接调用同一 canonical
  # library，不能再经会重复取锁的公开子命令，也不能先启动服务再补材料。
  local post_safety_projection=""
  if [[ "$QWQ_LOCAL_RELEASE_TARGET" == "gamma-local" ]]; then
    if ! post_safety_projection="$(
    PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 "$QWQ_STACKCTL_PYTHON" -B - <<'PY'
import shlex

from quwoquan_ops.cli.commands.post_safety_runtime import (
ensure_post_safety_runtime_for_locked_up,
)

projection = ensure_post_safety_runtime_for_locked_up("gamma-local")
for key, source in (
    ("CONTENT_POST_SAFETY_HMAC_SECRET_REF", "hmacSecretRef"),
    ("CONTENT_POST_SAFETY_RECOVERY_EVIDENCE_REF", "recoveryEvidenceRef"),
    ("CONTENT_POST_SAFETY_MATERIAL_ROOT", "containerMaterialRoot"),
    ("CONTENT_POST_SAFETY_CURRENT_BINDING_REF", "currentBindingRef"),
    ("QWQ_COMPOSE_POST_SAFETY_MATERIAL_ROOT", "hostMaterialRoot"),
    ("CONTENT_ACCOUNT_CLOSURE_SUBJECT_HMAC_SECRET", "accountSubjectHmacSecret"),
):
    print(f"export {key}={shlex.quote(projection[source])}")
PY
    )"; then
      echo "[local-gamma] GATE_BLOCK: canonical Post safety startup material/current verification failed" >&2
      return 1
    fi
    eval "$post_safety_projection"
    local post_safety_override="${LOCAL_GAMMA_DEPLOY_RENDER_ROOT}/post-safety.compose.json"
    PYTHONDONTWRITEBYTECODE=1 python3 - "$post_safety_override" <<'PY'
import json
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = {
"services": {
    "service-core": {
        # RuntimeFiles 核验实际进程 owner，不信任材料内声明。macOS bind mount 在
        # LinuxKit 内保留 host UID，因此 consumer 使用同一数值身份。
        "user": f"{os.geteuid()}:{os.getegid()}",
        "environment": {
            key: os.environ[key]
            for key in (
                "CONTENT_POST_SAFETY_HMAC_SECRET_REF",
                "CONTENT_POST_SAFETY_RECOVERY_EVIDENCE_REF",
                "CONTENT_POST_SAFETY_MATERIAL_ROOT",
                "CONTENT_POST_SAFETY_CURRENT_BINDING_REF",
                "CONTENT_ACCOUNT_CLOSURE_SUBJECT_HMAC_SECRET",
            )
        },
        "volumes": [
            {
                "type": "bind",
                "source": os.environ["QWQ_COMPOSE_POST_SAFETY_MATERIAL_ROOT"],
                "target": "/run/quwoquan/post-safety",
                "read_only": True,
            }
        ],
    }
}
}
path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
PY
    compose_cmd+=(-f "$post_safety_override")
    echo "[local-gamma] Post safety runtime current initialized/verified before service-core"
  fi
}

validate_stackctl_managed_python() {
  # stackctl 父进程已校验该绝对路径、真实目标及 owner/mode 安全边界。
  # 标准 venv 的 bin/python 是 symlink，必须保留 lexical path 才能加载 venv site-packages。
  QWQ_STACKCTL_PYTHON="${QWQ_STACKCTL_PYTHON:-}"
  if [[ "$QWQ_STACKCTL_PYTHON" != /* || ! -f "$QWQ_STACKCTL_PYTHON" || ! -x "$QWQ_STACKCTL_PYTHON" ]]; then
    echo "[local-release] GATE_BLOCK: stackctl-validated managed Python executable is required" >&2
    exit 2
  fi
  export QWQ_STACKCTL_PYTHON
}

export_post_safety_locators() {
  # Post safety 的四个 locator 与 host material root 只由 stackctl up 在完成
  # canonical current 初始化/复验后注入；脚本不创建、猜测或轮换任何材料。
  export \
    CONTENT_POST_SAFETY_HMAC_SECRET_REF \
    CONTENT_POST_SAFETY_RECOVERY_EVIDENCE_REF \
    CONTENT_POST_SAFETY_MATERIAL_ROOT \
    CONTENT_POST_SAFETY_CURRENT_BINDING_REF \
    CONTENT_ACCOUNT_CLOSURE_SUBJECT_HMAC_SECRET \
    QWQ_COMPOSE_POST_SAFETY_MATERIAL_ROOT
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
