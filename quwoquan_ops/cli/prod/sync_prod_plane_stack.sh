#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

ACCESS_MANIFEST="quwoquan_ops/environments/prod_plane_access_isolation.yaml"
TOPOLOGY_MANIFEST="quwoquan_ops/environments/environment_topology_manifest.yaml"
PROD_SSH_KEY_DIR="${PROD_SSH_KEY_DIR:-$HOME/.ssh/quwoquan-prod}"

plane="service"
source_dir=""
host_override=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --plane)
      plane="${2:-}"
      shift 2
      ;;
    --source-dir)
      source_dir="${2:-}"
      shift 2
      ;;
    --host)
      host_override="${2:-}"
      shift 2
      ;;
    *)
      echo "FAIL: unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$source_dir" ]]; then
  echo "FAIL: --source-dir is required" >&2
  exit 2
fi
if [[ ! -d "$source_dir" ]]; then
  echo "FAIL: source dir does not exist: $source_dir" >&2
  exit 2
fi

read -r account compose_root secret_name <<<"$(python3 - "$ACCESS_MANIFEST" "$plane" <<'PY'
import sys
import yaml

path, plane_name = sys.argv[1:3]
data = yaml.safe_load(open(path, encoding="utf-8"))
for plane in data.get("planes") or []:
    if str(plane.get("plane")) == plane_name:
        print(
            str(plane.get("account", "")),
            str(plane.get("composeProjectRoot", "")),
            str(plane.get("sshKeySecret", "")),
        )
        raise SystemExit(0)
raise SystemExit(f"FAIL: plane not found: {plane_name}")
PY
)"

if [[ -z "$account" || -z "$compose_root" || -z "$secret_name" ]]; then
  echo "FAIL: unable to resolve plane metadata for $plane" >&2
  exit 2
fi

host="$host_override"
if [[ -z "$host" ]]; then
  host="$(python3 - "$TOPOLOGY_MANIFEST" <<'PY'
import sys
import yaml
from urllib.parse import urlparse

data = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
api = (((data.get("targets") or {}).get("prod-hosted") or {}).get("publicBases") or {}).get("api", "")
print(urlparse(api).hostname or "")
PY
)"
fi
if [[ -z "$host" ]]; then
  echo "FAIL: unable to resolve prod host" >&2
  exit 2
fi

agent_has_pubkey() {
  local pub_file="$1"
  [[ -S "${SSH_AUTH_SOCK:-}" ]] || return 1
  [[ -f "$pub_file" ]] || return 1
  local expected
  expected="$(awk '{print $1 " " $2}' "$pub_file" 2>/dev/null || true)"
  [[ -n "$expected" ]] || return 1
  ssh-add -L 2>/dev/null | awk '{print $1 " " $2}' | rg -Fx --quiet "$expected"
}

resolve_ssh_mode() {
  local secret="$1"
  local login_account="$2"
  local explicit_var_file="${secret}_FILE"
  local explicit_var_path="${secret}_PATH"
  local candidate="${!explicit_var_file:-${!explicit_var_path:-}}"
  if [[ -z "$candidate" ]]; then
    candidate="${PROD_SSH_KEY_DIR%/}/${login_account}"
  fi
  if [[ -f "$candidate" ]]; then
    RESOLVED_SSH_KEY_FILE="$candidate"
    RESOLVED_SSH_USE_AGENT="false"
    RESOLVED_SSH_SOURCE="$candidate"
    return 0
  fi
  if agent_has_pubkey "${candidate}.pub"; then
    RESOLVED_SSH_KEY_FILE=""
    RESOLVED_SSH_USE_AGENT="true"
    RESOLVED_SSH_SOURCE="${candidate}.pub"
    return 0
  fi
  echo "FAIL: missing SSH credential for ${secret} (${candidate} / ${candidate}.pub)" >&2
  exit 2
}

resolve_ssh_mode "$secret_name" "$account"
echo "[sync] plane=$plane account=$account host=$host source=$source_dir key=${RESOLVED_SSH_SOURCE}"

remote_cmd="mkdir -p '${compose_root}' && tar -xf - -C '${compose_root}'"
if [[ "$RESOLVED_SSH_USE_AGENT" == "true" ]]; then
  tar -C "$source_dir" -cf - . | ssh \
    -o StrictHostKeyChecking=accept-new \
    -o BatchMode=yes \
    "${account}@${host}" \
    "$remote_cmd"
else
  tar -C "$source_dir" -cf - . | ssh \
    -i "$RESOLVED_SSH_KEY_FILE" \
    -o StrictHostKeyChecking=accept-new \
    -o BatchMode=yes \
    "${account}@${host}" \
    "$remote_cmd"
fi

echo "[sync] done plane=$plane compose_root=$compose_root"
