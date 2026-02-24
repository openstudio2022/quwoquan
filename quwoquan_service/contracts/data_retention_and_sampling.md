# 数据保留、采样与成本统一规范（Retention / Sampling / Cost）

目标：把日志/trace/体验事件/行为事件的保留与采样标准化，避免“无限制采集”导致成本失控，同时保证排障与优化所需的最小可用数据。

---

## 1. 数据类型与建议策略（初版）

> 具体数值应按真实流量与成本校准；此处给出可先落地的默认建议。

### 1.1 Logs（结构化日志）

- 访问日志：保留 7～14 天（可聚合统计长期保存）
- 错误日志：保留 14～30 天（建议单独索引）
- 过程日志：默认采样或按需开启，保留 7 天以内

### 1.2 Traces（分布式追踪）

- 默认采样（例如 1%～5%），错误/慢请求可提升采样（tail-based sampling）
- 保留 3～7 天（配合日志字段可回溯）

### 1.3 RUM / UX（体验事件）

- 高频事件（jank/帧统计）必须聚合后上报，避免“每帧一个事件”
- 体验事件保留 30～90 天（用于版本对比与回归）
- 关键旅程（P0）的体验事件可更长（如 180 天）但需强聚合

### 1.4 Behavior / Feedback（行为/反馈事件）

- 行为事件（曝光/点击/互动）建议“原始短保留 + 聚合长保留”
  - 原始：7～14 天
  - 聚合（按日/按人群/按版本/按策略）：180 天以上（用于训练与评估）

---

## 2. 采样与聚合原则（强制）

- 优先聚合：按 `endpoint`、`pageId`、`appVersion`、`deviceTier`、`networkType` 维度统计
- 避免高基数：禁止把 userId/postId/conversationId 直接作为 metrics label
- 错误与慢请求：提高采样率（至少保证可排障）

---

## 3. 与公共库的关系（强制）

- 采样策略、日志级别、trace exporter 等必须作为 `sys.*` 系统配置（见 `contracts/configuration.md`），通过 `runtime/config` 统一读取。
- 事件聚合与 envelope 约束必须遵从 `contracts/feedback_and_learning.md` 与 `contracts/messages/envelope.schema.json`。

隐私数据分级与保留期限的可配置策略见：`contracts/privacy_and_security.md`。

