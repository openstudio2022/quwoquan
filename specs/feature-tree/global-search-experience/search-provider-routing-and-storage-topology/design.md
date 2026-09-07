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

<a id="dec-002"></a>
### DEC-002 Elasticsearch 作为可替换 SearchIndexView Provider，以单代 Binding 与版本化投影保证一致性
- 决策：Elasticsearch 是当前生产搜索 Provider；替换不得降低现有中文 IK/pinyin、fuzzy/phrase、相关性排序、geo/vector、highlight、PIT 翻页快照与 alias 零停机 rebuild 能力。
- 边界：搜索核心 canonical contract、Planner 与 Provider Port 只表达查询、分页快照、投影写入/删除、重建与代际切换等语义操作，不暴露 Elasticsearch DSL、原始 PIT id、index/alias 细节或厂商响应；DSL、PIT 生命周期和 alias 操作只存在于 Provider Adapter 内。
- 对象与 owner：`SearchIndexView` 是可由领域事实重放或 backfill 重建的 projection，不成为业务写真相源；每个 searchable object 的 source owner 仍属于对应领域，Search 只拥有投影、查询与 Provider 适配。
- Deployment Binding：`search.objects` 是 reader 与全部 writer 共同消费的一个逻辑 deployment binding generation。每代一次性封存 endpoint、read/write alias generation 与按角色引用的 credential，由部署控制面原子激活并 fan-out；reader、writer、admin 分别使用不同的最小权限凭据，任一参与者观察到缺失或混合 generation 必须 fail-closed。
- 一致性与幂等：所有投影 sink 必须在 Provider 内以 source owner 提供的 `sourceVersion` 做原子条件写，拒绝旧版本 upsert；删除必须写入携带 source version 的 tombstone，任何不高于 tombstone version 的迟到或重放 upsert 都不得复活对象。同版本重放保持幂等，不得依赖到达顺序纠正结果。
- Checkpoint：Mongo 只保存每条投影流的 checkpoint/watermark，不与 Elasticsearch 组成分布式事务。Provider 文档或 tombstone 成功后才能推进 checkpoint；两者之间失败时保留旧 checkpoint 并安全重放，由 source-version 条件写吸收重复和乱序。
- Provider 替换：候选 Provider 必须先通过覆盖上述能力的 capability conformance 与 canonical Search SLO conformance，再经受控 projection rebuild、校验和整代 binding 原子切换完成 migration；禁止运行期 Provider fallback、按请求选择 Provider 或由调用方携带 selector。回滚只能恢复到仍满足 freshness/readiness 的上一已验证整代 binding，否则先重建并保持当前代，不能以请求级双路由掩盖失败。
- 拓扑不变量：Elasticsearch、search-service、indexer 与 Mongo 的物理共址或拆分只改变部署与容量，不改变 canonical contract、Planner 语义、source owner、`SearchIndexView` 一致性或 `search.objects` binding generation。
- 理由：当前 Elasticsearch 能力已经构成生产搜索行为基线；将实现细节封在 Adapter、将读写端绑定为同一代并以 source version 驱动 projection，才能在不污染领域 contract 的前提下支持可重建、可迁移和可证明不复活的数据路径。
- 被否决方案：在 contract 或 Planner 中透传 ES DSL/PIT；让 SearchIndexView 接管领域 source owner；reader 与各 writer 独立选择 endpoint/alias 或共用全权凭据；用 Mongo + Elasticsearch 分布式事务、到达顺序或无版本删除维持一致性；以运行期 fallback、请求级 selector、长期双读双写或物理拓扑差异替代受控 migration。
- 失败与恢复：capability/SLO 不满足、binding generation 不一致、凭据越权、投影条件写失败、checkpoint 落后、tombstone 冲突、重建校验失败或切换失败均产生可区分的 typed failure 并阻止成功事实或代际切换；恢复通过重放、backfill、整代重验与原子切换完成。
- 回滚与观测：切换前保留上一已验证 generation 的只读恢复材料；持续观测 canonical Search 延迟/错误率、projection freshness、旧版本拒绝数、tombstone 防复活冲突、checkpoint lag、binding generation skew、rebuild 校验与切换结果，阈值按 canonical Search SLO 告警并阻止迁移或触发整代回滚。
- 测试 seam：Provider conformance 覆盖 IK/pinyin、fuzzy/phrase、相关性、geo/vector、highlight、分页快照和 rebuild；静态 contract test 阻断 ES DSL/PIT 类型越过 Port；binding test 证明 reader/全部 writer/admin 同代且权限隔离；乱序 upsert/delete、重复投递及 Provider 成功但 checkpoint 未推进的故障注入证明旧写拒绝与 tombstone 防复活；migration test 证明 capability/SLO 准入、整代原子切换、整代回滚以及无运行期 selector；同一套 contract test 在共址与拆分拓扑下结果一致。
- 关联要求：`REQ-001`、`REQ-002`
- 影响 Story：[`canonical-search-contract`](./canonical-search-contract/spec.md)、[`search-execution-routing-policy`](./search-execution-routing-policy/spec.md)、[`search-object-taxonomy-and-provider-registry`](./search-object-taxonomy-and-provider-registry/spec.md)、[`search-risky-config-gray-release`](./search-risky-config-gray-release/spec.md)、[`search-storage-topology-and-elasticity`](./search-storage-topology-and-elasticity/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 未来统一高性能读库只替换 read model 实现。
- feature flag、观测、SLO 验证与回滚方案。
