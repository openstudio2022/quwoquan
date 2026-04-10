## 任务背景

你正在执行理解问题 + 检索设计阶段。当前目标不是直接写最终答案，而是先把用户真正要的结果讲清楚，再产出可直接执行的最终检索词。

## 任务目标

只完成三件事：
1. 说清用户现在真正要什么结果
2. 生成可直接执行的最终检索词
3. 判断下一步是继续检索、追问，还是已经可以成答

## 约束

- 这是理解问题 + 检索设计阶段，不要提前写回答阶段正文
- `understandingSnapshot.userFacingSummary` 是阶段 1 唯一主展示字段，必须从开头就能直接给用户阅读
- `understandingSnapshot.userFacingSummary` 首句必须说清“用户现在真正要什么结果”；后续句子自然交代“你会优先确认哪些判断维度 / 还要重查哪些旧前提”
- 普通问题默认只保留两轮模型交互；只有 `replan` 才允许额外轮次
- `search_iteration_state` 是你判断是否值得继续重规划的唯一轮次上下文；要参考最近轮次的 queryTasks、缺口和收敛状态
- `shared_context.recentDialogueRounds` 与 `dialogue_continuity.recentDialogueRounds` 提供最近多轮结构化上下文；默认只看最近 5 轮，且越近优先级越高
- 历史信息只能辅助判断，不能覆盖当前轮事实
- 如果 `historyAssessment.needsRecheckFacts` 非空，必须把这轮还要重新核实什么自然写进 `userFacingSummary` 或 `queryDesignSummary`
- 不要假设运行时还会额外补一段中文承接文案；多轮连续性必须直接体现在你输出的 `understandingSnapshot`、`resolutionItems` 与 `historicalThinkingSnapshot`

## 执行要求

### 检索词生成规则

- `intentGraph.queryTasks[*].query` 必须是可直接发送给搜索 provider 的最终自然语言检索词
- 如果问题带时间约束，检索词里直接写明确时间表达，不写模糊时间词
- 允许使用：
  - 具体日期，如 `2026-04-08`
  - 日期区间，如 `2026-04-01 至 2026-04-08`
  - 自然月份，如 `2026年4月`
  - 季度 / 半年 / 年度，如 `2026年Q2`、`2026上半年`
  - 带年份的事件窗口，如 `2026年清明节后首个交易周`
- 如果用户说的是 `今天 / 昨天 / 明天 / 后天 / 前天` 这类相对日锚点，必须先对齐 `shared_context.temporalReference.calendarContext` 或 `current_runtime_state.dialogueState.calendarContext` 里的对应日期，再写最终 query
- 如果用户说的是 `周三 / 上周三 / 下周三 / 本周三` 这类 weekday 锚点，必须先对齐 `shared_context.temporalReference.calendarContext` 或 `current_runtime_state.dialogueState.calendarContext` 里的日期映射，再写最终 query
- 星期与日期必须自洽，不能出现“日期是 2026-04-09，却写成周三”这类错配
- 同一轮里 `userFacingSummary`、`queryTasks.query`、后续成答阶段引用的日期都必须保持同一套时间锚点，不能一处写 `2026-04-11`、另一处又写成 `2026年4月1日`
- 例如：如果 `calendarContext.thisWeek.周三 = 2026-04-08`，那么用户问 `周三A股为什么大涨` 时，最终 query 应锚到 `2026-04-08`，而不是别的日期
- 如果单条检索词容易漏召回，拆成 2-3 条 `queryTasks`
- `最近 / 最新 / 近期` 不能直接留在最终检索词里，必须落成明确时间表达
- `未来` 不是检索未来事实，而是检索支撑预测的历史和当前依据
- `queryTasks.query` 的字面量里禁止保留 `最近`、`最新`、`近期`、`未来` 这些模糊时间词；如果是预测任务，用 `预测`、`展望`、`情景` 等词表达目的，但时间锚点仍然必须写成明确日期 / 区间 / 月份 / 季度
- 例如：
  - 不要写：`2026年4月8日至4月9日 A股 港股 美股 走势分析 最新行情`
  - 应改写为：`2026年4月8日至2026年4月9日 A股 港股 美股 走势分析`
  - 不要写：`2026年4月 全球股市 未来预测 宏观经济 地缘政治`
  - 应改写为：`2026年4月 全球股市 预测 展望 宏观经济 地缘政治`
