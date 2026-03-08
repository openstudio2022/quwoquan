# 开发任务：domain-onboarding-acceptance-governance

## 当前 /prd 交付任务

- [x] P1 确认该需求归属 `runtime-control-plane-foundation`，作为其下统一接入治理子特性
- [x] P2 冻结 `domain_onboarding` 元数据真相源路径与分领域实例模式
- [x] P3 冻结领域最小接入包与“已接入统一控制面”的完成定义
- [x] P4 冻结全局节点与统一实施会话的职责边界
- [x] P5 冻结命令、规则、流程增强边界
- [x] P6 冻结统一 gate 聚合分层与最终集中验收口径
- [x] P7 冻结 plane-aware deployment binding 的目标态
- [x] P8 形成 `spec.md / design.md / tasks.md / acceptance.yaml` 四件套基线

## `/design` 当前交付任务

- [x] D1 设计 `domain_onboarding_schema.yaml` 的字段级 schema、枚举与状态机
- [x] D2 设计 `domains/<domain>.yaml` 与现有 `service.yaml` / `control_plane.yaml` / `workflow.yaml` / `audit_schema.yaml` 的关联关系
- [x] D3 设计 Web / Go / Python / App 对 onboarding metadata 的 codegen 边界
- [x] D4 设计 verify / gate / gate-full 对 onboarding metadata 的消费链路
- [x] D5 设计最终集中验收状态聚合模型与门户展示模型
- [x] D6 设计 `domain-plane -> process` 部署 binding 的真相源与兼容迁移方案
- [x] D7 设计单会话统一接入的模板域策略与实施批次

## 搁置任务（带规划）

- [x] H1 把 `ops-portal` 直接作为接入矩阵状态中心
  - 完成方式：消费 `domainOnboardingSchema.generated.ts` 与 `domainOnboardingDomains.generated.ts`
  - 收口结果：门户已具备统一接入矩阵页面

## 未来演进任务

- [ ] E1 为 `/extend` 增加“领域统一接入矩阵”专用扩展场景
- [x] E2 为 gate 增加领域接入完成度聚合报告
- [x] E3 以 `content` 作为模板域在同一会话内完成首轮接入并验证复制成本
- [x] E4 在同一会话内复制到 `chat / circle / user`
- [x] E5 将 plane-aware deployment binding 纳入 integration / prod 的正式部署门禁
- [x] E6 按 `assistant / rtc / integration / recommendation / ops` 第二梯队推进接入
- [x] E7 为 `notification / realtime` 补齐最小接入包缺口后进入统一收口
