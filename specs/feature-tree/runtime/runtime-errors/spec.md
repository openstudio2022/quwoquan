# L2 特性：runtime-errors

## 功能说明
- 提供统一错误码、错误对象、响应封装与 HTTP/RPC 状态映射。
- 保证用户可见文案与调试信息分离，支持链路追踪字段透传。
- 提供端云一体化错误治理闭环：`errors.yaml` 是错误码、用户文案、HTTP 状态与 recovery 指令的唯一真相源；Go 服务通过生成的 `AppErrorFrom*` 工厂输出结构化 `ErrorResponse`；Flutter 端通过 `CloudException`、`RuntimeFailure` 与全域 `DomainErrorCode` 消费同一契约。
- 支持运营态用户提示语热配置：control-plane 下发 `sys.error_message.<MODULE.KIND.reason>.<locale>`，错误出口命中即覆盖 `userMessage`，未命中回退 codegen baseline，改文案不需要云服务重启或端侧发版。

## 约束
- 错误码格式固定为 `<MODULE>.<KIND>.<REASON>`。
- 所有服务必须使用 runtime-errors 输出错误响应，禁止手写错误 JSON。
- 与 `contracts/error_codes.md`、`contracts/openapi/common.yaml` 一致。
- 客户端可见域禁止保留 sentinel-only 错误生成路径；生成产物必须包含 `AppErrorFrom*`、`userMessage`、`.WithRecovery(...)`。
- 端侧所有云侧错误必须保留 raw `code`、`userMessage` 与 `recovery` 前向兼容，同时对已生成的 `*ErrorCode` 提供统一 typed 消费入口；禁止只生成枚举而中央 mapper 不注册。
- telemetry 自身失败必须可观测并保留队列，禁止 `catchError((_) {})` 或无上下文 `catch (_)` 静默吞掉异常上报失败。
- 指标、告警与回滚必须覆盖错误码激增、override hit/miss 异常、config disk fallback 和 runtime error response 契约漂移。

## 验收标准
- A1：核心服务统一错误响应结构可用。
- A3：`recovery policy` 可用于重试与降级决策。
- A7：错误码字典、OpenAPI、SDK 实现三方一致。
- A8：unit/contract/integration/uat 自动化完整。
- A9：客户端可见域端云错误码全集一致，且 recovery 按 code 精确对齐到生成的 Go 工厂和端侧解析策略。
- A10：用户提示语 override 支持 zh/en 热更新、命中率/回退率可观测、灰度发布和回滚审计。
- A11：异常遥测、行为上报与 UI 错误展示都消费结构化 runtime failure，不保留自建异常分支或第二套错误语义。
