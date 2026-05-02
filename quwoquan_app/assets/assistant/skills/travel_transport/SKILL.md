---
name: travel_transport
description: 交通路线规划、地铁公交查询、打车叫车、导航。可打开导航App。
domain: travel_transport
mode: hybrid
allowed_tools: web_search
trigger_keywords: []
searchPolicy:
  maxReflection: 1
  qualityThreshold: 0.5
  strategy: realtime
requires:
  tools: [web_search]
  permissions: [location]
output_contract: assistant_turn
tool_observation_contract: tool_observation_v1
reference_docs: references/domain-knowledge.md references/output-examples.md
script_guides: references/tool-call-guidance.md
dialogue_state_docs: dialogue/state_machine.md dialogue/state_transition_contract.json dialogue/state_prompts.md
---

# 出行交通技能

## 目标
输出快速、清晰、实用的出行路线建议，始终采用双轨响应：
- 机器轨：结构化 JSON（含 decision、userMarkdown 等标准字段）
- 用户轨：可读 Markdown（进度说明 + 出行方案卡片）

## 工具调用策略
- 优先使用当前问句与记录记忆完成关键槽位补全（出发地/目的地/出行时间/偏好）。
- 仅在必要时调用工具，且必须遵守最小权限原则。
- 工具失败允许一次重试；失败后返回降级说明与下一步。

## 触发与禁用条件
- 触发信号：命中本技能关键词与领域语义。
- 禁用信号：明显属于其他垂类时不应强行触发。
- 竞争冲突：不确定时先 ask_user 澄清主诉求。

## 系统上下文约束
位置、时间、设备与权限信息统一来自系统默认注入上下文，不再通过额外工具读取。

## 双轨输出契约
若 nextAction 为 tool_call，必须同时返回：
1. 机器轨 JSON：包含 decision、toolCalls、slotState
2. 用户轨 Markdown：简短说明当前执行进度

若 nextAction 为 answer，机器轨标记完成，Markdown 输出出行方案卡片。

### 结构化 JSON 契约（必填字段）
```json
{
  "contractId": "assistant_turn",
  "decision": {"nextAction": "tool_call|answer|ask_user|retry|abort"},
  "slotState": {
    "origin": {"value": "", "source": "user_query|system_context|memory|unknown"},
    "destination": {"value": "", "source": "user_query|memory|unknown"},
    "departureTime": {"value": "", "source": "user_query|system_context|unknown"},
    "preference": {"value": "fastest", "source": "user_query|default"}
  },
  "toolCalls": [
    {"toolName": "web_search", "arguments": {"query": "深圳 福田 到 南山 地铁路线 换乘", "freshnessHoursMax": 24}}
  ],
  "askUser": {"slotId": "", "prompt": "", "required": false, "suggestions": []},
  "userMarkdown": "正在规划出行路线…"
}
```

## Markdown 卡片结构

### 主标题 emoji
`🚇` 地铁 · `🚌` 公交 · `🚕` 打车/网约车 · `🚄` 高铁/火车 · `🛵` 骑行 · `🚶` 步行

### 出行方案对比卡片结构
```markdown
## 🚇 {出发地} → {目的地} 出行方案

**出发时间**：**{HH:MM}** · **预计到达**：约 **{HH:MM}**

### 方案对比
| 方式 | 时长 | 费用 | 换乘/步行 | 推荐指数 |
|---|---|---|---|---|
| 🚇 地铁 | **{N} 分钟** | **¥{N}** | 换乘 {N} 次 | ⭐⭐⭐⭐⭐ |
| 🚕 打车 | **{N} 分钟** | **¥{N}~{N}** | 无 | ⭐⭐⭐⭐ |
| 🚌 公交 | **{N} 分钟** | **¥{N}** | 步行约 {N} 分钟 | ⭐⭐⭐ |

### 🥇 推荐方案：{交通方式}

**具体路线**：
1. {出发站/起点}，乘 **{线路名/方向}**
2. 在 **{换乘站}** 换乘 {线路名}（可选）
3. 到 **{终点站}**，步行约 **{N} 分钟**到达目的地

### 实用提示
- ⏰ {早晚高峰/大型活动/特殊情况说明}
- 💡 {省时/省钱/体验更好的小技巧}

> 出行实时路况以高德/百度地图为准，建议出发前再刷新确认。

---
💬 **你可能还想了解**
- 这条路线早晚高峰拥挤程度如何？
- 如果我想 **{时间}** 前到达，最晚几点出发？
- 返回的路线有推荐吗？
```

### 用户亲和性要求
- 给出多个方案让用户选择（最快/最省/最省力）
- 若出行时间在早晚高峰，主动提示拥挤情况和备选方案
- 对不熟悉城市的用户（外地/初来），增加"地铁 App 推荐"或"导航建议"
- 有携带大件行李/推婴儿车等特殊情况时，优先推荐无障碍路线

## 参考资料
- `references/domain-knowledge.md`: 领域边界、关键槽位与风险约束
- `references/output-examples.md`: 标准输出与降级输出完整示例

## 脚本指引
- `scripts/tool-call-guidance.md`: 工具调用顺序、参数规范、重试与降级建议

## 轮次状态定义
- `dialogue/state_machine.md`: 轮次状态说明
- `dialogue/state_transition_contract.json`: 状态迁移与事件契约
- `dialogue/state_prompts.md`: 每个状态下的执行提示
