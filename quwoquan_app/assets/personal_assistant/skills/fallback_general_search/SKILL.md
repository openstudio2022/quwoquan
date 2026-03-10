---
name: fallback_general_search
description: 通用搜索兜底。当其他技能都不匹配时使用。
domain: fallback_general_search
mode: qa
allowed_tools: web_search local_context
trigger_keywords: []
searchPolicy:
  maxReflection: 2
  qualityThreshold: 0.4
  strategy: research
execution_shell:
  problemClass: general
  maxIterations: 4
  toolBudget: 2
  variantBudget: 1
  reflectionBudget: 1
  providerPolicy: model_choice
  preferredProviders: [web]
  authorityDomains: []
  freshnessHoursMax: 24
requires:
  tools: [web_search]
output_contract: assistant_turn_v2
tool_observation_contract: tool_observation_v1
reference_docs: references/domain-knowledge.md references/output-examples.md
script_guides: references/tool-call-guidance.md
dialogue_state_docs: dialogue/state_machine.md dialogue/state_transition_contract.json dialogue/state_prompts.md
---

# 通用检索技能

## 目标
输出稳健、有信息价值、格式精美的通用回复，作为所有垂类的兜底保障，始终采用双轨响应：
- 机器轨：结构化 JSON（含 decision、userMarkdown 等标准字段）
- 用户轨：可读 Markdown（进度说明 + 结果卡片）

## 工具调用策略
- 优先使用当前问句与历史记忆完成关键槽位补全。
- 仅在必要时调用工具，且必须遵守最小权限原则。
- 工具失败允许一次重试；失败后返回降级说明与下一步。

## 触发与禁用条件
- 触发信号：命中本技能关键词与领域语义，或其他垂类均未命中时兜底触发。
- 禁用信号：明显属于其他垂类时不应强行触发。
- 竞争冲突：不确定时先 ask_user 澄清主诉求。

## local_context 输出约束
当调用 local_context 时，必须按 `local_context_v1` 解析，并明确 `media.included=false`。

## 双轨输出契约
若 nextAction 为 tool_call，必须同时返回：
1. 机器轨 JSON：包含 decision、toolPlan、slotState
2. 用户轨 Markdown：简短说明当前执行进度

若 nextAction 为 answer，机器轨标记完成，Markdown 输出最终结果卡片。

### 结构化 JSON 契约（必填字段）
```json
{
  "contractVersion": "assistant_turn_v2",
  "decision": {"nextAction": "tool_call|answer|ask_user|retry|abort"},
  "slotState": {},
  "toolPlan": [
    {"tool": "web_search", "arguments": {"query": "示例查询"}}
  ],
  "askUser": {"needed": false, "question": ""},
  "userMarkdown": "正在查询相关信息…"
}
```

## Markdown 卡片结构

### 标准信息卡片结构（通用兜底）
```markdown
## 💡 {问题核心关键词} — 要点速览

**核心答案**：{1-2 句直接回答，结论前置}

### 详细信息
{正文，结构化段落或列表，视内容复杂度选择}

- {要点 1}
- {要点 2}
- {要点 3（可选）}

> 💡 来源：{权威来源}。信息有效期以来源发布时间为准，时效性内容建议二次核查。

---
💬 **你可能还想了解**
- {自然延伸的追问 1}
- {不同角度的追问 2}
```

### 降级回复结构（工具失败时）
```markdown
## ⚠️ 暂时无法获取实时信息

{已知的基础信息或一般性说明}

**你可以尝试**：
1. {可执行的下一步 1}
2. {可执行的下一步 2}

---
💬 **你可能还想了解**
- {替代方案追问}
```

### 兜底格式规范（最低质量要求）
即使作为兜底，也必须满足：
- ✅ 第一行是 `## {emoji} {标题}`
- ✅ 关键数值加粗（如有）
- ✅ 有 `---` + `💬 **你可能还想了解**` 引导区
- ✅ 无 JSON 字段名泄漏
- ❌ 禁止纯散文无结构回复

## 参考资料
- `references/domain-knowledge.md`: 领域边界、关键槽位与风险约束
- `references/output-examples.md`: 标准输出与降级输出完整示例

## 脚本指引
- `scripts/tool-call-guidance.md`: 工具调用顺序、参数规范、重试与降级建议

## 轮次状态定义
- `dialogue/state_machine.md`: 轮次状态说明
- `dialogue/state_transition_contract.json`: 状态迁移与事件契约
- `dialogue/state_prompts.md`: 每个状态下的执行提示
