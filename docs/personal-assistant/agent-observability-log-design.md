# Personal Assistant 可观测日志设计（通用版）

本文定义个人助理 Agent 的通用日志规范，覆盖：

- AgentLoop / ReAct / LLM / Tool(Search) / Skill / UI 交互链路
- 全局页面感知链路（发现、趣聊、创作）与回写链路（memory/profile/context）
- Debug 与 Release 两种模式
- 运行诊断、回放、归因、质量评估所需最小字段

目标是让复杂问题从“人工拼图”转为“单 Run 可回放 + 可归因”。

---

## 1. 设计目标

- 可关联：一次对话内所有日志可用 `runId + traceId + turnId` 串联。
- 可定位：每个阶段都有统一 `stageId / status / failureCode`。
- 可对齐 UI：日志能解释“UI看到什么、为什么这么显示”。
- 可控成本：Debug 全量，Release 采样 + 可提级。
- 可复用：同一规范可用于天气、搜索、日历、情绪陪伴等任意垂类。

---

## 2. 分层与阶段模型

建议把一次运行拆为以下阶段（可扩展）：

- `S0_MODEL_CONFIG_LOAD`：模型配置发现与选择
- `S1_CATALOG_LOAD`：模板/工具/路由目录装载
- `S2_HISTORY_MEMORY_LOAD`：会话摘要与长期记忆召回
- `S3_CONTEXT_ASSEMBLE`：上下文组装与准入判断
- `S4_DOMAIN_SKILL_RESOLVE`：领域路由与 Skill 选择
- `S4A_SKILL_EXECUTION_ORCHESTRATE`：Skill 执行编排（参数注入、能力白名单、执行目标）
- `S4B_PAGE_AWARENESS_COLLECT`：页面感知采集（发现/趣聊/创作统一上下文）
- `S4C_PERCEPTION_WRITEBACK_PLAN`：感知回写计划（memory/profile/session/context）
- `S5_DIALOGUE_SCRIPT_BUILD`：状态机脚本构建
- `S6_TEMPLATE_RENDER`：模板渲染与变量绑定
- `S7_LLM_CALL_PARSE`：模型请求、响应、解析
- `S8_REACT_TOOL_LOOP`：工具计划、执行、回灌
- `S9_EXTERNAL_SEARCH`：外部搜索 provider 链路
- `S10_STREAM_UI_MAPPING`：流式 token、UI chunk 过滤与映射
- `S11_PERSIST_AND_EMIT`：session/memory/log 写回

每个阶段必须至少发出一条 `stage_start` 与一条 `stage_end`（或 `stage_error`）。

---

## 3. 统一事件信封（Envelope）

每条日志事件建议统一为：

```json
{
  "ts": "2026-03-05T13:00:48.270926Z",
  "env": "debug|release",
  "logType": "runtime|api|exception|audit|metric|business",
  "level": "debug|info|warn|error|fatal",
  "sourceDomain": "assistant|content|discovery|chat|create|user|circle|settings",
  "sourceService": "quwoquan_app|quwoquan_service|python_worker",
  "component": "agent_loop|react_runtime|llm_provider|tool_registry|search_tool|skill_engine|perception_engine|writeback_engine|ui",
  "target": "llm|search_provider|skill|memory|profile|session|context_scope|ui_timeline|ui_reference",
  "sessionId": "assistant_xxx",
  "runId": "1772686844298_assistant_1772686835949",
  "traceId": "1772686844298_assistant_1772686835949",
  "spanId": "span_xxx",
  "parentSpanId": "span_parent_xxx",
  "requestId": "req_xxx",
  "cloudRequestId": "gateway_req_xxx",
  "pythonJobId": "py_job_xxx",
  "correlationId": "corr_xxx",
  "turnId": "turn_001",
  "stageId": "S7_LLM_CALL_PARSE",
  "eventName": "stage_start|stage_end|stage_error|interaction|decision|writeback",
  "action": "call_llm|execute_tool|render_ui|write_memory|write_profile",
  "status": "ok|degraded|error",
  "failureCode": "",
  "payload": {}
}
```

### 字段职责分层（关键）

