# 角色与范围统一定义（运营 vs 运维/平台）

目的：统一术语，避免“Ops（运营）”与“Ops（运维/SRE）”混用；明确受众、系统边界与归档位置。

---

## 1. 角色与受众

- **运营（Business Ops）**：面向业务策略、内容治理、实验与活动配置。
- **运维/平台（SRE/Platform Ops）**：面向稳定性、可靠性、性能、可观测性、系统配置与应急。
- **研发（Dev）**：实现业务能力与平台接入，保证统一规范落地。

---

## 2. 系统范围（What belongs where）

### 2.1 `product-ops`（产品运营服务，业务域）

**包含**：
- 业务事件/埋点接收（page_access/content_behavior/circle_behavior 等）
- 实验与分桶（A/B、灰度到人群）
- Visit 访问记录（为推荐/分析提供输入）
- 运营策略/治理规则（作为业务数据）

**不包含**：
- 平台日志采集、APM、指标存储、告警系统
- 配置中心（Nacos）、Secrets 管理、服务发现
- SLO、容量、应急演练与 oncall 流程

### 2.2 `platform/observability`（可观测性平台模块）

**包含**：
- 统一日志字段（`contracts/log_fields.md`）
- 统一指标规范（`contracts/metrics.md`）
- 异步链路 envelope（`contracts/messages/envelope.schema.json`）
- 接入脚本/模板、看板与告警模板（后续补齐）

### 2.3 `platform/config`（系统配置平台模块）

**包含**：
- 运维/系统配置的来源分层与治理（env/secrets/config-center/file）
- 本地测试策略与目录约定
- 运维高风险配置的灰度/回滚模板

### 2.4 配置边界（核心约束）

- 运营配置：走 `product-ops`（业务数据，支持按人群灰度与审计）
- 运维/系统配置：走配置中心/Secrets/env（按环境/按服务灰度与审计）
- 详见：`contracts/configuration.md`

---

## 3. 统一归档位置

- 配置分层与治理：`contracts/configuration.md`
- 可观测性字段/指标/异步 envelope：`contracts/log_fields.md`、`contracts/metrics.md`、`contracts/messages/envelope.schema.json`
- 平台模块入口：`platform/observability/`、`platform/config/`
