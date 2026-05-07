#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_ROOT="${APP_INSTANCE_STATE_ROOT:-$ROOT_DIR/tmp/app-instances}"

ENV_NAME=""
DEVICE_ID=""
QUIET=0
STOP_ALL=0

usage() {
  cat <<EOF
Usage:
  scripts/stop_app_instance.sh [options]

Options:
  --env <alpha|beta|gamma>   Stop matching env instances.
  --device-id <id>           Stop matching device instance.
  --all                      Stop all recorded app instances.
  --quiet                    Suppress per-instance logs.
  -h, --help                 Show this help.

Without --all, at least one of --env or --device-id is required.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      ENV_NAME="${2:-}"
      shift 2
      ;;
    --device-id)
      DEVICE_ID="${2:-}"
      shift 2
      ;;
    --all)
      STOP_ALL=1
      shift
      ;;
    --quiet)
      QUIET=1
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

if [[ "$STOP_ALL" != "1" && -z "$ENV_NAME" && -z "$DEVICE_ID" ]]; then
  echo "FAIL: provide --all or at least one of --env/--device-id" >&2
  exit 2
fi

python3 - "$STATE_ROOT" "$ENV_NAME" "$DEVICE_ID" "$STOP_ALL" "$QUIET" <<'PY'
import json
import os
import signal
import sys
import time
from pathlib import Path

state_root = Path(sys.argv[1])
env_name = sys.argv[2].strip()
device_id = sys.argv[3].strip()
stop_all = sys.argv[4] == "1"
quiet = sys.argv[5] == "1"

if not state_root.exists():
    raise SystemExit(0)


def log(message: str) -> None:
    if not quiet:
        print(message)


def matches(payload: dict[str, object]) -> bool:
    if stop_all:
        return True
    if env_name and str(payload.get("env") or "").strip() != env_name:
        return False
    if device_id and str(payload.get("deviceId") or "").strip() != device_id:
        return False
    return True


def wait_dead(pgid: int, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.2)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return


for path in sorted(state_root.glob("*/*.json")):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        path.unlink(missing_ok=True)
        continue
    if not matches(payload):
        continue
    pid = int(payload.get("pid") or 0)
    pgid = int(payload.get("pgid") or 0)
    instance_id = str(payload.get("instanceId") or path.stem)
    if pid > 0:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            path.unlink(missing_ok=True)
            log(f"[app-instance] prune stale record: {instance_id}")
            continue
    if pgid > 0:
        log(f"[app-instance] stopping {instance_id} pgid={pgid}")
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        wait_dead(pgid)
    path.unlink(missing_ok=True)
PY
