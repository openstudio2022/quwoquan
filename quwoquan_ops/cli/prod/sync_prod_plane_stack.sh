#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

ACCESS_MANIFEST="quwoquan_ops/environments/prod/access-isolation.yaml"
TOPOLOGY_MANIFEST="quwoquan_ops/environments/prod/runtime.yaml"
PROD_SSH_KEY_DIR="${PROD_SSH_KEY_DIR:-$HOME/.ssh/quwoquan-prod}"

plane="service"
source_dir=""
host_override=""
fetch_relative_dir=""
destination_dir=""
operation="sync"
service=""
request_path=""
output_path=""
receipt_id=""
root_suffix=""

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
    --fetch-relative-dir)
      fetch_relative_dir="${2:-}"
      shift 2
      ;;
    --destination-dir)
      destination_dir="${2:-}"
      shift 2
      ;;
    --operation)
      operation="${2:-}"
      shift 2
      ;;
    --service)
      service="${2:-}"
      shift 2
      ;;
    --request-path)
      request_path="${2:-}"
      shift 2
      ;;
    --output-path)
      output_path="${2:-}"
      shift 2
      ;;
    --receipt-id)
      receipt_id="${2:-}"
      shift 2
      ;;
    --root-suffix)
      root_suffix="${2:-}"
      shift 2
      ;;
    *)
      echo "FAIL: unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ "$operation" == "sync" && -z "$source_dir" && -z "$fetch_relative_dir" ]]; then
  echo "FAIL: --source-dir or --fetch-relative-dir is required" >&2
  exit 2
fi
if [[ -n "$source_dir" && ! -d "$source_dir" ]]; then
  echo "FAIL: source dir does not exist: $source_dir" >&2
  exit 2
fi
if [[ -n "$fetch_relative_dir" ]]; then
  if [[ -z "$destination_dir" ]]; then
    echo "FAIL: --destination-dir is required with --fetch-relative-dir" >&2
    exit 2
  fi
  if [[ "$fetch_relative_dir" == /* || "$fetch_relative_dir" == *".."* ]]; then
    echo "FAIL: --fetch-relative-dir must be a relative path without '..'" >&2
    exit 2
  fi
  mkdir -p "$destination_dir"
fi
case "$operation" in
  sync) ;;
  release-ledger-fetch)
    if [[ -z "$service" || -z "$output_path" ]]; then
      echo "FAIL: release-ledger-fetch requires --service and --output-path" >&2
      exit 2
    fi
    ;;
  release-ledger-commit)
    if [[ -z "$service" || -z "$request_path" || -z "$output_path" ]]; then
      echo "FAIL: release-ledger-commit requires --service, --request-path and --output-path" >&2
      exit 2
    fi
    if [[ ! -s "$request_path" ]]; then
      echo "FAIL: release ledger request does not exist or is empty: $request_path" >&2
      exit 2
    fi
    ;;
  release-ledger-receipt)
    if [[ -z "$service" || -z "$receipt_id" || -z "$output_path" ]]; then
      echo "FAIL: release-ledger-receipt requires --service, --receipt-id and --output-path" >&2
      exit 2
    fi
    ;;
  *)
    echo "FAIL: unsupported operation: $operation" >&2
    exit 2
    ;;
esac

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
if [[ -n "$root_suffix" ]]; then
  if [[ ! "$root_suffix" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
    echo "FAIL: --root-suffix must be a safe single directory name" >&2
    exit 2
  fi
  compose_root="${compose_root%/}/${root_suffix}"
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

ssh_command=(
  ssh
  -o StrictHostKeyChecking=accept-new
  -o BatchMode=yes
)
if [[ "$RESOLVED_SSH_USE_AGENT" != "true" ]]; then
  ssh_command+=(-i "$RESOLVED_SSH_KEY_FILE")
fi
ssh_command+=("${account}@${host}")

if [[ "$operation" == release-ledger-* ]]; then
  helper="$ROOT/quwoquan_ops/cli/prod/hosted_release_ledger.py"
  if [[ ! -s "$helper" ]]; then
    echo "FAIL: hosted release ledger helper is missing: $helper" >&2
    exit 2
  fi
  mkdir -p "$(dirname "$output_path")"
  remote_args=(
    --root "${compose_root%/}/release-ledger"
    --action "${operation#release-ledger-}"
    --service "$service"
  )
  if [[ "$operation" == "release-ledger-commit" ]]; then
    request_base64="$(base64 < "$request_path" | tr -d '\r\n')"
    remote_args+=(--request-base64 "$request_base64")
  elif [[ "$operation" == "release-ledger-receipt" ]]; then
    remote_args+=(--receipt-id "$receipt_id")
  fi
  remote_command="python3 -"
  for value in "${remote_args[@]}"; do
    printf -v quoted_value '%q' "$value"
    remote_command+=" $quoted_value"
  done
  "${ssh_command[@]}" "$remote_command" < "$helper" > "$output_path"
  [[ -s "$output_path" ]] || {
    echo "FAIL: hosted release ledger returned an empty readback" >&2
    exit 2
  }
  exit 0
fi

echo "[sync] plane=$plane account=$account host=$host key=${RESOLVED_SSH_SOURCE}"

if [[ -n "$source_dir" ]]; then
  remote_cmd="mkdir -p '${compose_root}' && tar -xf - -C '${compose_root}'"
  tar -C "$source_dir" -cf - . | "${ssh_command[@]}" "$remote_cmd"
  echo "[sync] pushed plane=$plane compose_root=$compose_root source=$source_dir"
fi

if [[ -n "$fetch_relative_dir" ]]; then
  remote_fetch_cmd="if test -d '${compose_root}/${fetch_relative_dir}'; then tar -C '${compose_root}/${fetch_relative_dir}' -cf - .; else exit 3; fi"
  "${ssh_command[@]}" "$remote_fetch_cmd" | tar -xf - -C "$destination_dir"
  echo "[sync] fetched plane=$plane remote=${compose_root}/${fetch_relative_dir} destination=$destination_dir"
fi
