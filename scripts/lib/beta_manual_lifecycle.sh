#!/usr/bin/env bash

# Shared lifecycle helpers for local beta manual stacks.
# The helpers track child process groups so restart/cleanup can stop go run,
# Python gateway, and their children without killing unrelated shell sessions.

BETA_MANUAL_LABEL="${BETA_MANUAL_LABEL:-beta-manual}"
BETA_MANUAL_STACK_NAME="${BETA_MANUAL_STACK_NAME:-beta_manual}"
BETA_MANUAL_LOG_DIR="${BETA_MANUAL_LOG_DIR:-}"
BETA_MANUAL_STATE_DIR="${BETA_MANUAL_STATE_DIR:-${BETA_MANUAL_LOG_DIR}/state}"
BETA_MANUAL_STOP_TIMEOUT_SECONDS="${BETA_MANUAL_STOP_TIMEOUT_SECONDS:-15}"
BETA_MANUAL_KILL_EXISTING="${BETA_MANUAL_KILL_EXISTING:-0}"
BETA_MANUAL_OWNER_ID="${BETA_MANUAL_OWNER_ID:-}"

beta_manual_init() {
  if [[ -z "$BETA_MANUAL_LOG_DIR" ]]; then
    echo "BETA_MANUAL_LOG_DIR is required" >&2
    exit 2
  fi
  BETA_MANUAL_STATE_DIR="${BETA_MANUAL_STATE_DIR:-${BETA_MANUAL_LOG_DIR}/state}"
  mkdir -p "$BETA_MANUAL_LOG_DIR" "$BETA_MANUAL_STATE_DIR/processes"
}

beta_manual_process_file() {
  local name="$1"
  echo "$BETA_MANUAL_STATE_DIR/processes/${name}.env"
}

beta_manual_quote() {
  python3 - "$1" <<'PY'
import shlex
import sys

print(shlex.quote(sys.argv[1]))
PY
}

beta_manual_record_metadata() {
  local key="$1"
  local value="$2"
  mkdir -p "$BETA_MANUAL_STATE_DIR"
  printf "%s=%s\n" "$key" "$(beta_manual_quote "$value")" >>"$BETA_MANUAL_STATE_DIR/stack.env"
}

beta_manual_port_pids() {
  local port="$1"
  lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
}

beta_manual_pid_pgid() {
  local pid="$1"
  ps -o pgid= -p "$pid" 2>/dev/null | tr -d '[:space:]' || true
}

beta_manual_process_group_alive() {
  local pgid="$1"
  [[ -n "$pgid" ]] && kill -0 "-$pgid" 2>/dev/null
}

