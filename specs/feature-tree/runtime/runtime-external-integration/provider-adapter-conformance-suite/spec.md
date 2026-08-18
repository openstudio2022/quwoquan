# L3 Story：Provider 适配器一致性套件 (`provider-adapter-conformance-suite`)

> 所属能力：[`runtime-external-integration`](../spec.md)
>
> Journey / Scenario：[`JNY-007 / SCN-016`](../../../spec.md#scn-016)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，我希望对所有 Provider Adapter 执行同一公共场景和能力专项场景，并分别生成不可提升的 Alpha/Beta/Gamma Debug-local protocol substitute matrix、managed non-prod Remote receipt 与 Prod hosted Remote release receipt，从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

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
- Alpha/Beta/Gamma Debug-local 开发验收选择受管 `protocol_fixture/local_*` Port 对等 Adapter；缺内部协议端点、LiveKit 材料或 health 直接阻断启动和证据生成。
- 普通本地、dirty tree、未评审 commit 或 local attestation 结果必须标记 `nonPromotable=true`。
- 同一环境本次命令新产生的 14×3 格若全部绑定该环境 active immutable candidate、由测试拥有的 CaseResult/cleanup/observability 可复核，则可满足该环境的 Debug-local functional readiness；该结论不要求 CI HMAC，也不得提升商业或发布 readiness。
- 只有 canonical provider-release workflow 在 clean reviewed commit 上重执行、绑定 active immutable candidate 并由 CI attestation authority 签发的完整 matrix evidence 才可标记为 promotable 并参与正式 release matrix readiness，但仍不得替代 managed non-prod/Prod Remote receipt。
- Gamma Debug-local 运行完整第一方拓扑、production Remote composition、独立协议 workload、真实本地 LiveKit 与黑盒 API/模拟器 Journey；禁止 UI Mock、Integration Service 内嵌 listener、运行时跨环境 fallback 和生产租户凭据。
- Alpha/Beta/Gamma 商业 readiness 必须另有各自 managed non-prod Provider Remote receipt；Debug-local matrix 不得提升 managed non-prod 或 Prod 正式 Adapter readiness，Gamma nonprod receipt 不得替代 Prod hosted rollout receipt。
- `identity.sms.otp` 的 Debug-local 协议替代实现必须是 Ops 所有的独立 HTTPS workload，不得以内嵌 Integration Service listener 或固定码实现代替；三目标各自隔离端口、凭据、捕获密钥和存储 namespace，并在 readiness/readback 标记 `nonPromotable=true`。
- SMS substitute harness 必须覆盖认证、E.164/template/trace、幂等冲突、TTL/一次性读取、rate-limit/failure/timeout、跨环境拒绝与脱敏；公开 SendOtp/LoginWithPhone response、日志、指标和报告均不得出现 OTP。
- 人工 OTP 读取只允许由 `stackctl provider-debug otp-read` 在当前 TTY 展示；自动 UAT 只调用受保护的进程内读取接口并立即输入 App，禁止解析 CLI 输出或把 OTP 写入 argv、receipt 与长期 artifact。
- Prod 仅接受 `user_acceptance` Remote receipt：它必须绑定 Prod selected Adapter、Prod config、不可变候选 image、真实用户/运营结果及 health/switch/callback-drain/last-good/rollback receipt。
- runtime.message.transport 的 user_acceptance 只接受受控 endpoint/auth/seed 下的原生设备 chat @ assistant Remote journey；缺该 harness 时 prerequisite 必须 fail-closed， memory Redis、fixture consumer、UI mock 和 Provider override 不得产生 passed cell。
- 每个实际 harness 直接声明其 `spec_ref`、Capability、Adapter、测试层、typed Port、契约来源、断言集合、命令目标和网络边界，并由执行进程写出可校验 CaseResult；不得由聚合器补写成功、断言、数据、清理或观测。
- api_integration 与 user_acceptance 中只断言“应阻断”或 `GATE_BLOCK` 的静态测试不构成 Remote evidence，必须阻断而非降格为通过。
- 同一 Capability 的九格保持同一 typed Port、契约与公共/能力专项断言集合；只有 Prod Remote `user_acceptance` 追加 health/switch/rollback 发布断言。每格绑定当前选中的环境 Adapter，而不是读取既有报告。
- Debug-local functional readiness 只消费当前 `stackctl provider-conformance --environment-matrix` invocation 新生成的 42 格；聚合结果必须显式声明 `readinessScope=local_functional`、`releasePromotionClaimed=false` 和 `attemptEvidenceCount=executed=42`。历史输出、其它环境 evidence、重复 cell 或缺 active candidate receipt 任一出现均阻断当前环境，不得为了复用历史结果扫描聚合成通过。
- Alpha/Beta/Gamma 各 42 格共 126 格若与 iOS Simulator + Android Emulator 的 `emulator_only` matrix 同轮绑定，只能支持 `ALPHA_BETA_GAMMA_EMULATOR_ONLY_FUNCTIONAL_GREEN`；该回执必须 `nonPromotable=true`，不得补写 Android 真机覆盖、不得关闭正式 140-cell 或 Prod Remote blocker。
- 正式 provider-release producer 必须从 generated Binding 动态推导 14 个 required Capability：Alpha/Beta/Gamma 各执行 14×3 层共 42 格，Prod 执行 14 个 native/operator `user_acceptance` 格，总计恰好 140 个唯一 cell。缺失、重复、额外、legacy evidence、local trust 或非 active receipt 任一出现即阻断；run-attempt 使用独立输出根，禁止迁移历史 evidence。

<a id="req-003"></a>
### REQ-003 假报告、动态跳过、输出越界和敏感信息均 fail-closed

- 所有负例有自动化测试且 gate_repo/CI 执行同一检查。
- 每份可用 evidence 同时绑定当前 commit/image/config/ContractGraph/Adapter 与测试源/CaseResult digest、命令、目标、网络边界、断言、logs/traces/metrics、cleanup receipt 及 source-tree/review/candidate/attestation authority 身份；nonprod active candidate 必须由 canonical running/full startup receipt + active deployment manifest + OCI composition 同源证明，Prod 必须由 native/operator readback 与 hosted release readiness 同源证明，validator 必须重新解析当前 receipt 而非信任 evidence 自报。dirty/unreviewed/local-authority/缺 active receipt evidence 必须 fail-closed 为 `nonPromotable=true`。dry-run、旧 digest、零断言、缺观测或缺清理均不能提升 readiness。
- 只有 Prod Remote receipt 追加生产 Adapter health、可切换性和回滚可恢复性；Gamma nonprod receipt 不得替代 Prod hosted receipt。

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

- GIVEN Alpha、Beta、Gamma 环境 artifact 已绑定对应 nonprod Provider Workload，Prod artifact 已绑定正式 Provider Workload，且测试数据与 cleanup 合同完整。
- WHEN 对同一 Capability 执行 local_contract、api_integration 和 user_acceptance。
- THEN 聚合报告恰含九个 required cell，且每格 Provider、网络边界、数据和环境语义匹配。
- AND 每格由该环境 artifact 封存的 Provider Workload 实际执行，并可从 CaseResult 追溯命令、目标、契约、断言、Workload image 与测试 artifact digest。
- AND Alpha/Beta/Gamma Debug-local cell 均绑定各自目标的 Port 对等替代 Adapter；普通本地、dirty tree、未评审 commit 或 local key 生成的 cell 标记 `nonPromotable=true`。
- AND 当前环境本次 invocation 的 42 格在 active immutable candidate、selected Binding、测试源、CaseResult、cleanup 和 observability 全部同源时，允许以 `local-sha256` 满足该环境 functional readiness，且无需 CI attestation key。
- AND 三环境共 126 格与双模拟器 UAT 即使全部通过，也只能形成独立的 emulator-only non-promotable claim；正式准出仍等待 Android 真机、CI-attested 140 格与 Prod Remote receipt。
- AND 历史 evidence 不得补格。
- AND 只有 clean reviewed commit + active immutable candidate + CI attestation authority 的 provider-release 重执行结果可参与正式 release matrix readiness。Gamma cell 额外执行完整第一方拓扑的黑盒 API 与模拟器 Journey，缺 endpoint/health、观测或清理回执时 fail-closed。
- WHEN 对 Alpha/Beta/Gamma 执行商业 Provider readiness。
- THEN 每个环境另有绑定 managed non-prod selected Adapter、不可变候选和真实 Remote 结果的 receipt，且不接受 Debug-local matrix 作为替代。
- WHEN 执行生产商用准出。
- THEN 每个 required Capability 另有一个绑定 Prod Provider Workload、Prod environment artifact 与 hosted topology 的 Remote `user_acceptance` receipt，且不接受 Alpha/Beta/Gamma nonprod matrix 作为替代。
- AND 正式 artifact 恰含 126 个 nonprod cell 与 14 个 Prod cell；`provider-conformance-readiness` 的 `issues/sourceCoverageIssues` 均为空、四环境同一 14 Capability 全部 `required=true/capability_ready=true`，140 个 raw evidence exact bytes 由 manifest/finalizer 收集并由 environment-stability final acceptance 重新推导验证。

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

<a id="open-002"></a>
### OPEN-002 三环境三层测试九格均有真实执行结果

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：由当前 generated Binding 动态派生的全部 executable source 必须被覆盖且 `sourceCoverageIssues=[]`，不得在规格中固化会随 Capability/Adapter 变更而漂移的 source 数量；当前覆盖 14 个 Capability 的 selected Binding × 三层。Prod `user_acceptance` 均有真实 harness，push/message/RTC 另含 Provider two-device native readback。当前真正缺口是 Alpha/Beta/Gamma 尚未在同一 active candidate 上分别执行出 42 格 Debug-local functional evidence，正式 provider-release 也尚未执行出 140 格 CI-attested evidence，且没有 Prod Remote receipt，因此 local Green 与 `gate-release` 均必须阻断。source/harness 存在不得冒充执行通过。
- PublicProvider 的本地 TLS conformance 只证明 Nominatim/OSRM compatible wire，不构成真实公网或 Prod probe。
- Open-Meteo 继续复用 Assistant owner 的 canonical `assistant.weather.forecast` binding，不在 Integration 复制 Adapter。
- `location.poi.search` 与 `location.route.read` 的**真实公网 Provider**（`ext.map.nominatim` / `ext.route.osrm`）在四环境保持未绑定。绑定真实 endpoint 前必须由人工确认自托管/商用 endpoint、Nominatim 使用政策与可识别 User-Agent/联系策略、OSRM 容量与限流政策，并生成绑定 active candidate/config digest 的 Remote receipt。
- Alpha 已将 `location.poi.search` 绑定到受管非生产协议替身 `ext.map.nominatim.protocol_substitute`（endpoint 为 `local_topology:provider-protocol-substitute` 的 `/nominatim` 协议兼容面），其三层自描述 conformance source 已登记且 `sourceCoverageIssues=[]`；UAT 层复用发布选点页真实 journey（`SearchLocations` 公开路径经 `LocationPoiSearchPort`）。替身启用不豁免上一条真实 Provider 政策。
- `location.route.read` 四环境保持 `not_required`：App 当前无路线消费页面，`user_acceptance` 层无法提供真实 user journey，三层 source 无法闭环；替身 `/osrm` 协议兼容面与 `ext.route.osrm.protocol_substitute` adapter 契约已就绪，待 App 路线消费点落地后再启用并补齐三层 source。Beta/Gamma/Prod 的 POI 亦为 `not_required`。
- Open-Meteo 的真实 Remote receipt 同样由其 owner 环境人工政策确认后生成，禁止把公共 demo endpoint 或本地 conformance 结果写成 `passed`。
- 完成判定：`GWT-002` 对应行为满足；每个实际 Capability/Adapter/layer 都有自描述原生 harness，14 个 Capability 在同一候选版本完成 Alpha/Beta/Gamma 九格 evidence 与 Prod Remote receipt，并通过 `--require-ready gamma` 与 `--require-ready prod`。
- 依赖：不可变候选镜像 digest、CI attestation key、Alpha/Beta/Gamma 受管非生产 Provider 材料、Prod 生产厂商材料、受控测试数据与 cleanup/observability 回执，以及 Prod health/switch/rollback 回执。

<a id="open-003"></a>
### OPEN-003 假报告、动态跳过、输出越界和敏感信息均 fail-closed

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：所有负例有自动化测试且 gate_repo/CI 执行同一检查。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效
