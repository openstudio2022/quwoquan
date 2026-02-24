# L2 特性：runtime-observability

## 功能说明
- 提供统一观测内核：结构化日志、指标、追踪与导出适配。
- 统一三类日志：接口终态、过程跟踪、异常日志，并支持 metadata 驱动 KV 输出。

## 约束
- 观测字段必须与 `contracts/log_fields.md` 与 baseline yaml 对齐。
- 禁止输出 headers/statusCode 等禁用字段。
- 观测内核不承载 HTTP/MQ 协议执行链逻辑。

## 验收标准
- A1：三类日志结构统一并可关联检索。
- A4：指标、追踪、日志可通过 trace/request/session 串联。
- A7：contracts 与日志模型一致。
- A8：unit/contract/integration/uat 完整。
