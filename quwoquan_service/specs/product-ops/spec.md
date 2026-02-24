# product-ops（产品运营域）

## Purpose

云侧**产品运营服务（Product Ops / Business Ops）**：策略、埋点、实验、访问记录、内容与圈子行为采集，为推荐与运营分析提供业务事件数据。

与平台运维域的边界：
- **product-ops（产品运营）**：业务策略与业务事件数据（可按人群灰度、可审计、可回滚）
- **platform-ops（平台运维）**：可观测性、系统配置、服务治理、可靠性/性能基线（见 `specs/platform-ops/spec.md` 与 `contracts/*`）

> 说明：接口路径仍保持 `/v1/ops/...`（对端侧与契约稳定）；本次仅统一“服务/目录命名”为 `product-ops`，避免与其它 `*-service` 产生歧义。

---

## ADDED Requirements

### Requirement: 埋点接收

系统 MUST 提供统一埋点接收接口，支持 page_access、agent、content_behavior、circle_behavior 等事件类型。

#### Scenario: 页面访问埋点

- **WHEN** 客户端请求 `POST /v1/ops/events` 携带 type=page_access、pageId、timestamp
- **THEN** 系统落库并返回 204

#### Scenario: 内容行为埋点

- **WHEN** 客户端请求 `POST /v1/ops/events` 携带 type=content_behavior、contentId、eventType、duration
- **THEN** 系统落库，可供 Content 推荐消费

#### Scenario: 圈子行为埋点

- **WHEN** 客户端请求 `POST /v1/ops/events` 携带 type=circle_behavior、circleId、eventType
- **THEN** 系统落库，可供 Circle 推荐消费

#### Scenario: 行为数据可供 Content/Circle 消费

- **WHEN** Content 或 Circle 服务需要用户行为作为推荐输入
- **THEN** 系统提供查询或订阅能力，使推荐模块可消费 product-ops 采集的 content_behavior、circle_behavior、page_access、visits 等数据

### Requirement: 实验与分桶

系统 MUST 提供实验配置与分桶查询接口。

#### Scenario: 实验分桶

- **WHEN** 客户端请求 `GET /v1/ops/experiments/{experimentId}/bucket?userId=`
- **THEN** 系统返回该用户的分桶结果

### Requirement: 访问记录

系统 MUST 支持 Visit 类访问记录的存储与查询，与端侧 VisitRecorderService 对接。

#### Scenario: 访问记录同步

- **WHEN** 客户端请求 `POST /v1/ops/visits` 携带 targetKey、visitCount、lastSeenAt 等
- **THEN** 系统落库并返回 204

### Requirement: 日志与可观测关联（运营视角）

系统 MUST 提供可被可观测性体系关联的**业务事件字段**（如 runId/pageId/experimentId 关联字段），使运营分析能与平台日志/trace 在检索层面做关联。

#### Scenario: 日志可关联

- **WHEN** 一次 Run 完成
- **THEN** 可通过 runId 关联 page_access、agent、integrations 等事件与平台侧日志/trace 的检索字段

