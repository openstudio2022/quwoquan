# L1 特性：runtime（统一运行时能力域）

## 功能说明
- 为所有云侧 **Go 服务**提供统一运行时能力，覆盖配置、错误、可观测、HTTP、RPC、消息、治理、实验与学习闭环。
- 目标是“服务只聚焦业务开发”，横切能力由 runtime 统一封装并复用。
- 不包含独立可部署的微服务（推荐平台下 rec-model-training、rec-model-service 归属 recommendation-platform L1）。

## 约束
- 业务服务不得重复实现横切基础能力，必须复用 runtime 子包。
- runtime 的契约、字段与元数据必须与 `quwoquan_service/contracts/*` 一致。
- runtime 变更必须遵循向后兼容与可回滚原则。

## 验收重点
- A3：治理策略可配置、可灰度、可回滚
- A4：日志/指标/追踪字段统一可检索
- A7：contracts 与 runtime 实现一致
- A8：runtime 级 mock/unit/contract/integration/uat 自动化完整
