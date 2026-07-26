# L2 Business Capability：运行时测试基础设施 (`runtime-testinfra`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

以物理目录扫描和运行报告提供三层测试证据，不维护路径登记或目录清单。

## 2. 范围与非目标

### In Scope

- App / Service / Data / Ops canonical 测试发现
- case ID、测试入口、运行结果、环境和制品摘要闭环
- directory-layout / no-fake / coverage-map 门禁

### Out of Scope

- 具体业务断言实现
- 远端环境容量与凭证供给

## 3. Journey / Scenario 贡献

- [`JNY-001 / SCN-004`](../../spec.md#scn-004)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：以物理目录扫描和运行报告提供三层测试证据，不维护路径登记或目录清单。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`test-engine-and-fixture-framework`](./test-engine-and-fixture-framework/spec.md)：按 canonical 测试目录发现用例，隔离 fixture 与真实依赖，并从执行结果生成证据。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 三层测试基础设施单轨可追溯

- UAT/DOM/SIT/GWT 只在所属节点定义；真实测试直接写稳定 `spec_ref`，不登记测试文件路径清单。
- App、Service、Data、Ops 测试均能由 canonical 目录直接发现，且不存在 bridge、tracked inventory 或 coverage map。
- runner 报告能由 `spec_ref` 反向关联实际测试、结果、环境和制品摘要。
- directory-layout、no-fake 与动态追踪门禁能独立阻断漂移。

<a id="req-002"></a>
### REQ-002 测试文件必须物理位于 canonical 目录

- 测试文件必须物理位于 canonical 目录；禁止 bridge、legacy allowlist 和手写绿色报告
- `support/` 只保存 fixture、harness、builder，不得保存测试入口

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 三层测试基础设施单轨可追溯

- GIVEN 执行“三层测试基础设施单轨可追溯”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“三层测试基础设施单轨可追溯”对应动作。
- THEN UAT/DOM/SIT/GWT 只在所属节点定义，真实测试直接写稳定 `spec_ref`，不登记测试文件路径清单。
- THEN App、Service、Data、Ops 测试均能由 canonical 目录直接发现，且不存在 bridge、tracked inventory 或 coverage map。
- THEN runner 报告能由 `spec_ref` 反向关联实际测试、结果、环境和制品摘要。
- THEN directory-layout、no-fake 与动态追踪门禁能独立阻断漂移。
