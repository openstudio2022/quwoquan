# L2 特性：runtime-rpc

## 功能说明
- 提供 gRPC/RPC 统一拦截器运行时能力，覆盖 metadata 传播、错误映射与治理策略接入。
- 提供服务内 RPC client/stub 统一封装，便于内部通信标准化。

## 约束
- RPC metadata 传播字段与 HTTP 追踪字段语义对齐。
- 错误映射需复用 runtime-errors，禁止服务自行定义状态映射。
- 与 runtime-observability/runtime-governance 挂钩，不重复实现。

## 验收标准
- A1：RPC server/client 拦截器统一接入可用。
- A3：timeout/retry/circuit 策略对 RPC 生效。
- A4：RPC 链路日志、指标、追踪完整。
- A8：拦截器与 stub factory 自动化覆盖。
