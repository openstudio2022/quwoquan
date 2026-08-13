# L2 Business Capability：运行时错误 (`runtime-errors`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[L1 DEC-001](../design.md#dec-001)

## 1. 能力目标

提供统一错误码、错误对象、响应封装与 HTTP/RPC 状态映射。

## 2. 范围与非目标

### In Scope

- errors.yaml -> Go AppErrorFrom* -> ErrorResponse -> Flutter CloudException/RuntimeFailure 的端云链路。
- userMessage control-plane 热配置、fail-safe baseline、override hit/miss 可观测。
- recovery_action/recovery_after_seconds 静态结构化下发与端侧消费。
- 客户端可见域错误码全集一致、全域 typed DomainErrorCode 消费与前向兼容。
- 异常遥测与行为上报失败的结构化可观测和本地队列保留。

### Out of Scope

- recovery 参数热配置。
- 新 MODULE 白名单 metadata 化。
- gateway/orchestrator 独立进程落地；本验收只登记后续需要补专属错误域。

## 3. Journey / Scenario 贡献

- [`JNY-001 / SCN-004`](../../spec.md#scn-004)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：提供统一错误码、错误对象、响应封装与 HTTP/RPC 状态映射。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`error-code-and-response-envelope`](./error-code-and-response-envelope/spec.md)：定义“错误代码与响应信封”的可观察主路径、失败语义及父能力交接。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 runtime errors 端云错误治理闭环 SIT

- 客户端可见域均通过 metadata/codegen 输出结构化错误；content 不再保留 sentinel-only 豁免。
- Flutter 端所有生成的 *ErrorCode 均被 CloudErrorMapper 或统一 registry 注册消费；未知 code 仍靠 userMessage + recovery 前向兼容。
- 行为上报、异常遥测与 UI 错误展示不保留自建异常或静默吞失败路径。
- override hit/miss、runtime error code/module/kind/recovery_action 指标和告警规格可复核。

<a id="req-002"></a>
### REQ-002 提供统一错误码、错误对象、响应封装与 HTTP/RPC 状态映射

- 提供统一错误码、错误对象、响应封装与 HTTP/RPC 状态映射。
- 每个 `errors.yaml` 条目必须以 `emitted_by` 声明真实发射 surface；只有 HTTP surface 强制 `http_status` 和对象内 operation 绑定，worker/consumer/player 等非 HTTP surface 禁止伪造 HTTP 状态。
- 所有服务必须使用 runtime-errors 输出错误响应，禁止手写错误 JSON。
- 错误响应只以 `debugMessage` 承载脱敏诊断，不保留 `message`、`user_message`、`reasonMessage` 或嵌套 `error.userMessage` 兼容解码轨。
- 客户端可见域禁止保留 sentinel-only 错误生成路径；生成产物必须包含 `AppErrorFrom*`、`userMessage`、`.WithRecovery(...)`。
- 端侧所有云侧错误必须保留 raw `code`、`userMessage` 与 `recovery` 前向兼容，同时对已生成的 `*ErrorCode` 提供统一 typed 消费入口；禁止只生成枚举而中央 mapper 不注册。
- telemetry 自身失败必须可观测并保留队列，禁止 `catchError((_) {})` 或无上下文 `catch (_)` 静默吞掉异常上报失败。
- 指标、告警与回滚必须覆盖错误码激增、override hit/miss 异常、config disk fallback 和 runtime error response 契约漂移。
- 核心服务统一错误响应结构可用。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 runtime errors 端云错误治理闭环 SIT

- GIVEN 执行“runtime errors 端云错误治理闭环”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“runtime errors 端云错误治理闭环”对应动作。
- THEN 客户端可见域均通过 metadata/codegen 输出结构化错误；content 不再保留 sentinel-only 豁免。
- THEN Flutter 端所有生成的 *ErrorCode 均被 CloudErrorMapper 或统一 registry 注册消费；未知 code 仍靠 userMessage + recovery 前向兼容。
- THEN 行为上报、异常遥测与 UI 错误展示不保留自建异常或静默吞失败路径。
- THEN override hit/miss、runtime error code/module/kind/recovery_action 指标和告警规格可复核。
- THEN `emitted_by` surface、HTTP status 与对象内 operation 引用由 metadata compiler 交叉校验，非 HTTP 错误不被误判为 HTTP 契约。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 runtime errors 端云错误治理闭环 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：客户端可见域均通过 metadata/codegen 输出结构化错误；content 不再保留 sentinel-only 豁免。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 各域错误 codegen 文案形态不齐与单语直读

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：当前各域生成错误码形态不一致——`UserErrorCode` 携带 zh/en + `recoveryAction`/`disruptionLevel`/`messageForLocale`，而 `SearchErrorCode`/`TagErrorCode`/`OpsEventRecordErrorCode` 只有单语 `defaultMessage`+`httpStatus`，`Content` 另用 `ContentErrorMessages` Map。导致同一错误码在不同消费点文案能力不同；`upload_policy` 等无 context 的 application 层只能直读 `ContentErrorMessages.zh`，无法随 locale 切换。
- 完成判定：`SIT-001` 对应行为满足——codegen 模板对全部客户端可见域输出统一形态（zh/en + recovery/disruption + `messageForLocale`），`DomainErrorCodeRegistry` 与 `UiErrorSemanticResolver` 消费统一形态，application 层策略校验类文案支持 locale 注入或返回错误码由 presentation 解析，且真实测试 `spec_ref` 有效。