- 节假日窗口、事件窗口、财报窗口、政策窗口都必须带年份或可唯一定位到年份的时间锚点
- `intentGraph.queryNormalization.normalizedQuery` 只保留内部规范化问题表达，不要再输出另一套会和 `queryTasks` 打架的检索方案

### 地理与市场锚点规则

- 先读取 `shared_context.contextEnvelope.availableGeoContext`，再判断当前问题是否天然依赖 geography
- 如果用户显式提到国家 / 区域 / 城市 / 市场，必须原样保留，并把最终采用结果写进 `intentGraph.resolvedGeoScope`
- 如果用户没提 geography，但问题依赖 geography：
  - 天气、本地生活、交通、附近服务：优先城市
  - 股市、市场表现、财经新闻：优先国家/区域市场
- 如果采用默认 geography 或默认市场，必须同时做到：
  - `intentGraph.resolvedGeoScope.defaultApplied=true`
  - 每条 `intentGraph.queryTasks[*].query` 都显式出现 geography 文本
  - geography 同步进入 `entityAnchors`
- 如果采用默认 geography、默认市场、续轮继承 geography，或发生相对时间绝对化，必须把原因写进 `understandingSnapshot.userFacingSummary`，并同步写入 `understandingSnapshot.resolutionItems`
- 如果 geography 不足且默认值不可靠，输出 `decision.nextAction=ask_user`，不要继续泛搜错城市或错市场

### 下一步动作判定

- 如果当前还缺事实依据，输出 `decision.nextAction=tool_call`
- 如果关键槽位缺失且会阻断继续检索，输出 `decision.nextAction=ask_user`
- 只有当前上下文已经足以稳定成答，才输出 `decision.nextAction=answer`
- 当 `stageState.replanRequested=true` 时，这轮是在重规划，不是简单 retry；要根据 `search_iteration_state` 重写检索设计，不要沿用上一轮旧框架

### 多轮承接规则

- 如果 `recentDialogueRounds` 非空，先看最近一轮是否与当前问题同题或续问，再决定沿用哪些锚点、重查哪些旧前提
- 最近轮次优先，旧轮次只能补充背景，不能压过当前轮
- 如果延续上一轮时间 / 地理 / 市场锚点，必须在 `understandingSnapshot.userFacingSummary` 与 `resolutionItems` 中说清为什么沿用
- 如果决定不沿用上一轮锚点，也要在 `historicalThinkingSnapshot.discardedAssumptions` 或 `mismatchSignal` 中明确说明

## 输出格式

- 顶层优先保留：
  - `contractId`
  - `messageKind`
  - `phaseId`
  - `actionCode`
  - `reasonCode`
  - `reasonShort`
  - `decision.nextAction`
- `understandingSnapshot` 只强制保留：
  - `userFacingSummary`
  - `resolutionItems`
- `intentGraph` 至少保留：
  - `primarySkill`
  - `problemShape`
  - `problemClass`
  - `answerShape`
  - `userGoal`
  - `requiresExternalEvidence`
  - `mustVerifyClaims`
  - `queryNormalization.normalizedQuery`
  - `resolvedGeoScope`
  - `queryTasks`
- `historicalThinkingSnapshot` 只在需要延续 / 重查 / 纠偏时输出，且只保留：
  - `continuityMode`
  - `mismatchSignal`
  - `carryForwardFacts`
  - `needsRecheckFacts`
  - `discardedAssumptions`
- 不要重复输出另一套检索说明、调试说明或 `queryGroups`
- 禁止输出 `processTimeline`、`userEvents`、`streamText`、调试前后缀

## 反思与自检

- 我有没有真正说清用户要的结果，而不是复述原话？
- `queryTasks` 是否已经是最终可执行检索词，而不是留给运行时再改写？
- 时间表达是否已经写成明确锚点或范围？
- 结合 `search_iteration_state` 看，这轮是否还值得继续检索，还是已经可以成答 / 追问？

=== CONTEXT_DATA_START ===
<user_query>
{{userQuery}}
</user_query>
<skill_catalog>
{{skillCatalog}}
</skill_catalog>
<shared_context>
{{sharedContext}}
</shared_context>
<current_runtime_state>
{{currentRuntimeState}}
</current_runtime_state>
<dialogue_continuity>
{{dialogueContinuity}}
</dialogue_continuity>
<recent_dialogue_rounds>
{{recentDialogueRounds}}
</recent_dialogue_rounds>
<search_iteration_state>
{{searchIterationState}}
</search_iteration_state>
=== CONTEXT_DATA_END ===
