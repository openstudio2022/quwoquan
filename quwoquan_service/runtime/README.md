# runtime（统一运行时能力域）

`runtime` 为云侧服务提供统一运行时能力封装，目标是让服务聚焦业务开发，避免重复实现横切逻辑。

当前分层：

- `runtime/config`：配置读取与运行时参数接口
- `runtime/errors`：统一错误码与错误响应
- `runtime/observability`：日志/指标/追踪内核
- `runtime/http`：HTTP inbound/outbound pipeline 与客户端工厂
- `runtime/messaging`：消息 envelope 与 MQ 运行时适配入口
- `runtime/governance`：治理策略接口（timeout/retry/circuit/rate-limit/degrade）
- `runtime/rpc`：RPC 运行时接口
- `runtime/experiments`：实验分桶与灰度运行时接口
- `runtime/learning`：反馈学习闭环运行时接口

接入要求：

- 业务服务统一依赖 `runtime/*`。
- 禁止在服务内重复实现横切能力。
