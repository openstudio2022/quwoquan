#!/usr/bin/env bash
# Ralph loop 驱动（boundary.md 豁免层，≤50 行）：阶段零感知、宿主零分支。
# 只读最新 receipt 的 verdict/next 协议字段决定续/停；每轮起全新宿主会话。
set -euo pipefail
EXEC_ID="" HOST_CMD="" MAX_ROUNDS=20 ROUND_TIMEOUT=1800
while [[ $# -gt 0 ]]; do case "$1" in
  --execution-id) EXEC_ID="$2"; shift 2;;
  --host-cmd) HOST_CMD="$2"; shift 2;;
  --max-rounds) MAX_ROUNDS="$2"; shift 2;;
  --round-timeout) ROUND_TIMEOUT="$2"; shift 2;;
  *) echo "unknown arg: $1" >&2; exit 64;;
esac; done
if [[ -z "$EXEC_ID" || -z "$HOST_CMD" ]]; then
  echo "usage: loop_driver.sh --execution-id <id> --host-cmd '<HOST_CMD>' [--max-rounds N] [--round-timeout S]" >&2
  exit 64
fi
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../.." && pwd)"
CLI=(python3 "$REPO_ROOT/quwoquan_data/scripts/cli.py")
PROMPT_SRC="$REPO_ROOT/.agents/skills/content-production/references/loop-prompt.md"
PROMPT="$(awk 'flag{print} /^---$/{flag=1}' "$PROMPT_SRC" | sed "s/<executionId>/$EXEC_ID/g")"
run_round() { # 单轮 hard timeout：超时杀整个会话进程组，宿主派生的孙进程不残留
  set -m  # 让本轮成为独立进程组，组 id 即下面的 pid
  bash -c "cd '$REPO_ROOT' && $HOST_CMD \"\$1\"" _ "$PROMPT" & local pid=$!
  set +m
  ( sleep "$ROUND_TIMEOUT" && kill -9 -"$pid" 2>/dev/null ) & local watchdog=$!
  local rc=0; wait "$pid" || rc=$?
  kill "$watchdog" 2>/dev/null || true; wait "$watchdog" 2>/dev/null || true
  return "$rc"
}
for ((round = 1; round <= MAX_ROUNDS; round++)); do
  # claim 属于执行者（每轮宿主会话）；驱动只做只读预检，不得自己写 claim。
  # 同时声明本轮 hard timeout，由 CLI 判它是否短于 claim 存活窗口（退出码 64）。
  CHECK_RC=0
  "${CLI[@]}" task lane-claim --execution-id "$EXEC_ID" --check \
    --round-timeout-seconds "$ROUND_TIMEOUT" >/dev/null || CHECK_RC=$?
  if [[ "$CHECK_RC" == "64" ]]; then exit 64; fi
  if [[ "$CHECK_RC" != "0" ]]; then
    echo "loop_driver: active claim held by an executor session, not taking over" >&2; exit 4; fi
  read -r VERDICT NEXT < <("${CLI[@]}" task fleet-status --execution-id "$EXEC_ID" --json \
    | python3 -c 'import json,sys; e=json.load(sys.stdin)["executions"][0]; print(e["verdict"] or "none", e["next"] or "none")')
  if [[ "$VERDICT" == "blocked" ]]; then echo "loop_driver: blocked, stopping"; exit 2; fi
  if [[ "$NEXT" == "END" ]]; then echo "loop_driver: execution completed"; exit 0; fi
  echo "loop_driver: round $round/$MAX_ROUNDS (next=$NEXT)"
  if ! run_round; then
    echo "loop_driver: host session exited non-zero; stopping without automatic retry" >&2
    exit 5
  fi
done
echo "loop_driver: max rounds reached without terminal receipt" >&2
exit 3
