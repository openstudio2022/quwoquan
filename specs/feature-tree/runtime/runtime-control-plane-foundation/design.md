# L2 Design：统一控制面基础 (`runtime-control-plane-foundation`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“为 `platform-ops` 与 `product-ops` 提供统一 Web 门户 `ops-portal`，统一门户壳层、全局导航、权限、审计、通知、环境切换与搜索入口”需要 `domain-onboarding-acceptance-governance` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：为 `platform-ops` 与 `product-ops` 提供统一 Web 门户 `ops-portal`，统一门户壳层、全局导航、权限、审计、通知、环境切换与搜索入口。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`domain-onboarding-acceptance-governance`](./domain-onboarding-acceptance-governance/spec.md)：不存在第二真相源，且统一门禁能够发现路径、拓扑、配置和证据漂移。

## 3. 端云与数据流

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 控制面状态归所属服务写入并由统一门户组合查询
- 决策：控制面状态归所属服务写入并由统一门户组合查询。
- 理由：为 `platform-ops` 与 `product-ops` 提供统一 Web 门户 `ops-portal`，统一门户壳层、全局导航、权限、审计、通知、环境切换与搜索入口。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`domain-onboarding-acceptance-governance`](./domain-onboarding-acceptance-governance/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 全局通知：审批、告警、case SLA、灰度中断、回滚结果。
- 全局审计：所有危险动作、配置变更、处置动作可统一检索。
- 全局对象跳转：服务、内容、用户、圈子、实验、case、配置项可跨模块跳转。
- 高危动作趋势、双签通过率、case 周期、配置变更热区、回滚频次。
