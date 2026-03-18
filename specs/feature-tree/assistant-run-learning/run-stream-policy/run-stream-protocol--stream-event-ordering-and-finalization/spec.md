# L4 特性：stream-event-ordering-and-finalization

## 功能定位

本特性把私人助手流式输出从“若干 trace / chunk / completed 的松散拼接”升级为正式协议：

- `trace` 只承载调试与观测，不直接进入用户可见 UI
- `process_replace / process_append / process_commit` 只承载用户可见过程
- `answer_delta` 只承载最终成答正文增量
- `completed` 只承载终态结果、终态 `AssistantJourney` 与最终渲染所需 artifacts

目标不是单纯“能流式显示”，而是保证**过程、答案、终态三轨严格分层**，并且在本地执行、远端 SSE、历史重载三个场景下保持同一语义。

## 当前问题

1. 过程区仍大量依赖 `trace -> thinkingProgress -> journey headline` 的回退链，模型原始思维片段、查询词、机械占位文案容易泄漏到用户界面。
2. 远端已提供 `process_*` 事件，但端侧未把它们纳入正式 reducer，导致 UI 继续依赖启发式推断。
3. 终态收口不够严格，terminal payload 缺失时可能拿 partial stream 直接合成 completed，造成答案提前结束或过程文本污染成答。
4. 完成态与流式态的过程摘要、来源计数、耗时口径不统一，历史重载后容易和实时过程出现分叉。

## 用户价值

- 用户在长等待期间持续看到可信、自然、面向目标的过程说明，而不是内部思维链。
- 用户最终看到的回答只包含可展示成答，不会混入 “Shenzhen tian qi” 这类内部查询构造或 JSON 协议碎片。
- 完成态抽屉首行、来源计数、耗时与过程时间线能稳定恢复，形成业界一流的“过程可解释但不打扰”体验。

## 唯一真相源

- 总体体验目标：`specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/spec.md`
- 助手架构与边界：`quwoquan_app/assistant/docs/PERSONAL_ASSISTANT_ARCHITECTURE_AND_FLOW.md`
- 助手开发约束：`quwoquan_app/assistant/docs/PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md`
- Tool phase 文案：`quwoquan_app/assets/assistant/tools/catalog/tool_catalog.meta.json`
- 助手配置资产：`quwoquan_app/assets/assistant/config/`
- 助手协议 metadata：`quwoquan_service/contracts/metadata/assistant/`

## 事件合同

### 1. `trace`

- 仅用于 observability、开发态回放、错误诊断。
- 允许承载内部阶段、模型调试、工具执行细节。
- **禁止**直接驱动用户可见过程文案、最终答案文本或动效分支。

### 2. `process_replace / process_append / process_commit`

- 是用户可见过程的唯一流式输入。
- 事件必须携带明确的 `scope`：
  - `root`
  - `skill`
  - `aggregation`
- 事件正文必须是用户语言，围绕“已经为你做了什么 / 正在为你核对什么”表达，**禁止**携带：
  - 原始查询词与 queryVariants
  - tool args
  - `provider / freshnessHoursMax / contractVersion / assistant_turn / tool_call`
  - 原始 `<think>` 内容和模型自由思维链

### 3. `answer_delta`

- 是最终成答正文的唯一流式增量输入。
- UI 仅在 `answer_delta` 到达且满足 answer gate 条件时暴露正文。
- `answer_delta` 不得复用于过程抽屉，也不得被 `process_*` 事件反向回填。

### 4. `completed`

- 是唯一终态封口事件。
- 必须携带终态可展示内容来源之一：
  - `assistant_turn.userMarkdown`
  - `runArtifacts.displayMarkdown`
  - `runArtifacts.displayPlainText`
- 必须携带终态 `AssistantJourney` 或足以重放出同构 `AssistantJourney` 的结构化数据。
- terminal payload 缺失时，只允许在“已确认具备完整 answer 通道内容”时合成 completed；否则必须回退到非流式 run 或显式不完整失败，不得用过程文本强行封箱。

## 排序与收口规则

### 流式阶段顺序

推荐顺序：

1. `process_replace` / `process_append`：入口理解与任务收口
2. `process_append`：检索、核对、汇总等过程推进
3. `answer_delta`：最终成答开始流出
4. `process_commit`：过程阶段完成
5. `completed`：唯一终态

### 允许的交错

- `process_*` 可在 `answer_delta` 之前或期间继续推进，但不得把过程文本并入答案缓冲。
- `trace` 可与任何事件交错，但不得改变用户态 reducer 的最终结果。

### 明确禁止

- 以 `thinkingProgress`、`assistantDelta`、`streamDelta` 或 raw `<think>` 直接作为用户过程流。
- terminal payload 缺失时，以任意 `thinkingProgress(streaming=true)` 或 raw reasoning 拼接最终答案。
- UI 同时消费 `trace`、`process_*`、`chunk` 多路并发修改同一份用户可见状态。

## UI 渲染约束

### 过程抽屉

- 只基于 canonical `AssistantJourney` 渲染。
- 无真实 `journey` 内容时不得因为 seeded stages 而默认显示过程抽屉。
- 完成态首行必须来自统一摘要模板，格式为“已{完成语义}，参考 N 个来源，用时 T 秒”一类用户语言摘要。
- 耗时展示必须取整数秒，禁止小数。

### 最终答案

- 只来自 `answer_delta` 与 terminal `assistant_turn/runArtifacts`。
- 进入终态时必须以 terminal payload 为准做一次 reconcile，但不得接受内部协议碎片或过程文本作为 completed answer。

## 历史恢复约束

- 流式态、完成态、历史重载态必须使用同一份 `AssistantJourney` / `uiProcessTimelineV2` 恢复过程抽屉。
- 历史消息中若不存在真实过程数据，UI 不得回退展示“假四阶段”过程壳。

## Legacy 清理要求

- 移除旧 `assets/personal_assistant/...` 过程配置路径。
- 移除 UI 中基于中文 `contains()` 的动效或状态判断。
- 移除“trace 兼 process”双重语义兼容路径，避免第二真相源继续存在。

## 验收标准

- A1：`process_*`、`answer_delta`、`completed` 三类事件在本地与远端都能按统一语义进入同一条 reducer 主链。
- A2：原始 `<think>`、reasoning field、查询拼音词、JSON envelope、tool XML 块不进入过程抽屉和最终成答。
- A3：当 terminal payload 缺失但流中已有完整 `answer_delta` 时，可安全合成 completed；若只有过程文本或不完整答案，则不得提前封口。
- A4：repair / fallback 路径不得把 `thinkingProgress`、`assistantDelta` 等过程文本恢复为最终答案。
- A5：过程抽屉完成态首行使用统一摘要模板，来源计数、耗时、完成语义与终态 `AssistantJourney` 一致，耗时为整数秒。
- A6：无真实 `journey` 内容的消息不渲染过程抽屉；历史重载时与流式完成态恢复结果一致。
- A7：UI 动效和答案 gate 仅依赖 typed stage / readiness / answer 通道，不再依赖中文 label `contains()`。
- A8：存在 T1/T2/T4 回归测试，覆盖过程泄漏、终态截断、摘要口径、历史恢复和 legacy 路径清理。
