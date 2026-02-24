# L2 特性：runtime-http

## 功能说明
- 提供 HTTP server/client 运行时中间件管线与上下文传播封装。
- 统一 outbound client factory 与服务级 client 预置，降低业务服务接入成本。

## 约束
- HTTP pipeline 必须与 runtime-errors/observability/governance 解耦集成。
- 头字段传播遵循 `contracts/openapi/common.yaml`。
- endpoint 归一化命名必须稳定，用于 SLI/SLO 统计。

## 验收标准
- A1：8 个服务可统一接入 HTTP server/client runtime。
- A3：超时/重试/降级策略可配置且生效。
- A4：inbound/outbound 链路日志指标一致。
- A8：pipeline 与 client factory 自动化测试完整。
