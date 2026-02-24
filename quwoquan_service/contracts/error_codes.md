# 统一错误码规范（v1）

目标：错误码既能**定位错误源模块**，又能区分**错误类型**（用户/系统/网络/中间件），并将**面向用户的提示**与**面向定位的原因**分离。

---

## 1. 错误码格式

采用固定 3 段结构：

`<MODULE>.<KIND>.<REASON>`

- `MODULE`：错误源模块（见 §2）
- `KIND`：错误类型（见 §3）
- `REASON`：稳定原因码（小写下划线，见 §4）

示例：

- `CONTENT.USER.invalid_argument`
- `USER.SYSTEM.conflict`
- `CHAT.NETWORK.timeout`
- `DB.MIDDLEWARE.connection_refused`
- `MQ.MIDDLEWARE.publish_failed`
- `CACHE.MIDDLEWARE.read_timeout`

---

## 2. MODULE（错误源模块）

业务模块：

- `GATEWAY`
- `ORCH`
- `CONTENT`
- `CIRCLE`
- `USER`
- `CHAT`
- `OPS`
- `ASSISTANT`

基础设施模块（中间件/依赖）：

- `DB`
- `MQ`
- `CACHE`
- `OSS`
- `CDN`

通用：

- `UNKNOWN`

---

## 3. KIND（错误类型）

- `USER`：用户侧输入/状态导致（参数不合法、无权限、频率过高、登录过期等）
- `SYSTEM`：服务端业务/代码/依赖处理异常（空指针、状态机非法、内部错误等）
- `NETWORK`：网络类（DNS/超时/连接中断/网关不可达等）
- `MIDDLEWARE`：中间件类（DB/MQ/Cache/OSS 等连接、超时、写失败等）

---

## 4. REASON（稳定原因码）

建议分两类：

### 4.1 通用原因码（跨服务一致）

- `invalid_argument`
- `unauthorized`
- `forbidden`
- `not_found`
- `conflict`
- `rate_limited`
- `timeout`
- `unavailable`
- `internal_error`

### 4.2 依赖细分原因码（仅用于定位）

- DB：`connection_refused`、`read_timeout`、`write_timeout`、`deadlock`、`duplicate_key`
- MQ：`publish_failed`、`consume_failed`
- Cache：`read_timeout`、`write_timeout`、`key_evicted`

---

## 5. ErrorResponse（返回结构约定）

接口响应中必须同时携带：

- `code`：上述 3 段错误码（定位用，稳定）
- `userMessage`：面向用户的友好提示（可 i18n）
- `debugMessage`：面向定位的错误原因（可带内部细节，但需脱敏）
- `module/kind/reason`：结构化字段（便于日志检索）
- `requestId/traceId`：全链路追踪关联（见 §6 分段格式）

**注意**：`userMessage` 不应直接暴露内部异常/SQL/依赖地址；`debugMessage` 必须经过脱敏策略。

---

## 5.1 SDK 落地约束（runtime/errors）

为避免各服务手写错误响应导致漂移，所有服务统一通过 `runtime/errors` 输出 `ErrorResponse`。

强制要求：

- 服务内抛错统一使用结构化错误对象（code/module/kind/reason/debug/retryable）。
- HTTP/gRPC 适配层统一调用 SDK 编码器，不允许手写 JSON 结构。
- `module`、`kind` 必须使用 SDK 枚举值，与 `contracts/openapi/common.yaml` 保持一致。

建议 HTTP 映射（默认）：

- `*.USER.invalid_argument` -> `400`
- `*.USER.unauthorized` -> `401`
- `*.USER.forbidden` -> `403`
- `*.USER.not_found` -> `404`
- `*.USER.conflict` -> `409`
- `*.USER.rate_limited` -> `429`
- `*.NETWORK.timeout` -> `504`
- `*.MIDDLEWARE.unavailable` -> `503`
- 其他 -> `500`

---

## 6. requestId / traceId 分段格式（可读、可定位源头）

目标：仅从 ID 字符串即可看出请求源头与大致归属（端侧页面/会话/时间），并可用于日志检索与影响范围分析。

### 6.1 字段定义

推荐所有请求同时携带：

- `X-Trace-Id`：链路 ID（端→网关→编排→服务可共享）
- `X-Request-Id`：单次请求 ID（每一跳可生成/覆盖，但建议至少端侧先注入）

### 6.2 格式约定

统一采用点分段：

- `traceId`：`<SRC>.<SESSION>.<PAGE>.<TS>.<RAND>`
- `requestId`：`<SRC>.<PAGE>.<TS>.<RAND>`

字段说明：

- `SRC`：源头标识（建议取：`APP` / `GW` / `ORCH` / `SVC-<SERVICE>` / `JOB` / `CRON` / `MQ`）
- `SESSION`：**源头会话/执行 ID**（不只端侧）。
  - 端侧：一次启动会话 ID（稳定）
  - 定时任务/异步任务：jobRunId / cronRunId（一次执行稳定）
  - MQ 消费：messageChainId（一次消费链路稳定）
- `PAGE`：来源标识（**三段式**）：`模块.业务对象.页面名/动作`
  - 例：`chat.conversation.list`、`chat.message.list`、`content.post.detail`、`user.persona.activate`
  - 说明：虽然叫 pageId，但允许用于“动作/接口场景”，核心是可读可定位
- `TS`：时间戳（**epoch 微秒时间戳的 base36 表示**，短且可排序）
- `RAND`：短随机串（建议 base36，避免同一微秒冲突）

示例：

- `traceId=APP.ky6m2b.chat.conversation.list.l9z1y4.2f8k`
- `requestId=APP.chat.conversation.list.l9z1y4.2f8k`

### 6.3 与错误码的关系

- 错误码用于**原因定位**（模块+类型+原因）
- trace/requestId 用于**链路定位**（源头/页面/会话/时间），与错误码组合可快速收敛问题范围

### 6.4 异步链路的来源追踪（消息/定时任务）

对于异步边界（MQ、定时任务触发等），建议采用“新 trace + 父链路关联”的方式，保证：

- 每条异步执行都有自己的 `traceId`
- 同时可通过父子关系追溯到触发源头

推荐额外字段（header 或 message metadata）：

- `X-Parent-Trace-Id`：触发源的 traceId（如果有）
- `X-Causation-Id`：触发载体 ID（如 messageId / topic+offset 的安全编码 / jobRunId）

示例（MQ 消费）：
- 生产时：`traceId=APP....`，并写入 message metadata：`parentTraceId=<traceId>`，`causationId=<messageId>`
- 消费时：生成 `traceId=MQ.<msgChain>.<page>.<ts>.<rand>`，同时携带 `X-Parent-Trace-Id` 与 `X-Causation-Id`

