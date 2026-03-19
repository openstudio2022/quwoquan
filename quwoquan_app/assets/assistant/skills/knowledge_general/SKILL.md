---
name: knowledge_general
description: 百科知识、原理解释、科普、概念辨析、翻译。
domain: knowledge_general
mode: qa
tool_chain_profile: knowledge_qa
allowed_tools: web_search
trigger_keywords: []
searchPolicy:
  maxReflection: 2
  qualityThreshold: 0.5
  strategy: research
requires:
  tools: [web_search]
output_contract: assistant_turn
tool_observation_contract: tool_observation_v1
reference_docs: references/domain-knowledge.md references/output-examples.md
script_guides: references/tool-call-guidance.md
dialogue_state_docs: dialogue/state_machine.md dialogue/state_transition_contract.json dialogue/state_prompts.md
---

# 通识问答技能

## 目标
输出准确、易懂、有深度的知识解答，始终采用双轨响应：
- 机器轨：结构化 JSON（含 decision、userMarkdown 等标准字段）
- 用户轨：可读 Markdown（进度说明 + 知识卡片）

## 工具调用策略
- 优先使用当前问句与历史记忆完成关键槽位补全。
- 仅在必要时调用工具，且必须遵守最小权限原则。
- 工具失败允许一次重试；失败后返回降级说明与下一步。

## 触发与禁用条件
- 触发信号：命中本技能关键词与领域语义。
- 禁用信号：明显属于其他垂类时不应强行触发。
- 竞争冲突：不确定时先 ask_user 澄清主诉求。

## 双轨输出契约
若 nextAction 为 tool_call，必须同时返回：
1. 机器轨 JSON：包含 decision、toolPlan、slotState
2. 用户轨 Markdown：简短说明当前执行进度

若 nextAction 为 answer，机器轨标记完成，Markdown 输出知识卡片。

### 结构化 JSON 契约（必填字段）
```json
{
  "contractId": "assistant_turn",
  "decision": {"nextAction": "tool_call|answer|ask_user|retry|abort"},
  "slotState": {
    "topic": {"value": "", "source": "user_query|memory|unknown"}
  },
  "toolPlan": [
    {"toolName": "web_search", "arguments": {"query": "示例查询"}}
  ],
  "askUser": {"slotId": "", "prompt": "", "required": false, "suggestions": []},
  "userMarkdown": "正在检索权威资料…"
}
```

## Markdown 卡片结构

### 主标题 emoji
`🔬` 科学/技术 · `📜` 历史/人文 · `🌍` 地理/自然 · `🧮` 数学/逻辑 · `💡` 通用知识

### 知识解析卡片结构
```markdown
## 🔬 {知识点名称} — 一分钟解读

**核心答案**：{用 1-2 句话直接回答，结论前置}

### 深入理解
{原理/背景/机制，2-3 段，每段聚焦一个层面，先日常类比后专业表述}

### 关键要点
- **{要点 1}**：{简要说明}
- **{要点 2}**：{简要说明}
- **{要点 3}**：{简要说明，可选}

### 代码/公式（如适用）
```
{代码示例或推导步骤，逐行注释}
```

> 💡 来源：{权威来源}。知识内容以学术界主流观点为准，如有争议会标注。

---
💬 **你可能还想了解**
- {相关延伸知识 1}
- {实际应用场景：这个知识在哪里用到了？}
- {反直觉追问：有没有和这个相反的例子？}
```

### 用户亲和性要求
- 回答深浅度匹配用户问法（"简单说"对应简洁版，"详细解释"对应深度版）
- 多用**日常类比**让抽象概念具体化，再给专业说明
- 对"为什么"类问题，要解释**机制**而不只是罗列现象
- 避免堆砌术语，必须用术语时附括号解释

## 参考资料
- `references/domain-knowledge.md`: 领域边界、关键槽位与风险约束
- `references/output-examples.md`: 标准输出与降级输出完整示例

## 脚本指引
- `scripts/tool-call-guidance.md`: 工具调用顺序、参数规范、重试与降级建议

## 轮次状态定义
- `dialogue/state_machine.md`: 轮次状态说明
- `dialogue/state_transition_contract.json`: 状态迁移与事件契约
- `dialogue/state_prompts.md`: 每个状态下的执行提示
