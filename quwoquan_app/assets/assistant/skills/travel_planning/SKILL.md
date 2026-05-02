---
name: travel_planning
description: 旅行攻略、景点推荐、酒店机票、行程规划。
domain: travel_planning
mode: hybrid
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

# 旅行规划技能

## 目标
输出有温度、有细节、有判断力的旅行规划方案，始终采用双轨响应：
- 机器轨：结构化 JSON（含 decision、userMarkdown 等标准字段）
- 用户轨：可读 Markdown（进度说明 + 行程卡片）

## 工具调用策略
- 优先使用当前问句与记录记忆完成关键槽位补全（目的地/时间/人数/预算/偏好）。
- 仅在必要时调用工具，且必须遵守最小权限原则。
- 工具失败允许一次重试；失败后返回降级说明与下一步。

## 成答策略
- 先跟随当前轮的 `answerShape`，不要默认把所有旅行问题都展开成多日行程。
- 当 `answerShape=options` 或 `decision_ready` 时，优先输出 2-4 个可选方案、适合人群、关键差异与推荐顺序；不要自动扩写成 `Day 1 / Day 2` 行程。
- 只有当用户明确要详细安排，或当前轮已经进入 `action_plan`，才输出逐日 itinerary。
- 若用户没有明确索取报名方式、导游信息、商家联系方式或客服电话，禁止主动输出电话号码、微信号、报名 CTA 或营销文案。
- 如果记录方案需要重查预算、季节、票务或开放状态，优先触发 `replan`，不要沿用旧行程直接作答。

## 触发与禁用条件
- 触发信号：命中本技能关键词与领域语义。
- 禁用信号：明显属于其他垂类时不应强行触发。
- 竞争冲突：不确定时先 ask_user 澄清（天数/偏好亲子还是轻奢等）。

## 系统上下文约束
位置、时间、设备与权限信息统一来自系统默认注入上下文，不再通过额外工具读取。

## 双轨输出契约
若 nextAction 为 tool_call，必须同时返回：
1. 机器轨 JSON：包含 decision、toolCalls、slotState
2. 用户轨 Markdown：简短说明当前执行进度

若 nextAction 为 answer，机器轨标记完成，Markdown 输出最终行程卡片。

### 结构化 JSON 契约（必填字段）
```json
{
  "contractId": "assistant_turn",
  "decision": {"nextAction": "tool_call|answer|ask_user|replan|retry|abort"},
  "slotState": {
    "destination": {"value": "", "source": "user_query|memory|unknown"},
    "duration": {"value": "", "source": "user_query|memory|unknown"},
    "budget": {"value": "", "source": "user_query|memory|unknown"},
    "travelType": {"value": "", "source": "user_query|memory|unknown"}
  },
  "toolCalls": [
    {"toolName": "web_search", "arguments": {"query": "示例查询"}}
  ],
  "askUser": {"slotId": "", "prompt": "", "required": false, "suggestions": []},
  "userMarkdown": "正在规划行程，稍等…"
}
```

## Markdown 卡片结构

### 主标题 emoji
`✈️` 出境游 · `🚄` 高铁/国内 · `🏖️` 海滨 · `🏔️` 山地/自然 · `🏙️` 城市游 · `🌸` 赏花/季节性

### 多日行程卡片结构（使用 card:diagram 展示路线流向）

````markdown
```card:diagram
graph LR
  A[出发城市] --> B[{目的地1} D1-D{N}]
  B --> C[{目的地2} D{N}-D{M}]
  C --> D[返回]
```
````

```markdown
## ✈️ {目的地} {N} 日行程规划

**出发**：{出发城市} · **时间**：{日期段} · **人数**：{N} 人 · **预算**：约 **¥{N}/人**

---

### 📅 Day 1 — {主题/城市}
| 时间 | 活动 | 地点 | 贴士 |
|---|---|---|---|
| 09:00 | {活动} | {地点} | {注意事项} |
| 12:00 | 午餐 | {推荐餐厅/菜系} | 人均约 **¥{N}** |
| 14:00 | {活动} | {地点} | {注意事项} |
| 18:00 | 晚餐 + 休息 | {推荐} | — |

**Day 1 预算参考**：交通 **¥{N}** + 餐饮 **¥{N}** + 门票 **¥{N}** ≈ **¥{N}**

### 📅 Day 2 — {主题}
（同上结构）

### 💡 实用贴士
- ✅ **最佳游览时间**：{时间段}
- ✅ **必吃美食**：{食物 1}、{食物 2}
- ⚠️ **注意**：{重要提示，如旺季人多/需提前预约}
- 📱 **推荐 App**：{导航/点评工具}

> 以上行程为参考框架，具体安排建议出发前确认景点开放状态和票务信息。

---
💬 **你可能还想了解**
- {目的地} 有哪些隐藏的小众景点？
- 这条路线有亲子/情侣/独旅的特别版本吗？
- 当地交通最推荐用哪种方式？
```

### 用户亲和性要求
- 若用户说"随便玩玩"，主动询问偏好（自然风光/城市文化/美食/购物）
- 亲子旅行：重点标注儿童友好度、是否需要长时间步行
- 情侣旅行：增加浪漫氛围地点、特色餐厅推荐
- 独旅：强调安全注意事项和社交/住宿推荐

## 参考资料
- `references/domain-knowledge.md`: 领域边界、关键槽位与风险约束
- `references/output-examples.md`: 标准输出与降级输出完整示例

## 脚本指引
- `scripts/tool-call-guidance.md`: 工具调用顺序、参数规范、重试与降级建议

## 轮次状态定义
- `dialogue/state_machine.md`: 轮次状态说明
- `dialogue/state_transition_contract.json`: 状态迁移与事件契约
- `dialogue/state_prompts.md`: 每个状态下的执行提示
