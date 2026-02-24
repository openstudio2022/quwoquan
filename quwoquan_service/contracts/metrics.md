# 统一指标规范（metrics）

目标：各服务暴露指标时具备统一命名、标签与最小集合，便于在 Prometheus/Grafana 或云厂商指标系统中统一看板。

本规范偏“最低可用标准”，支持后续按服务扩展。

---
## 1. 命名约定

- 前缀：`quwoquan_`（仅用于 metrics 名称，避免跨团队/多系统冲突）
- snake_case
- 计数用 `_total`
- 耗时直方图用 `_duration_ms` 或 `_duration_seconds`

示例：
- `quwoquan_http_requests_total`
- `quwoquan_http_request_duration_ms`
- `quwoquan_mq_consume_total`

---
## 2. 必备标签（labels）

| label | 说明 |
|---|---|
| `service` | 服务名 |
| `env` | 环境 |
| `endpoint` | 规范化的路由名（不要用高基数字段，例如完整 path） |
| `method` | HTTP 方法 |
| `status` | 状态码或状态类（2xx/4xx/5xx） |

异步补充：
| label | 说明 |
|---|---|
| `topic` | MQ topic |
| `consumer` | consumer group |
| `result` | ok/error/retry |

---
## 3. 最小指标集合

### 3.1 HTTP
- `quwoquan_http_requests_total{service,env,endpoint,method,status}`
- `quwoquan_http_request_duration_ms{service,env,endpoint,method,status}`（histogram/summary）

### 3.2 错误
- `quwoquan_errors_total{service,env,module,kind,reason}`

### 3.3 MQ（如服务使用）
- `quwoquan_mq_publish_total{service,env,topic,result}`
- `quwoquan_mq_consume_total{service,env,topic,consumer,result}`
- `quwoquan_mq_consume_duration_ms{service,env,topic,consumer,result}`

---
## 4. 与 tracing/log 的关联

建议在产生错误与超时时，同时写日志并打点指标；通过 `traceId/requestId` 在日志中定位具体样本。
