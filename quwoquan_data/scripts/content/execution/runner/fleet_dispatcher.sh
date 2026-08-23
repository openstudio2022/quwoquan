#!/usr/bin/env bash
# Fleet 调度器（boundary.md 豁免层，≤100 行）：只做进程起/收/记录退出码。
# 阶段语义零感知、宿主零分支；宿主/API 瞬时失败指数退避重启 ≤3 次（基础设施
# 重试），业务终态（完成 0 / blocked 2 / 超轮 3 / claim 冲突 4）永不重试。
set -euo pipefail
BACKLOG="" HOST_CMD="" MAX_PARALLEL=1 MAX_ROUNDS=20 ROUND_TIMEOUT=1800 LOG_DIR=""
while [[ $# -gt 0 ]]; do case "$1" in
  --backlog) BACKLOG="$2"; shift 2;;
  --host-cmd) HOST_CMD="$2"; shift 2;;
  --max-parallel) MAX_PARALLEL="$2"; shift 2;;
  --max-rounds) MAX_ROUNDS="$2"; shift 2;;
  --round-timeout) ROUND_TIMEOUT="$2"; shift 2;;
  --log-dir) LOG_DIR="$2"; shift 2;;
  *) echo "unknown arg: $1" >&2; exit 64;;
esac; done
if [[ -z "$BACKLOG" || -z "$HOST_CMD" || ! -f "$BACKLOG" ]]; then
  echo "usage: fleet_dispatcher.sh --backlog <executionId 列表文件> --host-cmd '<HOST_CMD>'" \
    "[--max-parallel N] [--max-rounds N] [--round-timeout S] [--log-dir DIR]" >&2
  exit 64
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"
DRIVER="$SCRIPT_DIR/loop_driver.sh"
LOG_DIR="${LOG_DIR:-$REPO_ROOT/.qwq_output/data/local/fleet/$(date +%Y%m%dT%H%M%S)}"
mkdir -p "$LOG_DIR"
RESULTS="$LOG_DIR/results.tsv"
: > "$RESULTS"

run_lane() { # 单 lane：业务终态直接记录；基础设施失败退避重启 ≤3
  local id="$1" attempt=0 rc=0
  while :; do
    rc=0
    bash "$DRIVER" --execution-id "$id" --host-cmd "$HOST_CMD" \
      --max-rounds "$MAX_ROUNDS" --round-timeout "$ROUND_TIMEOUT" \
      >>"$LOG_DIR/$id.log" 2>&1 || rc=$?
    case "$rc" in 0|2|3|4) break;; esac
    attempt=$((attempt + 1))
    if (( attempt > 3 )); then break; fi
    sleep $((30 * (2 ** (attempt - 1))))
  done
  printf '%s\t%s\texit=%s\tinfra_retries=%s\n' \
    "$(date -u +%FT%TZ)" "$id" "$rc" "$attempt" >> "$RESULTS"
}

while IFS= read -r line; do
  id="${line%%#*}"; id="$(echo "$id" | tr -d '[:space:]')"
  [[ -z "$id" ]] && continue
  while (( $(jobs -rp | wc -l) >= MAX_PARALLEL )); do sleep 5; done
  echo "fleet_dispatcher: lane start $id"
  run_lane "$id" &
done < "$BACKLOG"
wait
echo "fleet_dispatcher: all lanes finished; results: $RESULTS"
cat "$RESULTS"
