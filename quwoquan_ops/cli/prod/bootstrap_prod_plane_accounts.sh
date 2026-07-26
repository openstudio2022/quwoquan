#!/usr/bin/env bash
# 一次性 bootstrap：在 prod ECS 上按 quwoquan_ops/environments/prod/access-isolation.yaml 创建
# 非 root 中转账号 prod-ops 与四平面 rootless Linux service 账号（去 root，最小权限）。
#
# 设计原则（与访问隔离映射单一真相源一致）：
#   - 账号/路径全部来自 prod/access-isolation.yaml，脚本不内嵌第二套账号清单。
#   - rootless podman：为每个读写平面账号 enable-linger，独立 home / compose 项目根 / credentials(0700)。
#   - data 平面：只读审计账号，不建 compose 根、不授予写。
#   - 幂等：已存在的账号/目录跳过；可重复执行。
#   - 默认 DRY_RUN=true：只打印将执行的远端命令；DRY_RUN=false 才真正经 SSH 以管理员账号执行。
#
# 用法（dry-run 预览）：
#   quwoquan_ops/cli/prod/bootstrap_prod_plane_accounts.sh
# 用法（真实执行，需管理员 SSH 一次性 key-only 入口；之后不再用 root）：
#   DRY_RUN=false PROD_BOOTSTRAP_SSH_HOST=<host> PROD_BOOTSTRAP_SSH_USER=<admin> \
#   PROD_BOOTSTRAP_SSH_KEY_FILE=<path> quwoquan_ops/cli/prod/bootstrap_prod_plane_accounts.sh
# 若当前仅有口令入口，请走手工 break-glass：先由人工在目标机上安装管理员公钥，再回到本脚本执行。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

DRY_RUN="${DRY_RUN:-true}"
ACCESS_MANIFEST="quwoquan_ops/environments/prod/access-isolation.yaml"

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
    # prod 平面账号需要通过 SSH 自登录执行受限 bash 命令，不能继续使用 nologin。
    lines.append(f'if id "{name}" >/dev/null 2>&1; then echo "[skip] user {name} exists"; else useradd --create-home --home-dir "{home}" --shell /bin/bash "{name}"; echo "[done] useradd {name}"; fi')
    lines.append(f'install -d -m 0750 -o "{name}" -g "{name}" "{home}"')
    lines.append(f'chsh -s /bin/bash "{name}" >/dev/null 2>&1 || usermod -s /bin/bash "{name}"')
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

remote_shell="sudo bash -s"
if [[ "$PROD_BOOTSTRAP_SSH_USER" == "root" ]]; then
  remote_shell="bash -s"
fi

echo "[bootstrap] 经 SSH 以管理员 $PROD_BOOTSTRAP_SSH_USER@$PROD_BOOTSTRAP_SSH_HOST 执行（仅本次 bootstrap 使用 root/sudo）"
if [[ -z "${PROD_BOOTSTRAP_SSH_KEY_FILE:-}" ]]; then
  echo "FAIL: DRY_RUN=false 需要 PROD_BOOTSTRAP_SSH_KEY_FILE（已退役 sshpass / 口令 bootstrap 自动化）" >&2
  exit 2
fi
if [[ ! -f "$PROD_BOOTSTRAP_SSH_KEY_FILE" ]]; then
  echo "FAIL: SSH key 文件不存在: $PROD_BOOTSTRAP_SSH_KEY_FILE" >&2
  exit 2
fi
printf '%s\n' "$REMOTE_SCRIPT" | ssh \
  -i "$PROD_BOOTSTRAP_SSH_KEY_FILE" \
  -o StrictHostKeyChecking=accept-new \
  "${PROD_BOOTSTRAP_SSH_USER}@${PROD_BOOTSTRAP_SSH_HOST}" \
  "$remote_shell"
echo "[bootstrap] 完成：之后所有发布改用各平面账号自登录，禁止再用 root。"
