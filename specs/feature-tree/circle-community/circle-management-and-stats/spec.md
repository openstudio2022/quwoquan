# L2 Business Capability：圈子管理与统计 (`circle-management-and-stats`)

> 所属领域：[`circle-community`](../spec.md)
>
> 设计归属：[L1 DEC-001](../design.md#dec-001)

## 1. 能力目标

为圈子治理与运营提供权限受控的处置、固定口径指标和可下钻运营视图。

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“circle-management-and-stats”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-004 / SCN-001`](../../spec.md#scn-001)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：为圈子治理与运营提供权限受控的处置、固定口径指标和可下钻运营视图。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`kpi-reporting`](./kpi-reporting/spec.md)：定义“KPI 报告”的可观察主路径、失败语义及父能力交接。
- [`moderation-governance`](./moderation-governance/spec.md)：定义“治理”的可观察主路径、失败语义及父能力交接。
- [`ops-dashboard`](./ops-dashboard/spec.md)：定义“运营看板”的可观察主路径、失败语义及父能力交接。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 circle management and stats 能力 SIT

- 本能力必须组合直属 Story 与公开契约，交付“为圈子治理与运营提供权限受控的处置、固定口径指标和可下钻运营视图”所定义的业务结果；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 跨边界字段、operation 与错误语义只引用所属服务 contracts

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 6. 契约与依赖

- 上游能力：[`circle-community`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 circle management and stats 能力 SIT

- GIVEN 执行“circle management and stats 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“circle management and stats 能力”对应动作。
- THEN 直属 Story 共同交付“为圈子治理与运营提供权限受控的处置、固定口径指标和可下钻运营视图”，失败终态可区分且不产生伪成功事实。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 circle management and stats 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：为圈子治理与运营提供权限受控的处置、固定口径指标和可下钻运营视图。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