- `logType`：日志类型（运行/接口/异常/审计/指标/业务），用于平台级检索与告警。
- `level`：日志级别（debug~fatal），用于采样与报警阈值。
- `sourceDomain`：领域来源（助手/内容/发现/趣聊/创作等），第一层来源标识。
- `sourceService`：服务来源（端侧 app / 云侧服务 / python worker），第二层来源标识。
- `component`：产生日志的系统组件（agent_loop、ui、search_tool...）。
- `target`：交互对象（llm/search provider/skill/memory/profile...）。
- `eventName`：当前阶段内发生的事件语义（start/end/error/decision...）。
- `action`：具体动作（call_llm、execute_tool、write_memory...）。

> 结论：`logType` 不是交互对象；交互对象由 `component + target + action` 表达。

### 两层来源标识（领域 -> 组件）

- 第一层（业务领域）：`sourceDomain`
  - 示例：`assistant`（小趣助手）、`content`（内容流/创作）、`discovery`（发现）、`chat`（趣聊）
- 第二层（内部组件）：`component`
  - 示例：`agent_loop`、`perception_engine`、`ui`

推荐查询方式：

- 先按 `sourceDomain=assistant` 过滤业务范围
- 再按 `component` 过滤内部模块
- 最后按 `failureCode` 聚合根因

### 必填关联键

- `sessionId`
- `runId`
- `traceId`
- `spanId`
- `requestId`
- `correlationId`
- `turnId`（可由 run 内递增生成）
- `stageId`

### 推荐补充键

- `llmCallIndex`（第几次模型调用）
- `stepId`（ReAct step）
- `toolCallId`（function calling 协议关键）
- `provider`（search/llm provider）
- `cloudRequestId`（云侧网关或服务请求 ID）
- `pythonJobId`（Python 异步任务 ID）
- `skillId`（Skill 实例）
- `pageType`（discovery|chat|create）
- `writebackTarget`（memory|profile|session|context_scope）

### 小趣助手专用补全（在统一模板上加）

- `assistantDomainId`：weather/chat/create/...（领域）
- `dialogueStateId`：当前状态机节点
- `renderMode`：`md_json_dual|fallback_text`
- `decisionParseSuccess`：模型输出契约解析是否成功
- `uiPhaseTimelineVersion`：UI 阶段时间线协议版本
- `referencePackVersion`：参考资料打包协议版本
- `pageAwarenessScope`：`global|discovery|chat|create`
- `writebackScope`：`memory_only|memory_profile|memory_profile_context`

### 感知与回写扩展键（建议）

- `perceptionId`：一次页面感知快照 ID
- `perceptionSource`：`page_visible|user_action|system_pull`
- `perceptionScope`：`global|page|entity`
- `writebackPolicy`：`immediate|deferred|manual_review`
- `writebackDecision`：`accept|reject|partial`
- `writebackReason`

---

## 4. 阶段最小字段规范

## S0 模型配置装载

- `sourcesTried`: `["bundled","project","appStorage","env","fallback"]`
- `selectedSource`
- `selectedModelRef`
- `providerCount`, `modelCount`
- `missingFields`

## S1 目录装载（模板/工具/路由）

- `catalogType`: `template|tool|routing|event`
- `assetPath`, `fallbackPath`
- `catalogVersion`
- `itemCount`

## S2 历史与记忆

- `historyMessageCount`
- `historySummaryChars`
- `recallCount`
- `filteredRecallCount`
- `filterReasons`: `json_envelope|degraded_text|progress_placeholder`

## S3 上下文组装

- `canEnterDomain`
- `missingSlots`
- `fillTaskCount`
- `hasRealtimeNeed`, `hasLongtermNeed`

## S4 领域与 Skill

- `candidateDomains`
- `selectedDomain`
- `matchedRuleKeywords`
- `skillCountLoaded`
- `selectedSkillId`
- `skillInstructionLength`

## S4A Skill 执行编排

- `skillId`
- `skillVersion`
- `executionTarget`: `tool_chain|native_action|reasoning_only`
- `allowedTools`
- `deniedTools`
- `injectedParameters`
- `deviceScopeMatched`
- `capabilityGatePassed`

## S4B 页面感知采集（发现/趣聊/创作）

- `pageType`: `discovery|chat|create`
- `pageEntityId`
- `visibleModules`: `feed|composer|conversation|comment_sheet|draft_box`
- `selectionState`: 当前选中内容摘要（ID、类型、长度）
- `draftState`: 草稿状态（有无、字数、媒体数）
- `intentHints`: 从页面交互提取的意图提示
- `sensitiveScopeApplied`: 是否启用页面隐私裁剪

