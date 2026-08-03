# L2 Business Capability：实验分桶与灰度 (`experiment-bucketing-and-rollout`)

> 所属领域：[`product-ops-growth`](../spec.md)
>
> 设计归属：[L1 DEC-001](../design.md#dec-001)

## 1. 能力目标

让 Product Ops 以公开命令原子发布唯一实验策略，让推荐和搜索消费同一
`ExperimentPolicyActivated` durable fact 完成服务端权威分桶，并把实际流量归因到同一实验事实。

## 2. 范围与非目标

### In Scope

- Product Ops Experiment 聚合的创建、rollout、不可变 revision 与事务 outbox
- `ExperimentPolicyActivated` 是 recommendation/search 唯一的 runtime policy 分发轨
- runtime/experiments 统一 hash resolver 与 recommendation/search 复用
- 推荐曝光/行为和搜索查询事实携带服务端权威 experimentBucket
- 空环境必须经已授权的公开 command 创建首个策略，禁止数据库 seed、服务私有配置或隐式 fallback
- Alpha/Beta/Gamma 使用 target-scoped 受管非生产 operator port；Prod 只接受正式 OIDC operator

### Out of Scope

- Portal 产品交互与生产 rollout 审批流程；它们不能成为 runtime policy 的第二来源

## 3. Journey / Scenario 贡献

- [`JNY-002 / SCN-005`](../../spec.md#scn-005)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：推荐/搜索服务端权威分桶、实际流量事实归因，以及未绑定 Product Ops 控制面的 fail-closed 单轨验收。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`bucketing-strategy-engine`](./bucketing-strategy-engine/spec.md)：以服务端稳定主体键、experimentId 和受控 salt 计算唯一分桶并写入曝光事实。
- [`rollout-audit-and-rollback`](./rollout-audit-and-rollback/spec.md)：按 revision 灰度实验策略，记录操作者与指标判定，并在阈值越界时回退上一份配置。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 experiment bucketing and rollout 能力 SIT

- 推荐 recpolicy 与搜索实验复用 runtime/experiments 的单一 AssignBucket 实现。
- runtime assignment policy 的唯一运行身份由完整策略内容确定性生成 `sha256` 摘要；缺失、禁用或非法策略直接失败，禁止静态版本、not-found 哨兵与隐式 control/50:50 fallback。
- Product Ops `experimentRevision` 冻结 Experiment 聚合的并发修订号和 immutable assignment fact 历史键；它不是 runtime 策略身份，不得成为第二 resolver 或覆盖内容摘要。
- 推荐实际曝光/行为、搜索查询事实记录服务端权威 experimentBucket，可用于效果归因。
- 首个策略和后续 rollout 只经 Product Ops 公开 command、PostgreSQL 聚合与事务 outbox 生效；Search/Recommendation 禁止私有策略 seed。
- Alpha/Beta/Gamma 的 operator substitute 仅限对应 local target 和短时 scope；Prod、release 与未知环境必须配置真实 OIDC 并 fail-closed。
- Portal 是否提供入口不改变 Product Ops contract、权限、审计与 production approval 要求。
- verify_experiment_single_track.py 阻断第二 resolver、私有 runtime config、直接存储 seed 或 assignment write API 回归。

<a id="req-002"></a>
### REQ-002 分桶口径唯一：`experimentBucket` 维度定义复用 `event-schema-governance`，不得各端各自维护第二套桶映射

- 分桶口径唯一：`experimentBucket` 维度定义复用 `event-schema-governance`，不得各端各自维护第二套桶映射。
- 分桶算法唯一：推荐与搜索必须复用 `runtime/experiments`；禁止业务服务调用未绑定线上热路径的 assignment 接口形成第二套分桶。
- runtime 策略身份唯一：只接受 `ExperimentPolicyActivated` 内容摘要；搜索和推荐不得从服务私有 config 读取 bucket 权重，策略缺失或权重不闭合时 readiness/请求 fail-closed。
- 控制面 fail-closed：缺少有效 operator、scope、幂等键、revision、outbox 或 consumer 投影时不产生策略成功回执；Prod 不得使用非生产 operator substitute。
- 实验指标必须复用 `analytics-metric-dictionary` 主口径，不得绕过字典直接进 dashboard。

## 6. 契约与依赖

- 上游能力：[`product-ops-growth`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 experiment bucketing and rollout 能力 SIT

- GIVEN 执行“experiment bucketing and rollout 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“experiment bucketing and rollout 能力”对应动作。
- THEN 推荐 recpolicy 与搜索实验复用 runtime/experiments 的单一 AssignBucket 实现。
- THEN 推荐实际曝光/行为、搜索查询事实记录服务端权威 experimentBucket，可用于效果归因。
- THEN 空环境经 Product Ops 公开 command 创建首个策略，事务 outbox 发布唯一 `ExperimentPolicyActivated`，Search/Recommendation 投影同一 revision 后才 ready。
- THEN Alpha/Beta/Gamma 只接受 target-scoped 短时非生产 operator；Prod 只接受正式 OIDC operator。
- THEN verify_experiment_single_track.py 阻断第二 resolver、私有 runtime config、直接存储 seed 或 assignment write API 回归。
