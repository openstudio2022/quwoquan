# Personal Assistant 端云Python日志字段映射表

本表用于统一三侧日志语义与字段命名，确保一次问题可跨：

- 端侧：`quwoquan_app`
- 云侧：`quwoquan_service`
- Python 工程：`python_worker`（检索/排序/摘要/特征任务）

统一目标：同一请求可通过 `correlationId + traceId + requestId` 拉通定位。

---

## 1. 统一信封字段映射（Canonical Envelope）

| Canonical 字段 | 端侧（Flutter） | 云侧（Go） | Python | 说明 |
|---|---|---|---|---|
| `ts` | `ts` | `ts` | `ts` | ISO8601 时间戳 |
| `env` | `env` | `env` | `env` | `debug/release` 或 `dev/integration/prod` |
| `logType` | `logType` | `log_type` | `log_type` | `runtime/api/exception/audit/metric/business` |
| `level` | `level` | `level` | `level` | `debug/info/warn/error/fatal` |
| `sourceDomain` | `sourceDomain` | `source_domain` | `source_domain` | 业务域来源（assistant/content/...） |
| `sourceService` | `sourceService` | `service` | `service` | `quwoquan_app/quwoquan_service/python_worker` |
| `component` | `component` | `component` | `component` | 内部组件名 |
| `target` | `target` | `target` | `target` | 交互对象（llm/search/skill/...） |
| `eventName` | `eventName` | `event_name` | `event_name` | `stage_start/end/error/...` |
| `action` | `action` | `action` | `action` | `call_llm/execute_tool/...` |
| `status` | `status` | `status` | `status` | `ok/degraded/error` |
| `failureCode` | `failureCode` | `failure_code` | `failure_code` | 统一失败码 |
| `payload` | `payload` | `payload` | `payload` | 阶段细节 |

> 规范建议：落盘可保留本地命名风格（snake/camel），但日志平台入库前统一映射到 Canonical 字段。

---

## 2. 追踪与关联字段映射（Trace Correlation）

| Canonical 字段 | 端侧 | 云侧 | Python | 备注 |
|---|---|---|---|---|
| `sessionId` | `sessionId` | `session_id` | `session_id` | 会话维度 |
| `runId` | `runId` | `run_id` | `run_id` | 一次 Agent Run |
| `turnId` | `turnId` | `turn_id` | `turn_id` | 对话轮次 |
| `traceId` | `traceId` | `trace_id` | `trace_id` | 全链路追踪 |
| `spanId` | `spanId` | `span_id` | `span_id` | 当前节点 |
| `parentSpanId` | `parentSpanId` | `parent_span_id` | `parent_span_id` | 上游节点 |
| `requestId` | `requestId` | `request_id` | `request_id` | 单次请求 |
| `cloudRequestId` | `cloudRequestId` | `gateway_request_id` | `upstream_request_id` | 云网关请求号 |
| `pythonJobId` | `pythonJobId` | `python_job_id` | `job_id` | Python 任务号 |
| `correlationId` | `correlationId` | `correlation_id` | `correlation_id` | 端云统一主键 |

### Header 传递建议（HTTP / RPC）

| Header | 用途 | 建议来源 |
|---|---|---|
| `traceparent` | W3C Trace | tracing SDK 自动注入 |
| `x-correlation-id` | 业务关联键 | 端侧首次生成，云侧透传 |
| `x-request-id` | 请求唯一键 | 网关生成或端侧生成 |
| `x-run-id` | Agent Run 对齐 | 端侧 AgentLoop |
| `x-turn-id` | 轮次对齐 | 端侧对话层 |

---

## 3. 日志类型与旧枚举映射（端侧现状兼容）

当前端侧存在 `AppLogType`（`pageAccess/agentRun/llm/search/cloudApi/perf/error`），建议映射到通用模型：

| 端侧 `AppLogType` | Canonical `logType` | 推荐 `component` | 推荐 `target` |
|---|---|---|---|
| `agentRun` | `runtime` | `agent_loop` | `session` |
| `llm` | `api` | `llm_provider` | `llm` |
| `search` | `api` | `search_tool` | `search_provider` |
| `cloudApi` | `api` | `gateway_client` | `cloud_service` |
| `perf` | `metric` | `perf_probe` | `runtime` |
| `error` | `exception` | `*` | `*` |
| `pageAccess` | `business` | `ui` | `ui_context` |

---

## 4. 小趣助手专用字段映射（Assistant Extension）

| Canonical 扩展字段 | 端侧 | 云侧 | Python | 说明 |
|---|---|---|---|---|
| `assistantDomainId` | `assistantDomainId` | `assistant_domain_id` | `assistant_domain_id` | weather/chat/create... |
| `dialogueStateId` | `dialogueStateId` | `dialogue_state_id` | `dialogue_state_id` | 状态机节点 |
| `renderMode` | `renderMode` | `render_mode` | `render_mode` | `md_json_dual/fallback_text` |
| `decisionParseSuccess` | `decisionParseSuccess` | `decision_parse_success` | `decision_parse_success` | 输出契约是否解析成功 |
| `pageAwarenessScope` | `pageAwarenessScope` | `page_awareness_scope` | `page_awareness_scope` | 感知范围 |
| `writebackScope` | `writebackScope` | `writeback_scope` | `writeback_scope` | 回写范围 |
| `perceptionId` | `perceptionId` | `perception_id` | `perception_id` | 感知快照关联 |
| `writebackDecision` | `writebackDecision` | `writeback_decision` | `writeback_decision` | 回写决策 |

---

## 5. 组件命名建议（跨端云统一）

建议维持小写蛇形或小写短横线风格，避免同义词并存：

- 端侧组件：`agent_loop`, `react_runtime`, `llm_provider`, `search_tool`, `skill_engine`, `perception_engine`, `writeback_engine`, `ui`
- 云侧组件：`gateway`, `assistant_api`, `retrieval_proxy`, `profile_service`, `orchestrator`
- Python 组件：`offline_retrieval`, `ranking`, `summarizer`, `feature_job`

---

## 6. 查询模板（排障实用）

## 6.1 单问题全链路

按 `correlationId` 查询并按时间排序：

1. 过滤 `sourceDomain=assistant`
2. 聚合 `sourceService in [quwoquan_app, quwoquan_service, python_worker]`
3. 查看 `failureCode` 首次出现点（first-failure）

## 6.2 协议类故障（tool_call_id）

- 条件：`failureCode in [TOOL_PROTOCOL_MISMATCH, LLM_HTTP_400]`
- 重点字段：`toolCallId`, `eventName`, `action`, `statusCode`

## 6.3 搜索质量故障

- 条件：`failureCode=SEARCH_QUALITY_INSUFFICIENT`
- 重点字段：`providerSelected`, `fallbackChain`, `authorityScore`, `authoritativeCount`

---

## 7. 最小落地要求（进入实施前）

- 三侧（端/云/Python）至少能写出：`correlationId + traceId + requestId`
- 端侧 `AppLogType` 已映射到 `logType/component/target`
- 错误日志必须带 `failureCode`（禁止仅 message 文本）
- `run-diagnosis-template.md` 可用本映射表字段直接填报