## S4C 感知回写计划

- `writebackTargets`: `memory|profile|session|context_scope`
- `writebackItemsCount`
- `dedupBeforeWriteCount`
- `conflictPolicy`: `latest_wins|confidence_wins|manual_review`
- `minConfidenceThreshold`
- `writebackDryRun`: `true|false`
- `writebackDecision`

## S5 状态机脚本

- `domainId`
- `currentStateId`
- `detectedEvent`
- `suggestedNextStateId`
- `requiredFieldsForNextState`
- `fallbackScriptUsed`

## S6 模板渲染

- `templateId`
- `templateVersion`
- `bucket`
- `missingVariables`
- `promptChars`
- `stackLayers`

## S7 LLM 调用与解析

- `llmCallIndex`
- `endpoint`
- `statusCode`
- `latencyMs`
- `finishReason`
- `toolCallsCount`
- `responseParseStatus`
- `retryWithoutToolsTriggered`

## S8 ReAct 工具环

- `iteration`
- `stepId`
- `toolName`
- `toolCallId`
- `argValidationOk`
- `toolSuccess`
- `toolErrorCode`
- `observationStatus`

## S9 搜索链路

- `providerSelected`
- `fallbackChain`
- `requestQueryNormalized`
- `timeoutMs`
- `authorityScore`
- `authoritativeCount`
- `freshnessHours`
- `qualityGatePassed`

## S10 流式与 UI 映射

- `streamChunkCount`
- `streamChars`
- `chunkDropCount`
- `dropReasonStats`
- `renderMode`
- `renderFallback`
- `decisionParseSuccess`
- `uiTimelinePhaseCount`
- `uiReferenceCount`

## S11 持久化

- `sessionWriteOk`
- `memoryWriteOk`
- `memoryTextSource`: `userMarkdown|plainText|none`
- `logPolicy`: `full|summary|dropped`
- `profileWritebackOk`
- `contextScopeWritebackOk`
- `writebackRejectedCount`

---

## 5. 失败码字典（FailureCode）

建议统一为可枚举值，避免靠字符串匹配：

- 配置与装载：`MODEL_CONFIG_MISSING`, `CATALOG_PARSE_FAILED`, `ASSET_NOT_FOUND`
- 模板与协议：`TEMPLATE_NOT_FOUND`, `TEMPLATE_EMPTY`, `TOOL_PROTOCOL_MISMATCH`
- 模型与网络：`LLM_HTTP_400`, `LLM_HTTP_429`, `LLM_TIMEOUT`, `LLM_RESPONSE_INVALID`
- 工具执行：`TOOL_NOT_FOUND`, `TOOL_INVALID_ARGUMENTS`, `TOOL_EXECUTION_FAILED`
- 搜索质量：`SEARCH_PROVIDER_UNAVAILABLE`, `SEARCH_TIMEOUT`, `SEARCH_QUALITY_INSUFFICIENT`
- 流式渲染：`STREAM_PARSE_FAILED`, `RENDER_FILTER_OVERDROP`, `UI_REFERENCE_MAPPING_FAILED`
- 历史污染：`HISTORY_CONTAMINATION_GUARD_TRIGGERED`, `MEMORY_POLLUTION_BLOCKED`
- Skill 相关：`SKILL_NOT_FOUND`, `SKILL_SCOPE_MISMATCH`, `SKILL_CAPABILITY_DENIED`
- 感知相关：`PERCEPTION_SOURCE_MISSING`, `PERCEPTION_SCHEMA_INVALID`
- 回写相关：`WRITEBACK_POLICY_REJECTED`, `WRITEBACK_CONFLICT_UNRESOLVED`, `PROFILE_WRITEBACK_BLOCKED`

---

## 6. UI 交互联动日志（关键）

为便于前后端一致定位，建议 UI 日志统一使用：

- `component=ui`
- `logType=business`（用户交互）或 `logType=runtime`（渲染流程）
- `target=ui_timeline|ui_reference|ui_message|ui_context`

- `ui.send_message`：用户发送问题（文本长度、输入模式）
- `ui.receive_chunk`：收到 chunk（长度、阶段）
- `ui.drop_chunk`：被过滤 chunk（原因）
- `ui.render_message`：最终渲染文本（长度、是否降级）
- `ui.render_timeline`：阶段数量、空阶段数量
- `ui.render_references`：参考条目数、domain 命中率
- `ui.user_action`：重试/切模型/展开详情/复制答案

