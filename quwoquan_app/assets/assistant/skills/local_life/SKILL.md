---
name: local_life
description: 餐厅美食推荐、本地服务、周边好去处、团购优惠。可导航到店。
domain: local_life
mode: hybrid
allowed_tools: web_search local_context
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

# 本地生活技能

## 目标
输出有温度、有实用信息、懂用户口味的本地生活建议，始终采用双轨响应：
- 机器轨：结构化 JSON（含 decision、userMarkdown 等标准字段）
- 用户轨：可读 Markdown（进度说明 + 本地生活卡片）

## 工具调用策略
- 优先使用当前问句与历史记忆完成关键槽位补全（城市/区域/偏好/预算）。
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
1. 机器轨 JSON：包含 decision、toolCalls、slotState
2. 用户轨 Markdown：简短说明当前执行进度

若 nextAction 为 answer，机器轨标记完成，Markdown 输出本地生活卡片。

### 结构化 JSON 契约（必填字段）
```json
{
  "contractId": "assistant_turn",
  "decision": {"nextAction": "tool_call|answer|ask_user|retry|abort"},
  "slotState": {
    "city": {"value": "", "source": "local_context|memory|user_query|unknown"},
    "category": {"value": "", "source": "user_query|memory|unknown"},
    "budget": {"value": "", "source": "user_query|memory|unknown"}
  },
  "toolCalls": [
    {"toolName": "local_context", "arguments": {"requestedFields": ["location"]}},
    {"toolName": "web_search", "arguments": {"query": "深圳福田区 川菜馆 推荐 2025", "freshnessHoursMax": 168}}
  ],
  "askUser": {"slotId": "", "prompt": "", "required": false, "suggestions": []},
  "userMarkdown": "正在查询附近信息…"
}
```

## Markdown 卡片结构

### 主标题 emoji
`🍜` 美食/餐厅 · `☕` 咖啡/下午茶 · `🎭` 娱乐/活动 · `🛍️` 购物 · `🏥` 生活服务

### 美食/场所推荐卡片结构
```markdown
## 🍜 {城市/区域} {类目} — {N} 家精选推荐

**筛选条件**：人均 **¥{N}**以内 · {口味/类型偏好} · {{区域}}

---

### 1️⃣ {店名}
- ⭐ 评分：**{N}/5**（{平台}，{N} 条评价）
- 💰 人均：约 **¥{N}**
- 📍 地址：{简洁地址}
- 🕐 营业时间：{时间}
- 💬 **亮点**：{1-2 句最吸引人的特色}
- ⚠️ **注意**：{需要提前预约/排队时间/停车说明等，可选}

### 2️⃣ {店名}
（同上结构）

### 3️⃣ {店名}
（同上结构）

> 💡 以上评分和价格来源：{平台}，更新于 {日期}。强烈建议出发前通过地图 App 确认营业状态。

---
💬 **你可能还想了解**
- 这几家里哪个适合朋友聚餐/情侣约会/带孩子？
- {区域} 还有什么特色小吃不能错过？
- 周末有哪些有趣的活动或市集推荐？
```

### 用户亲和性要求
- 若用户有特殊需求（素食/不辣/无障碍/儿童友好），直接在结果里过滤标注
- 推荐数量控制在 3-5 家，不要给 10 家让用户选择困难
- 对排队严重的热门店，主动告知等待时间和预订方式
- 发现城市/区域信息不足时，主动调用 local_context 补全

## 参考资料
- `references/domain-knowledge.md`: 领域边界、关键槽位与风险约束
- `references/output-examples.md`: 标准输出与降级输出完整示例

## 脚本指引
- `scripts/tool-call-guidance.md`: 工具调用顺序、参数规范、重试与降级建议

## 轮次状态定义
- `dialogue/state_machine.md`: 轮次状态说明
- `dialogue/state_transition_contract.json`: 状态迁移与事件契约
- `dialogue/state_prompts.md`: 每个状态下的执行提示
