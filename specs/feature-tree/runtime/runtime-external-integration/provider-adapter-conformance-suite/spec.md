# L3 Story：Provider 适配器一致性套件 (`provider-adapter-conformance-suite`)

> 所属能力：[`runtime-external-integration`](../spec.md)
>
> Journey / Scenario：[`JNY-007 / SCN-016`](../../../spec.md#scn-016)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，我希望对所有 Provider Adapter 执行同一公共场景和能力专项场景，并生成可防伪、可聚合的 Alpha/Beta/Gamma local-substitute 九格 matrix，以及独立的 Prod hosted Remote release receipt，从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- 公共 scenario、fault model、能力专项 profile 和原生 harness
- 3×3 evidence schema、digest/freshness、观测引用、清理回执与防假绿
- output/Secret/PII 隔离

### Out of Scope

- 用一套跨语言测试代码替代各语言原生 harness
- 在测试中动态 skip 不可用 Provider 或回退 Mock

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 公共场景不可删减且能力专项语义可扩展

- success、validation、auth、network/DNS、timeout、throttle、retry、idempotency、 callback ordering、redaction、observability 均被同一 Adapter 执行。

<a id="req-002"></a>
### REQ-002 三环境三层 conformance matrix 与 Prod Remote receipt 均有真实执行结果

- local_contract 对对应环境 Adapter 类运行离线 harness
- api_integration 使用真实协议
- user_acceptance 验证真实用户或运营结果。
- Alpha/Beta/Gamma 仅选择 Port 对等 local substitute；缺替代 endpoint/credential 直接阻断启动和证据生成。
- Gamma 运行完整第一方拓扑、production Remote composition、黑盒 API 与真机 Journey；禁止 UI Mock 或 Provider override，但不访问真实第三方租户、不要求真实第三方凭据。
- Alpha/Beta/Gamma substitute 结果不得提升 Prod 真实 Adapter readiness；Gamma substitute receipt 不得替代 Prod hosted rollout receipt。
- Prod 仅接受 `user_acceptance` Remote receipt：它必须绑定 Prod selected Adapter、Prod config、不可变候选 image、真实用户/运营结果及 health/switch/callback-drain/last-good/rollback receipt。
- runtime.message.transport 的 user_acceptance 只接受受控 endpoint/auth/seed 下的原生设备 chat @ assistant Remote journey；缺该 harness 时 prerequisite 必须 fail-closed， memory Redis、fixture consumer、UI mock 和 Provider override 不得产生 passed cell。
- 每个实际 harness 直接声明其 `spec_ref`、Capability、Adapter、测试层、typed Port、契约来源、断言集合、命令目标和网络边界，并由执行进程写出可校验 CaseResult；不得由聚合器补写成功、断言、数据、清理或观测。
- api_integration 与 user_acceptance 中只断言“应阻断”或 `GATE_BLOCK` 的静态测试不构成 Remote evidence，必须阻断而非降格为通过。
- 同一 Capability 的九格保持同一 typed Port、契约与公共/能力专项断言集合；只有 Prod Remote `user_acceptance` 追加 health/switch/rollback 发布断言。每格绑定当前选中的环境 Adapter，而不是读取既有报告。

<a id="req-003"></a>
### REQ-003 假报告、动态跳过、输出越界和敏感信息均 fail-closed

- 所有负例有自动化测试且 gate_repo/CI 执行同一检查。
- 每份可用 evidence 同时绑定当前 commit/image/config/ContractGraph/Adapter 与测试源/CaseResult digest、命令、目标、网络边界、断言、logs/traces/metrics 和 cleanup receipt；dry-run、旧 digest、零断言、缺观测或缺清理均不能提升 readiness。
- 只有 Prod Remote receipt 追加真实 Adapter health、可切换性和回滚可恢复性；Gamma substitute receipt 不得替代 Prod hosted receipt。

<a id="req-004"></a>
### REQ-004 允许能力专项 profile 追加协议场景，但不得删减公共场景

- 允许能力专项 profile 追加协议场景，但不得删减公共场景。
- `api_integration` 必须连接该环境声明的真实 Provider/兼容服务，不得改跑内存实现。
- `user_acceptance` 必须验证用户或运营结果、失败提示、恢复与可查询观测。
- evidence 仅记录 `endpointRef/secretRef/configDigest`，不得记录实际 endpoint、环境变量、credential、token 或 PII。

## 4. 契约引用

- canonical：`specs/feature-tree/runtime/runtime-external-integration/spec.md`
- canonical：`quwoquan_ops/environments/provider_conformance_evidence.schema.json`
- 测试治理：[`runtime-test-pyramid`](../../runtime-test-pyramid/spec.md)
- canonical：[`runtime-external-integration` SIT](../spec.md#sit-003)
- canonical：`quwoquan_ops/environments/output_layout_manifest.yaml`
- canonical：`specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 公共场景不可删减且能力专项语义可扩展

- GIVEN 对象 operations 声明 Capability、canonical Port 和 conformance profile，环境绑定选择实际 Adapter。
- WHEN Conformance compiler 解析公共场景、能力专项场景和该 Adapter 的 harness 映射。
- THEN 每个 required 公共场景恰有一个可执行映射，专项场景只能追加不能覆盖或删除公共场景。

<a id="gwt-002"></a>
### GWT-002 三环境三层 conformance matrix 与 Prod Remote receipt 均有真实执行结果

- GIVEN Alpha、Beta、Gamma Binding 已选择对应 Adapter，测试数据和 cleanup 合同完整。
- WHEN 对同一 Capability 执行 local_contract、api_integration 和 user_acceptance。
- THEN 聚合报告恰含九个 required cell，且每格 Provider、网络边界、数据和环境语义匹配。
- AND 每格由该环境 Binding 选中的 Adapter 实际执行，并可从 CaseResult 追溯命令、目标、契约、断言与测试 artifact digest。
- AND Alpha/Beta/Gamma cell 均绑定各自环境的 Port 对等 local substitute；Gamma cell 额外执行完整第一方拓扑的黑盒 API 与真机 Journey，缺替代 endpoint/credential、观测或清理回执时 fail-closed。
- WHEN 执行生产商用准出。
- THEN 每个 required Capability 另有一个绑定 Prod selected Adapter 与 hosted topology 的 Remote `user_acceptance` receipt，且不接受 Alpha/Beta/Gamma substitute matrix 作为替代。

<a id="gwt-003"></a>
### GWT-003 假报告、动态跳过、输出越界和敏感信息均 fail-closed

- GIVEN 聚合器收到 report、观测 artifact 与 output path。
- WHEN report 含 NOT_RUN/required skip/零断言/dry-run，或路径/内容含配置、Secret、TLS、PII。
- THEN 对应 cell 判 FAIL，Adapter/Capability readiness 均不能提升。
- AND api_integration/user_acceptance 的静态 “should block” 或 `GATE_BLOCK` 断言、旧 source/config/ContractGraph/Adapter/image digest、缺观测或缺 cleanup receipt 均不得成为 evidence。

## 6. 依赖

- 前置要求：[`runtime-external-integration`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 公共场景不可删减且能力专项语义可扩展

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：success、validation、auth、network/DNS、timeout、throttle、retry、idempotency、 callback ordering、redaction、observability 均被同一 Adapter 执行。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 三环境三层测试九格均有真实执行结果

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前只有 B10 三个真实 Adapter 的 Remote UAT source，尚不能为 14 个 Capability 的全部 selected Binding 生成九格真实证据或 Prod Remote receipt，因此 `gate-release` 必须阻断。
- 完成判定：`GWT-002` 对应行为满足；每个实际 Capability/Adapter/layer 都有自描述原生 harness，14 个 Capability 在同一候选版本完成 Alpha/Beta/Gamma 九格 evidence 与 Prod Remote receipt，并通过 `--require-ready gamma` 与 `--require-ready prod`。
- 依赖：不可变候选镜像 digest、CI attestation key、Alpha/Beta/Gamma substitute 材料、Prod 生产厂商材料、受控测试数据与 cleanup/observability 回执，以及 Prod health/switch/rollback 回执。

<a id="open-003"></a>
### OPEN-003 假报告、动态跳过、输出越界和敏感信息均 fail-closed

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：所有负例有自动化测试且 gate_repo/CI 执行同一检查。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效
