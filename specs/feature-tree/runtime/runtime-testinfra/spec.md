# L2 Business Capability：运行时测试基础设施 (`runtime-testinfra`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

以物理目录扫描发现三层测试，以强类型请求按需准备隔离数据，并从真实执行、回读与清理结果生成证据，不维护路径登记、测试清单或 capability registry。

## 2. 范围与非目标

### In Scope

- App / Service / Data / Ops canonical 测试发现
- case ID、测试入口、运行结果、环境和制品摘要闭环
- directory-layout / no-fake / coverage-map 门禁
- Alpha/Beta/Gamma 验收数据的强类型请求、按需 Provider、依赖图、Actor 租约、回读、清理与追加式回执
- 测试数据准备关键路径、operation 数量与阶段耗时治理
- 契约驱动的压测负载生成与 SLO 对照性能证据
- 环境边缘受控故障注入 harness 与故障 profile 闭集

### Out of Scope

- 具体业务断言实现
- 远端环境容量与凭证供给

## 3. Journey / Scenario 贡献

- 横切工程能力：不直接拥有 AppRoot Scenario；业务领域继续拥有产品行为和断言，本能力只提供可审计的测试发现、隔离数据与执行证据。

## 4. Story



- [`test-execution-and-evidence`](./test-execution-and-evidence/spec.md)：按 canonical 目录发现并执行用例，从真实结果生成结构与运行证据。
- [`test-data-provisioning-and-isolation`](./test-data-provisioning-and-isolation/spec.md)：按选中用例的强类型请求图准备、回读和清理最小验收数据。
- [`performance-load-harness`](./performance-load-harness/spec.md)：按 operation 契约生成负载并出具与 SLO 对照的幂等性能证据。
- [`fault-injection-harness`](./fault-injection-harness/spec.md)：以闭集故障 profile 在环境边缘受控注入与恢复，production 装配零侵入。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 三层测试基础设施单轨可追溯

- UAT/DOM/SIT/GWT 只在所属节点定义；真实测试直接写稳定 `spec_ref`，不登记测试文件路径清单。
- App、Service、Data、Ops 测试均能由 canonical 目录直接发现，且不存在 bridge、tracked inventory 或 coverage map。
- runner 报告能由 `spec_ref` 反向关联实际测试、结果、环境和制品摘要。
- directory-layout、no-fake 与动态追踪门禁能独立阻断漂移。

<a id="req-002"></a>
### REQ-002 测试文件必须物理位于 canonical 目录

- 测试文件必须物理位于 canonical 目录；禁止 bridge、历史豁免 allowlist 和手写绿色报告
- `support/` 只保存 fixture、harness、builder，不得保存测试入口

<a id="req-003"></a>
### REQ-003 环境测试数据按强类型请求图最小准备

- 测试代码只引用领域公开的强类型 capability、参数与结果，不书写 capability key、wire path、operation ID、裸字典参数或 Provider 实现。
- Runner 只收集当前选中用例的根请求；控制面只加载其依赖闭包内 Provider，并按依赖图并行执行互不相关节点。
- 内容、Creator、Entity 与已发布 Media 只读引用当前候选绑定的 immutable release；账号与交易事实只经各领域公开 command/event 创建。同源表示采用相同 publish、release、importer、契约和 readback，不表示复制 Prod 数据库。
- 三环境各自消费 environment/target-bound exact handoff；共享 package/release/request，环境自治地绑定 config、import、readiness receipt 与 `candidateBindingDigest`。
- 一个 CaseResult 的一次尝试拥有独立数据实例和 Actor 租约；可变业务事实不得跨 case 复用，清理不确定时必须隔离并阻断。
- Prod 在首条测试数据 mutation 前拒绝，生产/App/Service 制品不得包含测试数据控制面、fixture、租约或回执。

<a id="req-004"></a>
### REQ-004 数据准备性能与证据可比较

- 报告分别记录环境启动、静态门、请求收集、Provider 发现、规划、Actor 准备、每个 capability 的 provision/readback/cleanup、测试正文、回执写入、关键路径和总耗时，以及 operation 数量、加载 Provider、并发度、租约等待与缓存命中。
- 前置失败或提前退出的 run 与完整绿色 run 分开表达，不得进入性能基线。
- 旧基线使用串行、禁 candidate cache 的 benchmark-only policy，候选使用正常并发与 single-flight；benchmark-only 结果不得作为环境正式绿色回执。
- 无 mutation 的 smoke 不执行环境数据准备；单领域用例的额外 Provider 与无关 operation 必须为零。

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

<a id="sit-002"></a>
### SIT-002 验收数据最小化、隔离与性能闭环

- GIVEN Runner 已得到当前选择的真实测试及其强类型根请求，候选、环境和公开契约均有效。
- WHEN 控制面准备、回读、执行并清理本次 CaseResult 所需数据。
- THEN 只加载请求依赖闭包内 Provider，只调用所属领域公开 operation，互不依赖节点并行且结果与串行执行一致。
- THEN immutable release 可只读复用，可变 Actor 与交易事实按 case 隔离；重试同一实例不重复创建，新尝试获得新实例，清理不确定进入隔离并阻断。
- THEN 完整报告可区分环境、数据准备、测试正文与清理耗时，失败早退不污染绿色性能基线，Prod 在任何 mutation 前拒绝。
