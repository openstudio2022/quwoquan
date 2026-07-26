# L2 Business Capability：圈内推荐闭环 (`in-circle-recommendation-loop`)

> 所属领域：[`circle-community`](../spec.md)
>
> 设计归属：[L1 DEC-002](../design.md#dec-002)

## 1. 能力目标

把圈子生命周期、成员与行为事实转为权限受控的发现候选和稳定排序，并向模型评估链路提供 canonical 输入。

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“in-circle-recommendation-loop”的独立业务结果。
- `circle-service` 单轨拥有候选资格、权限过滤、当前规则排序与发现缓存失效。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。
- 模型训练、发布与评分由 [`recommendation-platform`](../../recommendation-platform/spec.md) 拥有；模型不得绕过 Circle 候选资格与权限过滤。

## 3. Journey / Scenario 贡献

- [`JNY-004 / SCN-001`](../../spec.md#scn-001)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：将 Circle 生命周期、成员和行为事实投影为权限受控的发现候选与稳定排序。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`behavior-ingestion`](./behavior-ingestion/spec.md)：圈子创建后进入推荐候选，归档后退出候选，并接收圈内行为事实。
- [`optimization-feedback`](./optimization-feedback/spec.md)：定义“优化反馈”的可观察主路径、失败语义及父能力交接。
- [`recommendation-ranking`](./recommendation-ranking/spec.md)：定义“推荐排序”的可观察主路径、失败语义及父能力交接。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 圈子发现候选闭环

- active/public 圈子必须进入 `CircleDiscoveryFeed` 推荐候选；归档或不可见圈子必须从候选中移除。
- 圈子行为事实必须通过 append-only、幂等的 `CircleBehaviorFact` 写入，并更新 `weeklyActiveCount`；排序所依赖的投影提交后必须失效发现缓存。
- 当前规则排序必须具有稳定全序与 keyset cursor；模型评分只能细化合格候选顺序，不得改变候选资格或权限。

<a id="req-002"></a>
### REQ-002 跨边界字段、operation 与错误语义只引用所属服务 contracts

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 6. 契约与依赖

- 上游能力：[`circle-community`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循 [L1 DEC-002](../design.md#dec-002)；候选资格与 Circle 权威事实保持单轨，派生缓存允许短暂存在但写后必须主动失效。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 圈子候选、行为投影与归档下线

- GIVEN 两个 active/public 圈子已创建并被同一未入圈用户读取，发现切片已进入缓存。
- WHEN 用户对其中一个圈子产生合法行为事实，随后该圈子被 owner 归档。
- THEN 行为投影使该圈子在 active 排序中前移，且缓存不会返回旧顺序；归档后该圈子不再出现在推荐候选中。
- AND 重放相同行为不得重复计数，伪造 actor 或冲突幂等键必须失败且不产生成功事实。
