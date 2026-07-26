# L2 Business Capability：运行时实验 (`runtime-experiments`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[L1 DEC-001](../design.md#dec-001)

## 1. 能力目标

统一 runtime hash 分桶、推荐/搜索复用、实际流量归因及未绑定控制面 fail-closed。

## 2. 范围与非目标

### In Scope

- runtime/experiments AssignBucket 与 HashResolver
- recommendation recpolicy 与 search ranking 的 resolver 复用
- 实际曝光/查询事实中的 experimentBucket
- Product Ops Experiment/ExperimentAssignmentFact 冻结门禁

### Out of Scope

- Product Ops 到 runtime 的 durable policy/assignment binding

## 3. Journey / Scenario 贡献

- [`JNY-001 / SCN-004`](../../spec.md#scn-004)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：统一 runtime hash 分桶、推荐/搜索复用、实际流量归因及未绑定控制面 fail-closed。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`experiment-bucket-rollout-runtime`](./experiment-bucket-rollout-runtime/spec.md)：定义“实验分桶灰度运行时”的可观察主路径、失败语义及父能力交接。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 runtime experiments 能力 SIT

- 相同 experimentId、subjectKey 与 bucket 权重始终得到可复现结果。
- recommendation 与 search 不复制 hash 算法，均复用 runtime/experiments。
- 未绑定线上流量的 Product Ops assignment 轨不进入热路径或 Portal。

<a id="req-002"></a>
### REQ-002 提供统一实验分桶与灰度策略运行时

- 提供统一实验分桶与灰度策略运行时；`AssignBucket` 是推荐与搜索当前唯一商用分桶实现。
- 分桶规则必须稳定可复现，且支持版本化。
- 当前策略来源是各业务 metadata/codegen 配置，统一经 `runtime/experiments` 解析；禁止业务服务复制 hash 算法。
- 统一分桶 API 可被服务直接集成。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 runtime experiments 能力 SIT

- GIVEN 执行“runtime experiments 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“runtime experiments 能力”对应动作。
- THEN 相同 experimentId、subjectKey 与 bucket 权重始终得到可复现结果。
- THEN recommendation 与 search 不复制 hash 算法，均复用 runtime/experiments。
- THEN 未绑定线上流量的 Product Ops assignment 轨不进入热路径或 Portal。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 runtime experiments 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：相同 experimentId、subjectKey 与 bucket 权重始终得到可复现结果。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