beta_manual_start_process() {
  local name="$1"
  local log_file="$2"
  local cwd="$3"
  shift 3

  mkdir -p "$(dirname "$log_file")" "$BETA_MANUAL_STATE_DIR/processes"
  local process_file
  process_file="$(beta_manual_process_file "$name")"
  rm -f "$process_file"

  python3 - "$process_file" "$log_file" "$cwd" "$@" <<'PY' &
import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

process_file = Path(sys.argv[1])
log_file = Path(sys.argv[2])
cwd = sys.argv[3]
argv = sys.argv[4:]

log_file.parent.mkdir(parents=True, exist_ok=True)
process_file.parent.mkdir(parents=True, exist_ok=True)
log = log_file.open("ab", buffering=0)
child: subprocess.Popen[bytes] | None = None
stopping = False


def write_record() -> None:
    assert child is not None
    pgid = os.getpgid(child.pid)
    process_file.write_text(
        "\n".join(
            [
                f"name={shlex.quote(process_file.stem)}",
                f"pid={child.pid}",
                f"pgid={pgid}",
                f"wrapper_pid={os.getpid()}",
                f"owner_id={shlex.quote(os.environ.get('BETA_MANUAL_OWNER_ID', ''))}",
                f"log={shlex.quote(str(log_file))}",
                f"cwd={shlex.quote(cwd)}",
                f"started_at={int(time.time())}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def stop_child(signum: int = signal.SIGTERM) -> None:
    global stopping
    if child is None or child.poll() is not None:
        return
    if stopping:
        return
    stopping = True
    try:
        os.killpg(child.pid, signum)
    except ProcessLookupError:
        return
    except Exception:
        try:
            child.terminate()
        except Exception:
            return


def handle_signal(signum: int, _frame: object) -> None:
    stop_child(signum)


signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)

try:
    child = subprocess.Popen(
        argv,
        cwd=cwd,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    write_record()
    exit_code = child.wait()
    raise SystemExit(exit_code)
finally:
    try:
        log.close()
    finally:
        pass
PY
  BETA_MANUAL_LAST_WRAPPER_PID="$!"

  local deadline=$((SECONDS + 10))
  until [[ -f "$process_file" ]]; do
    if (( SECONDS >= deadline )); then
      echo "[$BETA_MANUAL_LABEL] failed to start managed process: $name" >&2
      return 1
    fi
    sleep 0.1
  done
}

beta_manual_stop_process_file() {
  local process_file="$1"
  [[ -f "$process_file" ]] || return 0

  local owner_filter="${2:-}"
  local name="" pid="" pgid="" wrapper_pid="" owner_id="" log=""
  # shellcheck disable=SC1090
  source "$process_file"

  if [[ -n "$owner_filter" && "${owner_id:-}" != "$owner_filter" ]]; then
    return 0
  fi

  if [[ -n "$pgid" ]] && beta_manual_process_group_alive "$pgid"; then
    echo "[$BETA_MANUAL_LABEL] stopping ${name:-process} pgid=$pgid"
    kill -TERM "-$pgid" 2>/dev/null || true
    local deadline=$((SECONDS + BETA_MANUAL_STOP_TIMEOUT_SECONDS))
    while beta_manual_process_group_alive "$pgid"; do
      if (( SECONDS >= deadline )); then
        echo "[$BETA_MANUAL_LABEL] force killing ${name:-process} pgid=$pgid"
        kill -KILL "-$pgid" 2>/dev/null || true
        break
      fi
      sleep 0.2
    done
  elif [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    echo "[$BETA_MANUAL_LABEL] stopping ${name:-process} pid=$pid"
    kill -TERM "$pid" 2>/dev/null || true
  fi

  if [[ -n "$wrapper_pid" ]] && kill -0 "$wrapper_pid" 2>/dev/null; then
    kill -TERM "$wrapper_pid" 2>/dev/null || true
  fi

  rm -f "$process_file"
}

beta_manual_stop_stack() {
  local clean_env="${1:-0}"
  local owner_filter="${2:-}"
  local controller_pid=""
  beta_manual_init
  for name in flutter-run gateway assistant-service; do
    beta_manual_stop_process_file "$(beta_manual_process_file "$name")" "$owner_filter"
  done
  if [[ -z "$owner_filter" && -f "$BETA_MANUAL_STATE_DIR/stack.env" ]]; then
    # shellcheck disable=SC1090
    source "$BETA_MANUAL_STATE_DIR/stack.env"
    if [[ -n "${controller_pid:-}" && "$controller_pid" != "$$" ]] && kill -0 "$controller_pid" 2>/dev/null; then
      kill -TERM "$controller_pid" 2>/dev/null || true
    fi
  fi
  if [[ "$clean_env" == "1" && -z "$owner_filter" ]]; then
    rm -rf "$BETA_MANUAL_STATE_DIR"
  fi
}

beta_manual_port_owned_by_stack() {
  local port="$1"
  local port_pid port_pgid process_file pgid=""
  while IFS= read -r port_pid; do
    [[ -n "$port_pid" ]] || continue
    port_pgid="$(beta_manual_pid_pgid "$port_pid")"
    for process_file in "$BETA_MANUAL_STATE_DIR"/processes/*.env; do
      [[ -f "$process_file" ]] || continue
      pgid=""
      # shellcheck disable=SC1090
      source "$process_file"
      if [[ -n "$pgid" && "$pgid" == "$port_pgid" ]]; then
        return 0
      fi
    done
  done < <(beta_manual_port_pids "$port")
  return 1
}

beta_manual_ensure_port_available() {
  local port="$1"
  local label="${2:-port}"
  local pids
  pids="$(beta_manual_port_pids "$port")"
  if [[ -z "$pids" ]]; then
    return 0
  fi

  if beta_manual_port_owned_by_stack "$port"; then
    echo "[$BETA_MANUAL_LABEL] stopping previous stack listener(s) on :$port"
    beta_manual_stop_stack 0
    sleep 1
    pids="$(beta_manual_port_pids "$port")"
    [[ -z "$pids" ]] && return 0
  fi

  if [[ "$BETA_MANUAL_KILL_EXISTING" == "1" ]]; then
    echo "[$BETA_MANUAL_LABEL] kill existing listener(s) on :$port: $pids"
    kill $pids 2>/dev/null || true
    sleep 1
    pids="$(beta_manual_port_pids "$port")"
    if [[ -n "$pids" ]]; then
      echo "[$BETA_MANUAL_LABEL] force kill existing listener(s) on :$port: $pids"
      kill -KILL $pids 2>/dev/null || true
      sleep 1
    fi
    pids="$(beta_manual_port_pids "$port")"
    if [[ -n "$pids" ]]; then
      echo "Port :$port is still in use by pid(s): $pids after --kill-existing." >&2
      exit 2
    fi
    return 0
  fi

  echo "Port :$port is already in use by pid(s): $pids" >&2
  echo "Run the stop script first, use --restart for a managed stack, or rerun with --kill-existing." >&2
  echo "Blocked label: $label" >&2
  exit 2
}

beta_manual_wait_http_ok() {
  local url="$1"
  local label="$2"
  local timeout="${3:-60}"
  local deadline=$((SECONDS + timeout))
  until curl -fsS "$url" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      echo "$label health check failed: $url" >&2
      return 1
    fi
    sleep 1
  done
  echo "[$BETA_MANUAL_LABEL] $label OK: $url"
}

beta_manual_wait_until_stopped() {
  local names=("$@")
  local process_file wrapper_pid any_running
  while true; do
    any_running=0
    for name in "${names[@]}"; do
      process_file="$(beta_manual_process_file "$name")"
      [[ -f "$process_file" ]] || continue
      wrapper_pid=""
      # shellcheck disable=SC1090
      source "$process_file"
      if [[ -n "$wrapper_pid" ]] && kill -0 "$wrapper_pid" 2>/dev/null; then
        any_running=1
      else
        rm -f "$process_file"
      fi
    done
    [[ "$any_running" == "1" ]] || return 0
    sleep 1
  done
}

beta_manual_terminate_flutter_app() {
  local device_id="${1:-}"
  local ios_bundle_id="${2:-com.example.quwoquanApp}"
  local android_package="${3:-com.quwoquan.quwoquan_app}"

  if [[ -n "$device_id" ]] && command -v xcrun >/dev/null 2>&1; then
    xcrun simctl terminate "$device_id" "$ios_bundle_id" >/dev/null 2>&1 || true
  fi
  if [[ -n "$device_id" ]] && command -v adb >/dev/null 2>&1; then
    adb -s "$device_id" shell am force-stop "$android_package" >/dev/null 2>&1 || true
  fi
}

# 被直接执行（非 source）时：本文件仅为函数库，不启动 assistant/gateway/Flutter。
if [[ -n "${BASH_VERSION:-}" ]] && [[ "${BASH_SOURCE[0]}" -ef "$0" ]]; then
  cat <<'EOF' >&2
[beta_manual_lifecycle] 本脚本只提供公共函数，不会启动 beta 端云实例。
           请在仓库根目录运行入口脚本，例如:
             scripts/start_app_beta_manual.sh
EOF
  exit 2
fi
