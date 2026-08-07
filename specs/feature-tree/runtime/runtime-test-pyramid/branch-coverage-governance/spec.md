# L3 Story：对象级分支覆盖率治理 (`branch-coverage-governance`)

> 所属能力：[三层测试模型](../spec.md)
>
> Journey / Scenario：不直接参与用户 Journey；证明对象行为的可判定分支已被真实测试触达
>
> 设计归属：[L2 DEC-002](../design.md#dec-002) 与 [DEC-003](../design.md#dec-003)

## 1. 用户价值

作为开发者或审核者，我希望按 canonical 业务对象看到由真实绿测试产生的覆盖结果，从而发现未触达分支、无 owner 源码和被仓库总百分比掩盖的对象级风险。

## 2. 范围与非目标

### In Scope

- production 源码到 domain/context/object 覆盖单元的反向归属。
- App line/branch、服务 statement 与语义 decision table 的对象级结果和不回退棘轮。
- 覆盖结构入口、runner 结果与三层 CaseResult 的证据边界。

### Out of Scope

- 用覆盖率替代 api_integration、user_acceptance、四环境、Provider 或设备验收。
- 人工 coverage registry、固定对象数量、测试文件清单或历史运行台账。
- 为追求百分比执行无业务意义的分支或改变产品语义。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 覆盖单元由 canonical 对象路径实时派生

- 每个计量单元必须由 production 的 domain/context/object 身份反向派生，不能按服务、domain 总量或人工名单合并掉对象差异。
- 无法归属、同优先级多 owner、目标对象无计量单元或测试触达非 production 替身时必须 GATE_BLOCK。
- App 对象报告 line 与 branch 结果。
- Go 对象报告 statement 结果，并用状态机、权限、错误恢复、幂等与边界条件的 decision table 证明语义分支；其他 runtime 使用其原生可判定覆盖能力。

<a id="req-002"></a>
### REQ-002 覆盖棘轮只接受可复核的绿测试结果

- baseline 只能由测试成功且绑定 commit、配置与工具链摘要的 runner 结果形成；失败、跳过、未采集或只有结构入口的对象不得写成已测基线。
- 同一对象的可比结果不得回退；新增 production 分支必须由职责匹配的测试触达，或保持明确未准出状态。
- 快速反馈可以只验证受影响对象，完整准出必须使用相同归属与计算口径覆盖全部受影响对象，不得以仓库总百分比抵消单个对象缺口。

<a id="req-003"></a>
### REQ-003 覆盖结果不替代三层与商业证据

- 源码与对象的可计量关系属于结构证据，line/branch/statement 与 decision table 结果属于 runner 结果证据，两类不得合并成文件存在布尔值。
- 覆盖结果只证明测试触达生产代码，不证明真实依赖、用户终态、Provider、环境、设备、SLO 或回滚已经通过。
- 对象覆盖已达棘轮但 api_integration、user_acceptance 或四环境结果缺失时，整体结论仍保持 GATE_BLOCK。

## 4. 契约引用

- object identity source：`quwoquan_service/services/*/contracts`、`quwoquan_service/control-plane/*/contracts`
- derived object graph：`quwoquan_service/generated/contract_graph.json`
- App source owner：[`AppRoot REQ-010`](../../../spec.md#req-010)
- 测试证据边界：[`three-layer-evidence`](../three-layer-evidence/spec.md)
- 目录与依赖设计：[`system-architecture-and-engineering-guide DEC-018`](../../system-architecture-and-engineering-guide/design.md#dec-018)、[`DEC-019`](../../system-architecture-and-engineering-guide/design.md#dec-019)

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 对象级覆盖结果不会被聚合总量掩盖

- GIVEN 同一 domain 中一个对象已触达全部既有分支，另一个对象存在未触达分支或无 owner 源码。
- WHEN 覆盖治理按 canonical 对象身份计算当前结果。
- THEN 两个对象分别报告，未触达或无 owner 的对象阻断，已覆盖对象的结果不能抵消其缺口。

<a id="gwt-002"></a>
### GWT-002 非绿结果不能建立或抬高覆盖基线

- GIVEN 某对象只有测试入口、跳过结果、失败结果或缺少可复核候选摘要。
- WHEN 系统尝试建立或比较覆盖棘轮。
- THEN 该对象保持未准出，不产生或抬高 baseline，也不能借覆盖结果替代更高层 CaseResult。

## 6. 依赖

- 前置要求：production 文件具有唯一 canonical 对象 owner，三层 runner 能输出可复核 CaseResult。
- 上游事实：对象路径、测试结果、commit/config/toolchain 摘要与语义 decision table。
- 下游结果：对象级覆盖棘轮或 GATE_BLOCK。
- 父级设计：`DEC-002`、`DEC-003`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 对象级覆盖率与绿结果棘轮尚未完整准出

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：当前覆盖计量仍以较粗粒度聚合，App 与服务并非全部对象都有来自绿测试的可比结果，且无 owner 源码与未采集对象尚不能稳定阻断，因此不能证明对象级分支风险已闭环。
- 完成判定：`GWT-001` 与 `GWT-002` 对应行为满足且真实测试 `spec_ref` 有效。
- 依赖：对象 source owner、三层 runner 结果和覆盖 producer 的单轨接线完成。
- 门禁接线现状：`verify_coverage_ratchet.py --scope cloud|service` 在对象 source
  owner 单轨闭合前 fail-closed，会在 `go test -coverprofile` 采集之前返回
  `GATE_BLOCK`，因此不产出任何覆盖数据。`quwoquan_ops/gate/gate_repo.sh` 的
  `run_service` 曾无条件调用它，使该阶段恒为红且零证据；该调用已移除，工具侧
  fail-closed 行为保留。当 OPEN 关闭且云侧具备 canonical object source owner、
  `-coverpkg` 能按对象产出数据时，必须同时把调用按 `--scope cloud` 重新接回
  `run_service`。
- App scope 现状：`discover_app_units()` 对 `quwoquan_app/lib/l10n/**` 等无 owner
  的横切目录 fail-closed，导致 baseline 中没有任何 `app:` 单元；该项归属
  `object_path_map` 对象归属工作，与本 OPEN 的云侧缺口分属两条链路。
