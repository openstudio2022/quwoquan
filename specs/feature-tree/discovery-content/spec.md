# L1 规格：内容发现与发布

## 范围
- 发现流、推荐排序、内容发布、评论互动、媒体处理与帮读能力。

## 功能说明
- 为端侧首页与内容详情提供统一发现流与内容读取能力，支持按用户画像和行为进行推荐排序。
- 提供内容生产链路（发布、媒体处理、评论、互动）并保证端云契约一致，避免端侧猜字段。
- 把内容行为反馈接入运营闭环，为推荐优化和质量评估提供可追踪数据。

## 约束
- 端侧 UI 必须遵从语义 token（`AppSpacing`/`AppColors`/`AppTypography`），禁止硬编码视觉值。
- 发现流与内容列表响应统一 `items` + `nextCursor`。
- 行为事件必须可被 `product-ops` 消费，且可关联 `traceId/requestId/pageId`。

## 验收标准（L1 重点）
- A1：发现流、发布、评论、互动端到端可用。
- A2：发现链路 p95 延迟达标，首屏体验可度量。
- A7：OpenAPI、metadata、endpoint_catalog 一致。
- A8：mock/unit/contract/integration/uat 自动化映射完整。
