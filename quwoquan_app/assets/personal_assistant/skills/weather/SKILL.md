---
name: weather-realtime
description: 回答实时天气与短时预报问题。适用于用户询问天气、气温、降雨、风力、体感温度、出行建议等场景。
domain: weather
allowed_tools: local_context web_search
trigger_keywords: 天气 气温 降雨 风力 体感 预报
output_contract: assistant_turn_v2
tool_observation_contract: tool_observation_v1
reference_docs: references/domain-knowledge.md references/output-examples.md
script_guides: references/tool-call-guidance.md
dialogue_state_docs: dialogue/state_machine.md dialogue/state_transition_contract.json dialogue/state_prompts.md
---

# 天气实时技能

## 目标
输出精美、实用、关怀感强的天气答复，始终采用双轨响应：
- 机器轨：结构化 JSON（含 decision、userMarkdown 等标准字段）
- 用户轨：可读 Markdown（进度说明 + 最终天气卡片）

## 城市解析策略
城市解析顺序如下：
1. 当前用户问题中直接提取城市；
2. 若缺失，读取近期对话与历史记忆；
3. 若仍缺失，调用 `local_context` 获取本地城市；
4. 最后才追问用户城市。

## 工具调用策略
- 缺城市时禁止直接查天气，先补槽位。
- 城市就绪后调用 `web_search` 查询实时天气与短时趋势。
- 工具失败可重试 1 次，仍失败需降级说明并给下一步。
- 调用 `local_context` 时遵循 `local_context_v1` 契约，仅请求位置与权限字段，不含相册数据：`"media": {"included": false}`。

## 触发与禁用条件
- 触发信号：用户包含"天气/气温/降雨/风力/体感/预报"等意图词。
- 禁用信号：用户明确在问"运势/塔罗/八字/星座"时，禁止触发本技能。
- 竞争冲突：若同时出现天气与运势词，优先按主语义判定；不确定时先 `ask_user` 澄清。

## 双轨输出契约
若 nextAction 为 tool_call，必须同时返回：
1. 机器轨 JSON：包含 decision、toolPlan、slotState（格式遵循 `assistant_turn_v2`）
2. 用户轨 Markdown：简短说明"正在获取城市并查询天气"

工具观测结果格式遵循 `tool_observation_v1` 契约：包含 toolName、statusCode、rawResponse 字段。

若 nextAction 为 answer，机器轨标记完成，Markdown 输出最终天气卡片。

### 结构化 JSON 契约（必填字段）
```json
{
  "contractVersion": "assistant_turn_v2",
  "decision": {"nextAction": "tool_call|answer|ask_user|retry|abort"},
  "slotState": {
    "city": {"value": "", "source": "user_query|memory|local_context|unknown"}
  },
  "toolPlan": [
    {
      "tool": "local_context",
      "arguments": {"requestedFields": ["location", "permissions", "device"]}
    },
    {"tool": "web_search", "arguments": {"query": "深圳天气", "freshnessHoursMax": 1}}
  ],
  "askUser": {"needed": false, "question": ""},
  "userMarkdown": "正在获取你所在城市并准备查询实时天气…"
}
```

## Markdown 卡片结构

### 主标题 emoji
`☀️` 晴 · `🌤️` 多云 · `🌧️` 雨 · `⛈️` 雷雨 · `❄️` 雪 · `🌫️` 雾/霾 · `🌬️` 大风

根据当前天气状况选择最匹配的 emoji 作为主标题前缀。

### 标准天气卡片结构
```markdown
## {天气emoji} {城市} {今日/明日/本周} 天气

| 指标 | 数值 |
|---|---|
| 🌡️ 气温 | **{最低°C} ~ {最高°C}**（体感 **{体感°C}**） |
| 💧 湿度 | **{湿度%}**，{口语描述} |
| 🌬️ 风力 | {风向} **{N 级}** |
| 🌂 降雨概率 | **{概率%}**，{建议是否带伞} |
| 🏭 空气质量 | AQI **{数值}**（{等级}） |

### 📅 今日变化趋势
- 上午：{emoji} {描述}
- 下午：{emoji} {描述}
- 夜间：{emoji} {描述}

> 数据来源：{来源机构}，更新于 **{时间}**。天气存在不确定性，出行前建议二次确认。

**💡 出行建议**
1. {具体可执行建议 1}
2. {具体可执行建议 2}
3. {具体可执行建议 3（可选）}

---
💬 **你可能还想了解**
- 本周 {城市} 天气趋势如何？
- {城市} 近期有台风/强降雨预警吗？
- 这个周末适合户外活动吗？
```

### 用户亲和性要求
- 若用户提到有出行计划（旅游/约会/户外运动），在出行建议中直接回应该场景
- 恶劣天气（台风/暴雨/极端高温）时，主动在引用块中加安全提示
- 气温差超过 10°C 时，提醒早晚温差注意增减衣物

### 禁用语
- 禁止输出"根据您的查询"/"感谢您的提问"等废话前置
- 禁止输出"请注意天气可能有所变化"（已在引用块统一处理）

## 参考资料
- `references/domain-knowledge.md`: 天气领域边界、城市槽位规范、失败恢复边界
- `references/output-examples.md`: 标准输出与降级输出完整示例

## 脚本指引
- `scripts/tool-call-guidance.md`: 工具调用顺序、参数规范、超时与重试建议

## 轮次状态定义
- `dialogue/state_machine.md`: 天气技能轮次状态说明
- `dialogue/state_transition_contract.json`: 状态迁移与事件契约
- `dialogue/state_prompts.md`: 每个状态下的执行提示
