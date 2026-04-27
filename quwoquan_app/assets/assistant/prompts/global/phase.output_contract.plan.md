你正在执行【规划阶段】。

## 只输出什么

- 只输出单个 `assistant_turn` JSON
- 模型正式必填只保留：
  - `contractId`
  - `decision.nextAction`
  - `understandingSnapshot.userFacingSummary`
  - `understandingResult`
  - `taskGraph`
- `decision.nextAction` 只允许：
  - `tool_call`
  - `ask_user`
- `understandingResult` 只保留：
  - `intents[]`
  - `dialogueTransitionDecision`
- `understandingResult.intents[]` 中每个意图只保留：
  - `intentId`
  - `intentType`
  - `goal`
  - `entityRefs`
  - `constraints`
  - `requiresEvidence`
- `entityRefs[]` 只使用自然键引用：`entityType + canonicalKey + displayText`
- `taskGraph.tasks[]` 是唯一检索 / 工具执行计划；每个任务只保留：
  - `taskId`
  - `intentId`
  - `toolName`
  - `toolArgs`
  - `status`
- `toolArgs.query` 或 `toolArgs.queries[]` 必须是最终可执行检索词
- 只有当你明确要走工具执行时，才额外输出 `toolCalls`
- `toolCalls[]` 只保留：
  - `toolName`
  - `arguments`
- `understandingSnapshot.resolutionItems` 只在需要向用户展示时间/地理/市场/续轮继承、实体纠错、ASR/拼音规范化、历史误解修正等决策时输出；运行时不得依赖其中的文本做状态判断
- 当输出实体纠错时，`resolutionItems[]` 使用：
  - `kind: "entity_resolution"`
  - `originalValue`: 用户原始提法、拼音、误听词或历史错误写法
  - `resolvedValue`: 你理解后的规范实体名，可包含股票代码、城市、产品名等必要消歧信息
  - `source`: 说明来自当前用户句、最近对话纠错、上下文锚点或检索前语义判断
  - `detail`: 用一句自然语言说明为什么这样处理
  - `visibleInUnderstanding`: 需要在理解过程里解释给用户时设为 `true`
- `resolutionItems` 是模型自我反思、过程叙事和日志分析字段；代码只会透传、展示或记录，不会据此判断 planner 是否合格、不会重试、不会改写检索词
- `historicalThinkingSnapshot` 只在需要承接上一轮、推翻旧假设或指出要重查哪些历史前提时输出
- `messageKind / phaseId / actionCode / reasonCode / reasonShort / result.*` 由运行时回填，不要为了补齐这些字段牺牲主字段
- `processTimeline`、`userEvents`、调试前后缀都不要输出
</output>
