# 可观测性平台模块（Observability Kit）

本模块用于落地“云厂商 SaaS + 统一接入规范 + 接入脚本/配置”的组合能力。
它**不是面向 App 的业务服务**，不提供业务 API；其目标是让 Gateway/Orchestrator/各业务服务以一致方式输出：
- 结构化日志（访问/过程/异常）
- 指标（metrics）
- 分布式追踪（traces/spans）
- 统一错误码（见 `contracts/error_codes.md`）

---
## 1. 推荐方案（厂商无关）
### 1.1 标准协议
- **OpenTelemetry（OTEL）**：作为 traces/metrics/logs 的统一采集与导出标准。
  - Go 服务：OTEL SDK + middleware 自动注入 traceId/requestId/span
  - Python（assistant-service）：OTEL SDK + ASGI middleware

### 1.2 云厂商 SaaS（优先）
- 使用云厂商提供的 APM/日志/指标 SaaS（阿里云/火山引擎均可），通过 OTEL exporter 或厂商 agent 接入。
- 本仓库只维护“统一字段/规范/脚本/仪表盘模板”，不自研监控平台。

---
## 2. 与 contracts 的关系

统一约束以 `quwoquan_service/contracts/` 为单一事实来源：
- `contracts/openapi/common.yaml`：trace/requestId/pageId/causationId 等 header 约定
- `contracts/error_codes.md`：错误码与 requestId/traceId 分段格式
- `contracts/log_fields.md`：日志字段标准
- `contracts/metrics.md`：指标命名与标签标准
- `contracts/messages/envelope.schema.json`：消息队列 envelope 结构（含 parentTraceId/causationId）

---
## 3. 建议的落地目录（后续实现时补齐）

```
platform/observability/
  README.md
  dashboards/                  # Grafana/厂商仪表盘模板
  alerts/                      # 告警规则模板（Prometheus/厂商）
  scripts/                     # 接入脚本：本地/云侧
  otel/                        # OTEL Collector 配置模板（如需自部署）
```

---
## 4. 是否需要“监控服务”？

不建议再新增一个对外业务 API 的“监控服务”。
可观测性应作为**平台能力**：由 SaaS/标准栈承载；本模块负责统一规范与接入落地。

---
## 5. 云厂商接入建议（阿里云 / 火山引擎）

建议采用“协议统一、厂商可插拔”：
- 协议统一：OTEL（trace/metric/log） + `contracts/*` 字段口径
- 厂商接入：
  - 阿里云：ARMS / SLS / CloudMonitor（或等价）
  - 火山引擎：APMPlus / TLS / 云监控（或等价）

落地要求：
- `service` 标签、`endpoint` 标签、`traceId/requestId` 字段在两家厂商保持同口径
- 告警模板（错误率/延迟/依赖失败/队列积压）统一维护，通知通道按厂商配置切换
