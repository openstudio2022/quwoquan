# L3 Story：CAPABILITYProvider 商用就绪门禁 (`capability-provider-commercial-readiness-gate`)

> 所属能力：[`runtime-external-integration`](../spec.md)
>
> Journey / Scenario：[`JNY-007 / SCN-016`](../../../spec.md#scn-016)
>
> 设计引用：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，我希望由同一版本的真实证据计算 Adapter 和 Capability 两级 readiness，并以 fail-closed 启动、降级、切换、回滚和 Prod deploy gate 阻断假商用，从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- Adapter/Capability 双层状态计算、启动 preflight 和 readiness
- required/optional 降级语义、Provider 切换、config+image 回滚
- Alpha/Beta/Gamma protocol substitute/local infrastructure 与 Prod 真实厂商分层准出

### Out of Scope

- 人工修改 ready 状态
- 用替代 Adapter、Prod smoke 或历史 report 提升目标 Adapter
- 未实现 provider-neutral boundary、真实 consumer 与启动 preflight 的 NATS/DNS release readiness

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 Adapter 与 Capability 状态独立且证据同版本

- 替代 Adapter 通过、旧 digest、不同 commit/image/config 或缺目标厂商证据均不能 提升目标 adapter_ready。

<a id="req-002"></a>
### REQ-002 required Provider 缺失或未就绪时启动失败

- readiness 端点 `/readyz` 不泄露 endpoint/Secret，Remote 失败不返回 fixture/空集合/固定成功。
- 每项 required Capability 的 root-scoped descriptor、composition entrypoint 与 resolver symbol 经 BindingCompiler 静态校验；descriptor 缺失、漂移或未消费均阻断。

<a id="req-003"></a>
### REQ-003 只在 ready Adapter 间切换并原子回滚

- 用户 Journey 连续、数据结果一致、指标按 release/adapter 可查询，失败时无 Mock fallback。

<a id="req-004"></a>
### REQ-004 非生产 Provider 九格与 Prod hosted 正式厂商证据独立计算

- 每个 target 的 required Capability 集合必须从当前候选的 generated target Binding 中动态枚举；门禁不得维护固定 Capability 清单或数量。Alpha/Beta/Gamma 九格验证环境选中的受管 **protocol substitute/local infrastructure** Adapter 健康、Port 同源 assertion 与逐级增强的第一方黑盒结果；required 数据集不接受 App/UI Mock、运行时 fallback 或未经 Binding 的 override。
- `prod-sim` 仍是 `environment=prod` 的本机 package-bound Provider rehearsal target，不形成第五环境。候选在 package/candidate 阶段封存 target-scoped、Port 对等 protocol substitute/local infrastructure Binding 并运行完整第一方服务；无论法务占位是否消除都固定 `nonPromotable=true`。
- `prod-sim` 每项 required Capability 都必须由其 owner 的第一方 Service（由 integration-service 所有时即由 Integration 黑盒入口）发起至少一次非零调用，并同源绑定 Provider invocation、可观察 effect/readback、cleanup 与 logs/traces/metrics。其证据 scope 只能为 `local_rehearsal` / `local_functional`，不得置任何 Prod `adapter_ready` / `capability_ready` 为 true，也不得关闭真实厂商 receipt 缺口。零调用、required skip、旧 receipt 或只探测 `/healthz` 均失败。
- `prod-hosted` deploy gate 只接受当前版本真实厂商 Adapter、真实凭据和正式 hosted rollout/health/switch/callback-drain/last-good/rollback receipt；fixture、protocol substitute 与 local infrastructure workload 必须拒绝，缺凭据、远端租户或审批时保持 blocked。
- Prod smoke 不反写非生产九格；Alpha/Beta/Gamma nonprod receipt 与 `prod-sim` local rehearsal 均不得提升 Prod 目标厂商 adapter_ready，也不得替代 Prod hosted rollout receipt。

<a id="req-005"></a>
### REQ-005 optional Provider 不可用时只允许结构化关闭并提供用户指引

- optional Provider 不可用时只允许结构化关闭并提供用户指引。
- Provider 失败不得返回 fixture、空集合、固定成功或自动切 Mock。
- 仅允许在两个 `adapter_ready=true` 的 production-grade Adapter 之间切换。

## 4. 契约引用

- canonical：`quwoquan_service/contracts/metadata`
- configuration：`quwoquan_service/services/integration-service/config/schema.yaml` 与 `quwoquan_service/services/integration-service/environments/`
- canonical：`specs/feature-tree/runtime/runtime-external-integration/design.md`
- canonical：[`runtime-external-integration` SIT](../spec.md#sit-004)
- 测试治理：[`runtime-test-pyramid`](../../runtime-test-pyramid/spec.md)
- canonical：`quwoquan_ops/environments/provider_conformance_evidence.schema.json`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 Adapter 与 Capability 状态独立且证据同版本

- GIVEN 对象 operations 声明 Capability，环境绑定选择至少一个 production-grade Adapter。
- WHEN readiness compiler 聚合 Conformance、九格、观测、切换和回滚证据。
- THEN 每个 Adapter 独立计算 adapter_ready；Capability 只在至少一个生产 Adapter ready 且 能力级条件全部满足时为 ready。

<a id="gwt-002"></a>
### GWT-002 required Provider 缺失或未就绪时启动失败

- GIVEN 四环境 Binding 声明 required 与 optional Capability。
- WHEN required Binding、Secret、Adapter 初始化或健康探针缺失，或 optional Provider 不可用。
- THEN required 失败阻止进程 ready；optional 只产生结构化 unavailable/degraded。

<a id="gwt-003"></a>
### GWT-003 只在 ready Adapter 间切换并原子回滚

- GIVEN Primary 与 secondary 均为 production-grade 且 adapter_ready。
- WHEN 触发受控切换、故障演练或回滚。
- THEN 合同/数据/幂等/callback/指标兼容，旧流量收口，config+image 成对回滚到 last-good。

<a id="gwt-004"></a>
### GWT-004 非生产 Provider 九格与 Prod hosted 正式厂商证据分层

- GIVEN 当前候选同时具有 `environment=prod,target=prod-sim` 与 `environment=prod,target=prod-hosted` 的 generated target Binding。
- WHEN 执行 `prod-sim` Provider rehearsal gate。
- THEN 门禁从 `prod-sim` Binding 动态枚举全部 `required=true` Capability，并逐项验证第一方 Service/Integration 黑盒调用与同一 attempt 的 Provider invocation/effect/readback/cleanup/logs/traces/metrics；expected invocation count 为零、required skip、旧 receipt、重复补格或仅 `/healthz` 成功时均 fail-closed。
- AND 通过结果只写 `readinessScope=local_rehearsal|local_functional`、`releasePromotionClaimed=false` 与 `nonPromotable=true`；legal-static 是否仍含占位不得改变 `nonPromotable`，也不得产出 Prod Adapter/Capability ready 事实。
- WHEN 执行 `prod-hosted` gray_initial deploy gate。
- THEN Alpha/Beta/Gamma 当前版本 protocol substitute/local infrastructure Adapter 的九格证据必须齐备，且从 `prod-hosted` Binding 动态枚举的每个 required Capability 都具有当前版本真实厂商 Adapter、真实凭据与正式 hosted rollout/health/switch/callback-drain/last-good/rollback receipt 才允许继续。
- AND `prod-sim`/nonprod evidence、fixture/local workload、零调用、required skip、旧 receipt 或只有 `/healthz` 的结果均不得满足该 hosted receipt；任一层证据不得替代另一层。

## 6. 依赖

- 前置要求：[`runtime-external-integration`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 Adapter 与 Capability 状态独立且证据同版本

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：替代 Adapter 通过、旧 digest、不同 commit/image/config 或缺目标厂商证据均不能 提升目标 adapter_ready。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 required Provider 缺失或未就绪时启动失败

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：readiness 端点 `/readyz` 不泄露 endpoint/Secret，Remote 失败不返回 fixture/空集合/固定成功。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 只在 ready Adapter 间切换并原子回滚

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：用户 Journey 连续、数据结果一致、指标按 release/adapter 可查询，失败时无 Mock fallback。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-004"></a>
### OPEN-004 本地演练与 Prod hosted readiness scope 隔离

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：本项只跟踪门禁对 `local_rehearsal` / `local_functional` 与 Prod readiness 的 scope 隔离、动态 Binding 枚举和 fail-closed 消费；真实厂商材料与 hosted receipt 的执行缺口继续唯一归属 [`provider-adapter-conformance-suite` OPEN-002](../provider-adapter-conformance-suite/spec.md#open-002)，不得在此复制第二份缺口。
- 完成判定：`GWT-004` 对应行为满足且真实测试 `spec_ref` 有效
