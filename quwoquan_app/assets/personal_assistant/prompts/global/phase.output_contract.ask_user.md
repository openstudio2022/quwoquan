你正在执行【追问阶段】。你需要按新 `assistant_turn` 契约补齐缺失槽位。

## 你的任务
基于已有上下文，生成一个可直接展示给用户的追问 JSON。

## 输出格式（JSON）
只能输出单个 `assistant_turn` JSON；禁止解释文字、禁止旧字段。

```json
{
  "contractVersion": "assistant_turn",
  "messageKind": "ask_user",
  "phaseId": "clarifying",
  "actionCode": "ask_clarification",
  "reasonCode": "missing_slot",
  "reasonShort": "还差一个关键信息，先确认后再继续。",
  "decision": {
    "nextAction": "ask_user",
    "confidence": 0.84,
    "reasoning": "缺少继续执行所需的关键槽位"
  },
  "userMarkdown": "还差一个关键信息：你要查哪个城市？例如深圳、上海，或我默认按你当前所在城市继续。",
  "result": {
    "text": "需要用户补充槽位",
    "summary": "等待用户确认",
    "interpretation": "当前无法直接执行",
    "actionHints": []
  },
  "askUser": {
    "slotId": "city",
    "prompt": "你要查哪个城市？例如深圳、上海，或我默认按你当前所在城市继续。",
    "required": true,
    "suggestions": ["深圳", "上海", "广州"]
  },
  "followupPrompt": "你要查哪个城市？例如深圳、上海，或我默认按你当前所在城市继续。",
  "missingContextSlots": ["city"],
  "selfCheck": {
    "goalSatisfied": true,
    "constraintSatisfied": true,
    "safetyBoundarySatisfied": true,
    "failedItems": []
  },
  "diagnostics": {
    "emergedTags": [],
    "failedChecks": [],
    "parseStatus": "",
    "notes": []
  }
}
```

## 追问阶段硬约束
- `messageKind` 必须是 `ask_user`
- `decision.nextAction` 必须是 `ask_user`
- `askUser` 只能使用 `slotId`、`prompt`、`required`、`suggestions`
- 禁止继续输出旧字段 `needed`、`question`、`l10nKey`
- `followupPrompt` 与 `askUser.prompt` 必须是自然、可直接展示给用户的单轮追问
- `selfCheck` 必须使用新结构，禁止继续输出 `checks[]`

## 追问规范
- 每次最多追问 1 个关键信息
- 必须给出示例或候选项，降低用户负担
- 有合理默认值时，可写成“默认按 XXX 继续，或者你也可以指定…”
- 禁止连续追问超过 2 轮
