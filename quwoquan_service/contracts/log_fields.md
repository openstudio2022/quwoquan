# 统一日志字段规范（log fields）

目标：所有服务输出结构化日志时，字段名/含义一致，便于跨服务检索、聚合与告警。

本规范适用于：Gateway / Orchestrator / Content / Circle / User / Chat / Assistant / ProductOps，以及后续新增服务。

---
## 1. 字段分层

- **Identity（身份）**：userId/personaId 等
- **Request（请求）**：requestId/traceId/pageId、method/path/status、latency
- **Runtime（运行时）**：service/module/env/version/region/host
- **Error（错误）**：error.code、error.userMessage、error.debugMessage、retryable
- **Event（事件）**：mq/job/cron 的 causationId/parentTraceId

---
## 2. 必填字段（所有日志级别都应尽量包含）

| 字段 | 类型 | 说明 |
|---|---:|---|
| `service` | string | 服务名：`gateway-service` / `orchestrator-service` / `content-service` ... |
| `env` | string | 环境：`local` / `dev` / `staging` / `prod` |
| `timestamp` | string | ISO8601（由日志系统补齐也可） |
| `level` | string | `debug`/`info`/`warn`/`error` |
| `message` | string | 人类可读的简要描述（不替代结构化字段） |
| `traceId` | string | 全链路追踪 ID（分段格式见 `contracts/error_codes.md`） |
| `requestId` | string | 单次请求 ID（分段格式见 `contracts/error_codes.md`） |
| `pageId` | string | 端侧来源（如存在）：三段式 `模块.对象.页面/动作` |

---
## 2.1 I/O 终态日志统一基线（冻结）

接口与消息发送/接收统一使用同一结构，且每次请求/消息仅输出一条终态日志。

固定字段（最简）：

- `schemaVersion`
- `service`
- `timestamp`
- `origin`（`app.http`/`app.grpc`/`service.http`/`service.grpc`/`service.mq`/`job.internal`/`cron.internal`）
- `direction`（`inbound`/`outbound`）
- `endpoint`
- `sourceId`
- `traceId`
- `requestId`
- `sessionId`
- `src`
- `userId`
- `personaId`
- `pageId`
- `devicePlatform`
- `appVersion`
- `serviceName`
- `serviceInstanceId`
- `status`
- `durationMs`
- `errorCode`
- `messageSize`

约束：

- `headers` 不输出到统一日志。
- `statusCode` 不单独输出，统一由 `status + errorCode` 表达。
- `errorCode` 统一遵循 `<MODULE>.<KIND>.<REASON>`。
- 详细 machine-readable schema 见 `contracts/io_access_log_baseline.yaml`。

---

## 2.2 过程日志基线（process_trace_log）

过程日志与接口终态日志区分开，仅用于追踪“发生了什么”：

- 不承载错误对象
- 受 `traceLogLevel=off|info|debug` 控制
- 输入/输出参数统一为 `io.inputKv` / `io.outputKv`
- 参数输出完全由 metadata 驱动（`contracts/metadata/log_kv_policy.yaml`），默认最小输出

字段基线见：`contracts/process_trace_log_baseline.yaml`

---

## 2.3 异常日志基线（exception_log）

异常日志独立于普通日志：

- 单独 schema：`contracts/exception_log_baseline.yaml`
- 单独输出通道：error sink
- 默认必打，不受普通日志级别控制
- 可携带 `io.inputKv` / `io.outputKv`（仍由 metadata 驱动）

---
## 3. HTTP 访问日志建议字段

| 字段 | 类型 | 说明 |
|---|---:|---|
| `http.method` | string | GET/POST/... |
| `http.path` | string | 路径（避免记录完整 query 中的敏感信息） |
| `http.status` | number | 状态码 |
| `durationMs` | number | 服务端耗时 |
| `client.ip` | string | 透传或网关采集 |
| `userId` | string | 用户 ID（可空） |
| `personaId` | string | 分身 ID（可空） |

---
## 4. 异步（MQ/JOB/CRON）日志建议字段

| 字段 | 类型 | 说明 |
|---|---:|---|
| `src` | string | 事件源：`MQ`/`JOB`/`CRON`/`APP`/`GW`/`ORCH` |
| `parentTraceId` | string | 上游 traceId（如存在） |
| `causationId` | string | 因果 ID（消息/任务触发链路） |
| `mq.topic` | string | topic（如适用） |
| `mq.messageId` | string | 消息 ID（如适用） |
| `job.name` | string | job 名（如适用） |

---
## 5. 错误日志字段

将错误码与 user/debug 信息分离：
- `error.code`：形如 `MODULE.KIND.REASON`
- `error.userMessage`：面向用户
- `error.debugMessage`：面向定位

建议额外字段：
- `error.kind` / `error.module` / `error.reason`
- `error.retryable`（bool）
- `error.details`（object，避免塞超大内容）

---
## 6. 隐私与安全

- 禁止记录明文密码、token、验证码、完整身份证号/手机号等。
- 对可能包含隐私的字段（query/body）做脱敏或摘要。

更完整的字段分级、可配置匿名化与可配置加密策略见：`contracts/privacy_and_security.md`。
