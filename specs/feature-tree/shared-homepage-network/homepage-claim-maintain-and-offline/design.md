# L2 Design：主页认领、维护与下线 (`homepage-claim-maintain-and-offline`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“提供主页从候选、发布、认领维护到现实对象消亡后软下线并保留记录的完整治理链路”需要 `claimed-homepage-basic-maintenance`、`homepage-candidate-intake-and-publish`、`homepage-claim-request-and-review`、`homepage-offline-report-and-history-retention` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：提供主页从候选、发布、认领维护到现实对象消亡后软下线并保留记录的完整治理链路。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`claimed-homepage-basic-maintenance`](./claimed-homepage-basic-maintenance/spec.md)：仅允许认领方维护基础资料，并明确处理越权写入和版本冲突。
- [`homepage-candidate-intake-and-publish`](./homepage-candidate-intake-and-publish/spec.md)：治理方建档候选并在审核后发布。
- [`homepage-claim-request-and-review`](./homepage-claim-request-and-review/spec.md)：定义“认领是共享主页可信治理的关键入口”的可观察主路径、失败语义及父能力交接。
- [`homepage-offline-report-and-history-retention`](./homepage-offline-report-and-history-retention/spec.md)：用户上报状态异常，治理审核后软下线主页并保留历史内容。

## 3. 端云与数据流

- 上游能力：[`shared-homepage-network`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 候选主页统一 intake -> verify -> publish
- 决策：候选主页统一 intake -> verify -> publish。
- 理由：提供主页从候选、发布、认领维护到现实对象消亡后软下线并保留记录的完整治理链路。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`claimed-homepage-basic-maintenance`](./claimed-homepage-basic-maintenance/spec.md)、[`homepage-candidate-intake-and-publish`](./homepage-candidate-intake-and-publish/spec.md)、[`homepage-claim-request-and-review`](./homepage-claim-request-and-review/spec.md)、[`homepage-offline-report-and-history-retention`](./homepage-offline-report-and-history-retention/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 Homepage 写聚合与 viewer-scoped 读模型分离

- 决策：`Homepage` 只拥有主页权威状态与版本 CAS。
- 读侧边界：关注、评分、内容、问答、群组、关系与助手上下文由独立 projection owner 维护，并在 `HomepageDetailView` / `HomepageShellView` 查询边界组合。
- 理由：viewer-scoped 与跨对象最终一致事实不可能属于同一个 Homepage 聚合版本，把它们写入聚合会同时污染一致性边界、加载成本与权限语义。
- 被否决方案：在 `Homepage.fields` 保留 `role: projection`、让查询直接返回写聚合、在 `HomepageShellView` 用裸 `object` 再复制一份投影 shape。
- 约束与影响：`HomepageViewerFollowSlice` 独立于聚合快照，壳层字段必须引用 canonical typed read model。
- 写入约束：命令只更新权威字段，投影只能由 reader/projector 写入。
- 关联要求：`REQ-002`
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- feature flag、观测、SLO 验证与回滚方案。
