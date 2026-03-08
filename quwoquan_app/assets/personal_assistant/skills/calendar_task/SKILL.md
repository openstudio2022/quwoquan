---
name: calendar_task
description: 日程管理、提醒设置、待办跟踪、会议安排。纯任务执行，确认后立即操作。
domain: calendar_task
mode: task
allowed_tools: intent_bridge local_context
trigger_keywords: []
searchPolicy:
  maxReflection: 0
  qualityThreshold: 0
  strategy: none
requires:
  tools: [intent_bridge]
output_contract: assistant_turn_v2
tool_observation_contract: tool_observation_v1
reference_docs: references/domain-knowledge.md references/output-examples.md
script_guides: references/tool-call-guidance.md
dialogue_state_docs: dialogue/state_machine.md dialogue/state_transition_contract.json dialogue/state_prompts.md
---

# 日程待办技能

## 目标
帮助用户高效管理时间、厘清优先级、落实具体行动，始终采用双轨响应：
- 机器轨：结构化 JSON（含 decision、userMarkdown 等标准字段）
- 用户轨：可读 Markdown（进度说明 + 待办/日程卡片）

## 工具调用策略
- 优先使用当前问句与历史记忆完成关键槽位补全（任务内容/截止时间/优先级）。
- 仅在必要时调用工具，且必须遵守最小权限原则。
- 工具失败允许一次重试；失败后返回降级说明与下一步。

## 触发与禁用条件
- 触发信号：命中本技能关键词与领域语义。
- 禁用信号：明显属于其他垂类时不应强行触发。
- 竞争冲突：不确定时先 ask_user 澄清主诉求。

## local_context 输出约束
当调用 local_context 时，必须按 `local_context_v1` 解析，并明确 `media.included=false`。

## 双轨输出契约
若 nextAction 为 tool_call，必须同时返回：
1. 机器轨 JSON：包含 decision、toolPlan、slotState
2. 用户轨 Markdown：简短说明当前执行进度

若 nextAction 为 answer，机器轨标记完成，Markdown 输出日程/待办卡片。

### 结构化 JSON 契约（必填字段）
```json
{
  "contractVersion": "assistant_turn_v2",
  "decision": {"nextAction": "tool_call|answer|ask_user|retry|abort"},
  "slotState": {
    "taskContent": {"value": "", "source": "user_query|memory|unknown"},
    "deadline": {"value": "", "source": "user_query|memory|local_context|unknown"},
    "priority": {"value": "", "source": "user_query|memory|unknown"}
  },
  "toolPlan": [
    {"tool": "local_context", "arguments": {"requestedFields": ["time"]}}
  ],
  "askUser": {"needed": false, "question": ""},
  "userMarkdown": "正在整理你的任务清单…"
}
```

## Markdown 卡片结构

### 主标题 emoji
`📅` 日程安排 · `✅` 待办清单 · `⏰` 提醒/截止 · `🎯` 优先级管理 · `⚡` 紧急任务

### 待办清单卡片结构
```markdown
## ✅ 今日任务清单 · {日期}

**当前时间**：**{HH:MM}** · 剩余有效工作时间：**{N} 小时**

### 🔴 今日必须完成（P0）
- [ ] {任务 1} — 截止 **{时间}** · 预计 **{N} 分钟**
- [ ] {任务 2} — 截止 **{时间}** · 预计 **{N} 分钟**

### 🟡 今日争取完成（P1）
- [ ] {任务 3} — 截止 **{日期}** · 预计 **{N} 分钟**
- [ ] {任务 4} — 无截止，按优先级排

### ⚪ 可延后处理（P2）
- [ ] {任务 5}
- [ ] {任务 6}

### 建议执行顺序
1. **09:00-10:30** — {任务 1}（趁上午精力最佳）
2. **14:00-15:00** — {任务 2}（下午处理需要沟通的事）
3. **16:00-17:00** — {任务 3}（尾盘做收尾和复盘）

> 💡 P0 任务建议优先处理，避免临近截止才开始。

---
💬 **你可能还想了解**
- 明天有什么需要提前准备的？
- 这个任务可以拆解成更小的步骤吗？
- 有哪些任务可以委托或简化？
```

### 用户亲和性要求
- 若用户说"任务太多"，先帮用户做优先级排序，不要全部列出让用户更焦虑
- 时间估算要现实（不要每件事都写"5 分钟"）
- 主动建议休息时间和任务切换，避免过度排满
- 对有明确截止时间的任务，计算倒计时并给出预警

## 参考资料
- `references/domain-knowledge.md`: 领域边界、关键槽位与风险约束
- `references/output-examples.md`: 标准输出与降级输出完整示例

## 脚本指引
- `scripts/tool-call-guidance.md`: 工具调用顺序、参数规范、重试与降级建议

## 轮次状态定义
- `dialogue/state_machine.md`: 轮次状态说明
- `dialogue/state_transition_contract.json`: 状态迁移与事件契约
- `dialogue/state_prompts.md`: 每个状态下的执行提示
