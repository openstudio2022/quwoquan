#!/usr/bin/env bash
# Cursor 侧未合入工作副本提醒的投递通道。
#
# 角色：hook。由 `.cursor/hooks.json` 的 `beforeShellExecution`（无 matcher）调用。
#
# 为什么不挂 sessionStart：Cursor 的 Event Output Cheat Sheet 只为 preToolUse、
# postToolUse、subagentStart/Stop 与 beforeShellExecution/beforeMCPExecution 声明了输出
# 字段，sessionStart 没有任何可投递消息的字段。提醒必须落在能出声的事件上，否则它会
# 静默不生效——而静默失效正是本机制要治理的那类问题。
#
# 因为它对每条 shell 命令都触发，未到提醒时点必须在 bash 内短路，不启动解释器：把
# 50ms 的 python 启动摊到每条命令上不可接受。sentinel 里只有一个 epoch 数字，因此这里
# 不需要、也不得内联提醒间隔——间隔只由 quwoquan_ops/policies/worktree_policy.yaml 决定。
#
# 行为语义归属：
#   specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md
#   的 REQ-002。

set -uo pipefail

# 必须消费 stdin：Cursor 会把事件 payload 写进来，不读会让上游拿到 broken pipe。
cat >/dev/null 2>&1 || true

allow() {
  printf '{"permission":"allow"}\n'
  exit 0
}

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. && pwd)" || allow
sentinel="${QWQ_OUTPUT_ROOT:-$ROOT/.qwq_output}/env/repo/local/worktree-governance/cache/next-reminder-at"

next="$(cat "$sentinel" 2>/dev/null || true)"
if [[ "$next" =~ ^[0-9]+$ ]] && (( $(date +%s) < next )); then
  allow
fi

cd "$ROOT" 2>/dev/null || allow
message="$(PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/hooks/worktree_merge_reminder.py \
  --harness git --reason session 2>/dev/null)" || allow
[[ -n "$message" ]] || allow

# 提醒既给用户看也给执行体看：执行体需要知道有副本压着未合入工作，才不会再开新的。
MESSAGE="$message" python3 -c '
import json, os
text = os.environ["MESSAGE"]
print(json.dumps({"permission": "allow", "user_message": text, "agent_message": text}, ensure_ascii=False))
' 2>/dev/null || allow
