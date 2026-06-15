#!/usr/bin/env bash
# 一次性 bootstrap：在 prod ECS 上按 deploy/shared/prod_plane_access_isolation.yaml 创建
# 非 root 中转账号 prod-ops 与四平面 rootless Linux service 账号（去 root，最小权限）。
#
# 设计原则（与访问隔离映射单一真相源一致）：
#   - 账号/路径全部来自 prod_plane_access_isolation.yaml，脚本不内嵌第二套账号清单。
#   - rootless podman：为每个读写平面账号 enable-linger，独立 home / compose 项目根 / credentials(0700)。
#   - data 平面：只读审计账号，不建 compose 根、不授予写。
#   - 幂等：已存在的账号/目录跳过；可重复执行。
#   - 默认 DRY_RUN=true：只打印将执行的远端命令；DRY_RUN=false 才真正经 SSH 以管理员账号执行。
#
# 用法（dry-run 预览）：
#   agent_ops/deploy/prod/bootstrap_prod_plane_accounts.sh
# 用法（真实执行，需管理员 SSH 一次性入口；之后不再用 root）：
#   DRY_RUN=false PROD_BOOTSTRAP_SSH_HOST=<host> PROD_BOOTSTRAP_SSH_USER=<admin> \
#   PROD_BOOTSTRAP_SSH_KEY_FILE=<path> agent_ops/deploy/prod/bootstrap_prod_plane_accounts.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

DRY_RUN="${DRY_RUN:-true}"
ACCESS_MANIFEST="deploy/shared/prod_plane_access_isolation.yaml"

if [[ ! -f "$ACCESS_MANIFEST" ]]; then
  echo "FAIL: 缺少访问隔离映射 $ACCESS_MANIFEST" >&2
  exit 2
fi

# 从单一真相源生成远端 bootstrap 命令脚本（不内嵌第二套账号清单）。
REMOTE_SCRIPT="$(python3 - "$ACCESS_MANIFEST" <<'PY'
import sys
import yaml

data = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
lines = ["set -euo pipefail"]

def ensure_account(name, home, *, rootless, compose_root, creds_path):
    lines.append(f'if id "{name}" >/dev/null 2>&1; then echo "[skip] user {name} exists"; else useradd --create-home --home-dir "{home}" --shell /usr/sbin/nologin "{name}"; echo "[done] useradd {name}"; fi')
    lines.append(f'install -d -m 0750 -o "{name}" -g "{name}" "{home}"')
    if creds_path:
        lines.append(f'install -d -m 0700 -o "{name}" -g "{name}" "{creds_path}"')
    if compose_root:
        lines.append(f'install -d -m 0750 -o "{name}" -g "{name}" "{compose_root}"')
    if rootless:
        # rootless podman 需要 lingering，使账号无需登录会话即可常驻容器。
        lines.append(f'loginctl enable-linger "{name}" || true')
        lines.append(f'echo "[done] enable-linger {name} (rootless podman)"')

relay = data.get("relayAccount") or {}
ensure_account(
    relay["name"], relay["home"],
    rootless=False,
    compose_root=relay.get("bootstrapPath"),
    creds_path=None,
)

for p in data.get("planes") or []:
    ensure_account(
        p["account"], p["home"],
        rootless=(p.get("runtimeContainer") == "rootless-podman"),
        compose_root=p.get("composeProjectRoot"),
        creds_path=p.get("credentialsPath"),
    )

print("\n".join(lines))
PY
)"

if [[ -z "$REMOTE_SCRIPT" ]]; then
  echo "FAIL: 未能从 $ACCESS_MANIFEST 生成 bootstrap 命令" >&2
  exit 2
fi

echo "[bootstrap] prod 四平面 + prod-ops 账号（DRY_RUN=${DRY_RUN}）"
echo "----- 将在 prod ECS 上执行的远端命令 -----"
echo "$REMOTE_SCRIPT"
echo "------------------------------------------"

if [[ "$DRY_RUN" == "true" ]]; then
  echo "[bootstrap] dry_run — 仅预览，不执行。设置 DRY_RUN=false 并提供 PROD_BOOTSTRAP_SSH_* 后真实执行。"
  exit 0
fi

: "${PROD_BOOTSTRAP_SSH_HOST:?DRY_RUN=false 需要 PROD_BOOTSTRAP_SSH_HOST}"
: "${PROD_BOOTSTRAP_SSH_USER:?DRY_RUN=false 需要 PROD_BOOTSTRAP_SSH_USER（一次性管理员账号）}"
: "${PROD_BOOTSTRAP_SSH_KEY_FILE:?DRY_RUN=false 需要 PROD_BOOTSTRAP_SSH_KEY_FILE}"

if [[ ! -f "$PROD_BOOTSTRAP_SSH_KEY_FILE" ]]; then
  echo "FAIL: SSH key 文件不存在: $PROD_BOOTSTRAP_SSH_KEY_FILE" >&2
  exit 2
fi

echo "[bootstrap] 经 SSH 以管理员 $PROD_BOOTSTRAP_SSH_USER@$PROD_BOOTSTRAP_SSH_HOST 执行（仅本次 bootstrap 使用 root/sudo）"
printf '%s\n' "$REMOTE_SCRIPT" | ssh \
  -i "$PROD_BOOTSTRAP_SSH_KEY_FILE" \
  -o StrictHostKeyChecking=accept-new \
  "${PROD_BOOTSTRAP_SSH_USER}@${PROD_BOOTSTRAP_SSH_HOST}" \
  "sudo bash -s"
echo "[bootstrap] 完成：之后所有发布改用各平面账号自登录，禁止再用 root。"
