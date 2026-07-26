# L2 Business Capability：实验分桶与灰度 (`experiment-bucketing-and-rollout`)

> 所属领域：[`product-ops-growth`](../spec.md)
>
> 设计归属：[L1 DEC-001](../design.md#dec-001)

## 1. 能力目标

让推荐和搜索使用服务端权威分桶并把实际流量归因到同一实验事实；未绑定线上流量的控制面操作必须 fail-closed。

## 2. 范围与非目标

### In Scope

- runtime/experiments 统一 hash resolver 与 recommendation/search 复用
- 推荐曝光/行为和搜索查询事实携带服务端权威 experimentBucket
- Product Ops Experiment/ExperimentAssignmentFact 未绑定 runtime 前 commercial blocked 且 Portal 无入口

### Out of Scope

- Product Ops 控制面向 runtime 的 durable policy 发布与 assignment 回写；该能力启用前须另行冻结规格和 gamma 对账

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
- 推荐实际曝光/行为、搜索查询事实记录服务端权威 experimentBucket，可用于效果归因。
- 未绑定线上流量的 Product Ops Experiment/ExperimentAssignmentFact 操作保持 default-deny。
- Portal 不暴露实验目录、rollout 或 assignment 统计，避免将离线控制面事实冒充线上结果。
- verify_experiment_single_track.py 阻断第二 resolver、热路径回接冻结 assignment API 或 Portal 入口回归。

<a id="req-002"></a>
### REQ-002 分桶口径唯一：`experimentBucket` 维度定义复用 `event-schema-governance`，不得各端各自维护第二套桶映射

- 分桶口径唯一：`experimentBucket` 维度定义复用 `event-schema-governance`，不得各端各自维护第二套桶映射。
- 分桶算法唯一：推荐与搜索必须复用 `runtime/experiments`；禁止业务服务调用未绑定线上热路径的 assignment 接口形成第二套分桶。
- 控制面 fail-closed：未接入实际线上流量的实验控制面必须 default-deny 且无 Portal 入口，不得把离线 assignment 事实冒充线上实验结果。
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
- THEN 未绑定线上流量的 Product Ops Experiment/ExperimentAssignmentFact 操作保持 default-deny。
- THEN Portal 不暴露实验目录、rollout 或 assignment 统计，避免将离线控制面事实冒充线上结果。
- THEN verify_experiment_single_track.py 阻断第二 resolver、热路径回接冻结 assignment API 或 Portal 入口回归。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 experiment bucketing and rollout 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：推荐 recpolicy 与搜索实验复用 runtime/experiments 的单一 AssignBucket 实现。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
