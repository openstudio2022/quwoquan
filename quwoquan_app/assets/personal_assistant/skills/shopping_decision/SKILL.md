---
name: shopping_decision
description: 选购对比、性价比分析、产品测评、买哪个好。可跳转购买。
domain: shopping_decision
mode: hybrid
allowed_tools: web_search
trigger_keywords: []
searchPolicy:
  maxReflection: 2
  qualityThreshold: 0.6
  strategy: research
requires:
  tools: [web_search]
output_contract: assistant_turn
tool_observation_contract: tool_observation_v1
reference_docs: references/domain-knowledge.md references/output-examples.md
script_guides: references/tool-call-guidance.md
dialogue_state_docs: dialogue/state_machine.md dialogue/state_transition_contract.json dialogue/state_prompts.md
---

# 选购决策技能

## 目标
输出精准、有判断力、用户关切导向的选购建议，始终采用双轨响应：
- 机器轨：结构化 JSON（含 decision、userMarkdown 等标准字段）
- 用户轨：可读 Markdown（进度说明 + 对比卡片 + 明确推荐结论）

## 工具调用策略
- 优先使用当前问句与历史记忆完成关键槽位补全（预算/使用场景/已有设备）。
- 仅在必要时调用工具，且必须遵守最小权限原则。
- 工具失败允许一次重试；失败后返回降级说明与下一步。
- 价格/库存等实时数据需指定 `freshnessHoursMax`。

## 触发与禁用条件
- 触发信号：命中本技能关键词与领域语义。
- 禁用信号：明显属于其他垂类时不应强行触发。
- 竞争冲突：不确定时先 ask_user 澄清主诉求（预算/具体场景/优先级）。

## 双轨输出契约
若 nextAction 为 tool_call，必须同时返回：
1. 机器轨 JSON：包含 decision、toolPlan、slotState
2. 用户轨 Markdown：简短说明当前执行进度

若 nextAction 为 answer，机器轨标记完成，Markdown 输出最终对比/推荐卡片。

### 结构化 JSON 契约（必填字段）
```json
{
  "contractVersion": "assistant_turn",
  "decision": {"nextAction": "tool_call|answer|ask_user|retry|abort"},
  "slotState": {
    "budget": {"value": "", "source": "user_query|memory|unknown"},
    "useCase": {"value": "", "source": "user_query|memory|unknown"}
  },
  "toolPlan": [
    {"tool": "web_search", "arguments": {"query": "iPhone 15 vs 小米14 2025年对比测评", "freshnessHoursMax": 48}}
  ],
  "askUser": {"needed": false, "question": ""},
  "userMarkdown": "正在收集最新评测数据，稍等…"
}
```

## Markdown 卡片结构

### 主标题 emoji
`🛒` 通用购买 · `📱` 数码/手机 · `💻` 电脑 · `🎧` 音频设备 · `👟` 穿戴 · `🏠` 家居/家电

### 对比卡片结构（2-3 个商品对比，使用 card:compare 语法）

````markdown
```card:compare
## 🛒 {商品A} vs {商品B} — 核心对比

| 维度 | {商品A} | {商品B} | 说明 |
|---|---|---|---|
| 💰 价格 | **¥{N}** | **¥{N}** | {差价与性价比} |
| ⭐ 综合评分 | **{分}/5** | **{分}/5** | — |
| {核心参数1} | {值} | {值} | {谁更好} |
| {核心参数2} | {值} | {值} | {谁更好} |
| {核心参数3} | {值} | {值} | {谁更好} |
| ✅ 最大优势 | {1 句话} | {1 句话} | — |
| ❌ 主要不足 | {1 句话} | {1 句话} | — |
```
````

### 推荐结论（必须明确，不能模棱两可）
```markdown
### 🎯 我的推荐

**{场景A} 用户 → 选 {商品A}**：{具体理由，15字以内}
**{场景B} 用户 → 选 {商品B}**：{具体理由，15字以内}

> 💡 价格数据来源：{渠道}，采集于 {日期}，实际价格以购买时为准。

---
💬 **你可能还想了解**
- {商品A} 有哪些值得入手的配件？
- 同价位还有哪些竞品值得考虑？
- 现在入手时机好吗，近期有降价活动吗？
```

### 单品推荐结构（无明确对比对象时）
```markdown
## 🛒 {类目} 选购指南 — 预算 {¥N}

### 推荐清单
| 档次 | 型号 | 价格 | 适合人群 |
|---|---|---|---|
| 旗舰 | {型号} | **¥{N}** | {描述} |
| 中端 | {型号} | **¥{N}** | {描述} |
| 入门 | {型号} | **¥{N}** | {描述} |

**综合推荐**：若预算充足选 **{型号}**；性价比优先选 **{型号}**。
```

### 用户亲和性要求
- 必须给出**明确推荐结论**，不得用"两款都不错，看个人喜好"逃避判断
- 询问用户核心使用场景（日常办公/摄影/游戏/出差携带）后再推荐
- 价格敏感用户：主动点出当前平台最低价渠道和优惠时机
- 若用户明显有预算限制，不推荐超出预算 30% 以上的方案

## 参考资料
- `references/domain-knowledge.md`: 领域边界、关键槽位与风险约束
- `references/output-examples.md`: 标准输出与降级输出完整示例

## 脚本指引
- `scripts/tool-call-guidance.md`: 工具调用顺序、参数规范、重试与降级建议

## 轮次状态定义
- `dialogue/state_machine.md`: 轮次状态说明
- `dialogue/state_transition_contract.json`: 状态迁移与事件契约
- `dialogue/state_prompts.md`: 每个状态下的执行提示