### 建议补齐页面感知 UI 事件

- `ui.page_visible`：页面可见（`pageType/pageEntityId`）
- `ui.context_snapshot`：页面上下文快照（组件、选中态、草稿态）
- `ui.context_change`：关键上下文变化（切 tab、切会话、进入创作）
- `ui.writeback_feedback`：用户对回写建议的确认/拒绝

通过 `runId/traceId` 与 Agent 日志对齐，能定位“模型正常但 UI 显示异常”。

---

## 7. Debug vs Release 策略

## Debug 模式（研发排障）

- 成功/失败均记录全量 payload
- 保留完整 request/response（敏感字段脱敏）
- 输出 run 文件（可完整回放）
- 建议保留最近 N 天全量
- 记录 Skill 编排明细（allowed/denied tools、参数注入）
- 记录页面感知快照全量（经隐私裁剪）
- 记录回写决策明细（命中规则、冲突处理、最终写入对象）

## Release 模式（线上）

- 失败全量、成功采样（默认 20%）
- 成功日志默认摘要化，保留关键指标
- 支持会话/Run 提级（boost）为全量，便于线上快速定位
- 严格脱敏：API Key、用户身份、地理精确坐标
- 感知与回写日志默认摘要化，仅保留 hash、计数、决策结果
- 当 `writebackDecision != accept` 或 `failureCode` 非空时自动提级该 run

---

## 8. 数据治理与隐私

- 所有密钥字段统一脱敏（不可逆）
- 用户隐私字段分级：
  - P0：身份证明类（强脱敏）
  - P1：位置/设备（模糊化）
  - P2：行为统计（可保留聚合值）
- release 环境禁止落盘原始 prompt 全文（仅 hash + 长度 + 缺参信息）
- 感知快照中用户正文、评论、草稿仅保留摘要与统计，不落盘全文
- 回写前后都要记录字段级脱敏策略版本（便于审计）

---

## 9. 运行诊断最小闭环

一次运行可诊断，至少满足：

- 有 `stage_start/end` 完整链
- 有 `failureCode`（失败场景）
- 有 `tool_call_id` 对齐证据（工具回合）
- 有 `ui.render_*` 事件（前端展示证据）
- 有同一 `runId` 的多路日志，且可按 `logType + component + target` 串联：
  - `runtime`: `agent_loop/react_runtime/ui`
  - `api`: `llm_provider/search_tool`
  - `exception`: 任意组件错误
  - `business`: 用户交互、回写决策
- 有页面感知快照与最终回写记录的一一对应（`perceptionId` 可追溯）

### 端云 + Python 联合定位最小条件

- 同一问题在端、云、Python 三侧共享同一 `correlationId`
- 端侧日志含：`traceId/spanId/requestId`
- 云侧日志含：`traceId/spanId/parentSpanId/cloudRequestId`
- Python 工程日志含：`traceId/spanId/parentSpanId/pythonJobId`
- 任一侧失败时，必须能在另一侧检索到同一 `correlationId` 的上下游记录

### 端云日志拉通视图（建议）

- 端侧（`sourceService=quwoquan_app`）
  - `component=agent_loop|react_runtime|ui|perception_engine|writeback_engine`
- 云侧（`sourceService=quwoquan_service`）
  - `component=gateway|assistant_api|retrieval_proxy|profile_service`
- Python（`sourceService=python_worker`）
  - `component=offline_retrieval|ranking|summarizer|feature_job`

统一按以下维度聚合：

- `sourceDomain + sourceService + component`
- `logType + level + failureCode`
- `correlationId + traceId + requestId`

---

## 10. 落地建议（不改业务逻辑优先）

- 第一步：先统一字段与 failureCode，不改决策逻辑
- 第一步补充：先统一 `logType/level/component/target/action` 五元组
- 第二步：补齐 UI 事件日志，打通 runId
- 第三步：引入“单 Run 诊断视图”脚本，自动聚合四路日志
- 第三步补充：扩展为端云 Python 联合视图，按 `correlationId` 串联
- 第四步：把关键质量阈值挂 gate（例如 `decisionParseSuccessRate`、`renderFallbackRate`）

