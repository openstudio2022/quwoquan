# L2 Design：搜索 Provider 路由与存储拓扑 (`search-provider-routing-and-storage-topology`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“统一搜索 contract、对象 taxonomy、Provider 路由、显式降级、本地搜索生命周期与云侧派生读模型，为全屏搜索和页面内 picker 提供同一查询边界”需要 `canonical-search-contract`、`circle-group-hybrid-fallback-contract`、`local-search-lifecycle-and-account-isolation`、`search-execution-routing-policy`、`search-object-taxonomy-and-provider-registry`、`search-risky-config-gray-release`、`search-storage-topology-and-elasticity` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：统一搜索 contract、对象 taxonomy、Provider 路由、显式降级、本地搜索生命周期与云侧派生读模型，为全屏搜索和页面内 picker 提供同一查询边界。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`canonical-search-contract`](./canonical-search-contract/spec.md)：页面与业务层只看到一个 contract，商用字段以 metadata 为唯一真相源。
- [`circle-group-hybrid-fallback-contract`](./circle-group-hybrid-fallback-contract/spec.md)：fallback 必须返回 typed `resolvedFrom=local_fallback`。
- [`local-search-lifecycle-and-account-isolation`](./local-search-lifecycle-and-account-isolation/spec.md)：定义“本地搜索生命周期与账号隔离”的可观察主路径、失败语义及父能力交接。
- [`search-execution-routing-policy`](./search-execution-routing-policy/spec.md)：定义“搜索执行路由策略”的可观察主路径、失败语义及父能力交接。
- [`search-object-taxonomy-and-provider-registry`](./search-object-taxonomy-and-provider-registry/spec.md)：location 成为 canonical search 可召回的一类对象，且 geo 维度机制仅一套。
- [`search-risky-config-gray-release`](./search-risky-config-gray-release/spec.md)：每个发布 revision 必须绑定兼容镜像范围和配置摘要；环境 overlay 不得包含真实 endpoint 密钥、password 或 token。
- [`search-storage-topology-and-elasticity`](./search-storage-topology-and-elasticity/spec.md)：搜索读请求只走 metadata 只读 API + 注入 CloudRequestHeaders 审计；多读切片按 objectType 独立弹性。

## 3. 端云与数据流

- 上游能力：[`global-search-experience`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 统一搜索 Contract 与 Planner，读模型实现可替换
- 决策：统一搜索 Contract 与 Planner，读模型实现可替换。
- 理由：统一搜索 contract、对象 taxonomy、Provider 路由、显式降级、本地搜索生命周期与云侧派生读模型，为全屏搜索和页面内 picker 提供同一查询边界。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`canonical-search-contract`](./canonical-search-contract/spec.md)、[`circle-group-hybrid-fallback-contract`](./circle-group-hybrid-fallback-contract/spec.md)、[`local-search-lifecycle-and-account-isolation`](./local-search-lifecycle-and-account-isolation/spec.md)、[`search-execution-routing-policy`](./search-execution-routing-policy/spec.md)、[`search-object-taxonomy-and-provider-registry`](./search-object-taxonomy-and-provider-registry/spec.md)、[`search-risky-config-gray-release`](./search-risky-config-gray-release/spec.md)、[`search-storage-topology-and-elasticity`](./search-storage-topology-and-elasticity/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 未来统一高性能读库只替换 read model 实现。
- feature flag、观测、SLO 验证与回滚方案。
