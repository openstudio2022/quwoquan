# L2 特性：runtime-errors

## 功能说明
- 提供统一错误码、错误对象、响应封装与 HTTP/RPC 状态映射。
- 保证用户可见文案与调试信息分离，支持链路追踪字段透传。

## 约束
- 错误码格式固定为 `<MODULE>.<KIND>.<REASON>`。
- 所有服务必须使用 runtime-errors 输出错误响应，禁止手写错误 JSON。
- 与 `contracts/error_codes.md`、`contracts/openapi/common.yaml` 一致。

## 验收标准
- A1：核心服务统一错误响应结构可用。
- A3：`recovery policy` 可用于重试与降级决策。
- A7：错误码字典、OpenAPI、SDK 实现三方一致。
- A8：unit/contract/integration/uat 自动化完整。
