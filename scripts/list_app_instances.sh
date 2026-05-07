#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_ROOT="${APP_INSTANCE_STATE_ROOT:-$ROOT_DIR/tmp/app-instances}"

ENV_NAME=""
JSON_OUTPUT=0
PRUNE=0

usage() {
  cat <<EOF
Usage:
  scripts/list_app_instances.sh [options]

Options:
  --env <alpha|beta|gamma>   Filter by env.
  --json                     Print JSON instead of a table.
  --prune                    Remove stale state files while listing.
  -h, --help                 Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      ENV_NAME="${2:-}"
      shift 2
      ;;
    --json)
      JSON_OUTPUT=1
      shift
      ;;
    --prune)
      PRUNE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

python3 - "$STATE_ROOT" "$ENV_NAME" "$JSON_OUTPUT" "$PRUNE" <<'PY'
import json
import os
import sys
from pathlib import Path

state_root = Path(sys.argv[1])
env_name = sys.argv[2].strip()
json_output = sys.argv[3] == "1"
prune = sys.argv[4] == "1"

records: list[dict[str, object]] = []
for path in sorted(state_root.glob("*/*.json")):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        path.unlink(missing_ok=True)
        continue
    if env_name and str(payload.get("env") or "").strip() != env_name:
        continue
    pid = int(payload.get("pid") or 0)
    alive = False
    if pid > 0:
        try:
            os.kill(pid, 0)
            alive = True
        except ProcessLookupError:
            alive = False
    payload["alive"] = alive
    payload["stateFile"] = str(path)
    if prune and not alive:
        path.unlink(missing_ok=True)
        continue
    records.append(payload)

if json_output:
    print(json.dumps(records, ensure_ascii=False, indent=2))
    raise SystemExit(0)

if not records:
    print("No app instances recorded.")
    raise SystemExit(0)

print("ENV\tDEVICE\tPID\tALIVE\tMODE\tNAMESPACE\tGATEWAY")
for record in records:
    print(
        "\t".join(
            [
                str(record.get("env") or ""),
                str(record.get("deviceId") or ""),
                str(record.get("pid") or ""),
                "yes" if bool(record.get("alive")) else "no",
                str(record.get("serviceMode") or ""),
                str(record.get("instanceNamespace") or ""),
                str(record.get("gatewayBaseUrl") or ""),
            ]
        )
    )
PY
