# L2 Business Capability：运行时外部集成 (`runtime-external-integration`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

以能力专属 typed Port、Provider Adapter、构建期 BindingCompiler、统一 Conformance Suite、3×3 证据和双层 readiness 隔离第三方差异；integration-service 只是 runtime 治理的一种部署形态。

## 2. 范围与非目标

### In Scope

- Capability/Adapter/环境 Binding 单轨注册、显式 composition 与启动 fail-closed
- Alpha/Beta/Gamma × local_contract/api_integration/user_acceptance 的受管非生产 Provider 九格证据
- 统一错误、超时/取消、幂等、隐私、观测、成本、降级、切换与回滚
- SLS、MQ、DNS、RTC、LLM 首波及其余现存外部依赖的分波迁移

### Out of Scope

- 为无产品需求的未来能力预造万能 Provider
- 运行时扫描 metadata、动态选厂或以 Mock/Fake 作为 **Prod** fallback
- 在 Alpha/Beta/Gamma 注入生产租户凭据，或用任一 sandbox/nonprod evidence 冒充 Prod hosted readiness

## 3. Journey / Scenario 贡献

- [`JNY-007 / SCN-016`](../../spec.md#scn-016)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：以能力专属 typed Port、Provider Adapter、构建期 BindingCompiler、统一 Conformance Suite、3×3 证据和双层 readiness 隔离第三方差异，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`capability-provider-commercial-readiness-gate`](./capability-provider-commercial-readiness-gate/spec.md)：替代 Adapter 通过、旧 digest、不同 commit/image/config 或缺目标厂商证据均不能 提升目标 adapter_ready。
- [`integration-service-foundation`](./integration-service-foundation/spec.md)：对外只暴露标准化接口，禁止端侧直接调用供应商 API。
- [`provider-adapter-conformance-suite`](./provider-adapter-conformance-suite/spec.md)：success、validation、auth、network/DNS、timeout、throttle、retry、idempotency、 callback ordering、redaction、observability 均被同一 Adapter 执行。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 能力专属 Port、Adapter 隔离与访问策略

- 每项外部能力有唯一 canonical typed Port；Vendor SDK/type/endpoint/error/callback DTO 只存在于登记的 Adapter 路径。
- Adapter 恰属 central_integration、domain_owned_adapter、client_platform_adapter、 data_pipeline_adapter 之一；豁免不绕过注册、合同、测试和商用门禁。
- application/domain/UI 不直接读取第三方配置、环境变量或 Vendor DTO。

<a id="req-002"></a>
### REQ-002 构建期 Binding、显式装配与逐能力 readiness

 - 对象 `operations.yaml` 的 external dependency、服务本地环境 Binding、派生
   receipt/descriptor、SBOM 与 acceptance 双向一致；不得维护全局 registry、binding
   file 或 conformance manifest。
- BindingCompiler 只在构建/门禁阶段运行；运行时不扫描 metadata 或按字符串动态选厂。
- content embedding、user one-tap/social、integration location/SMS/Push、assistant model、 RTC room 与 runtime SLS 各自产出 root-scoped checked-in Go descriptor，并由对应 composition entrypoint fail-closed 消费。
- runtime.message.transport 使用唯一 Redis Adapter Binding；其所有实际 producer/ consumer root 共享同一环境选择、各自产出 descriptor 并在 publisher/consumer 构造前 preflight Redis scene。任何 root 直接构造未校验 transport、静默跳过 consumer 或把 Pub/Sub 当作 durable delivery 均为阻断。
- runtime NATS 与 DNS 显式声明生产消费为 none，仅为资产登记；不得列为 release-required、不得生成 release Binding 或冒充 readiness 证据。
- Alpha/Beta/Gamma 缺受管非生产 Provider 材料、初始化、conformance 或健康探针时启动失败；stackctl 不自动生成 Provider endpoint/secret。
- Prod 缺 **真实厂商** Provider、外部注入凭据、初始化或健康探针时启动失败，并拒绝 local substitute Adapter。
- optional 能力仅结构化 unavailable/degraded，绝不假成功。
- readiness 只暴露 capability/adapter ID、状态、版本、digest 和 evidence URI，不暴露 endpoint、Secret 或 token。

<a id="req-003"></a>
### REQ-003 Provider 公共/专项 Conformance 与 Alpha/Beta/Gamma 九格证据

- 公共 suite 覆盖 success、validation、auth、network/DNS、timeout、throttle、retry、 idempotency、redaction 与 observability；能力专项 profile 覆盖本能力协议语义。
- Alpha/Beta/Gamma 各自执行 local_contract、api_integration、user_acceptance；环境不是 第四测试目录层。
- local_contract 对对应环境 Binding 选中的 Adapter 类运行离线协议/故障 harness，永不访问外网；api_integration 连接该环境声明的协议端点：Alpha/Beta/Gamma 连接隔离 sandbox/nonprod tenant，Prod Remote receipt 连接生产厂商租户。
- runtime.message.transport 的 user_acceptance 只能以 production Remote composition 的 原生设备 chat @ assistant journey 取证，并受 stackctl 解析的 endpoint、CI 注入的 auth 和环境 seed 约束；未登记该 harness 时必须输出 PROVIDER.CONFORMANCE.REMOTE_CHAT_ASSISTANT_UAT_HARNESS_REQUIRED 并 GATE_BLOCK， 不得用 memory Redis、fixture consumer、UI mock 或 Provider override 生成 passed。
- 每格报告含当前 commit/image/config/ContractGraph/Adapter digest、断言/skip、网络边界、 数据 digest、acceptance refs 与 logs/traces/metrics 引用。
- NOT_RUN、required skip、零断言、dry-run、旧 digest、缺观测或缺清理回执均阻断。

<a id="req-004"></a>
### REQ-004 Provider 故障、降级、替换与原子回滚

- required Provider 不可用且无 ready 备选时阻断 rollout；optional 能力关闭时返回结构化 指引，禁止切 Mock 或本地合成成功。
- 切换只发生在两个 ready 的 production-grade Adapter 之间，并验证合同/数据兼容、 用户 Journey 连续、指标口径一致和旧 callback 收口。
- config+image 成对发布和回滚；last-good 可恢复且回滚后健康、数据与用户结果一致。

<a id="req-005"></a>
### REQ-005 输出目录、Secret 与 evidence 隔离

- Provider 配置、环境 Binding、schema、policy、endpoint/secret 值、渲染 `.env`、 证书和 TLS 状态均不进入 `.qwq_output`。
- 输出根 `.qwq_output` 只含可删除重建的 runs/observability/process/cache 分类产物
- deploy payload、渲染配置、Caddy、TLS 与 env 文件写入 `QWQ_DEPLOY_WORK_ROOT/<target>/`
- process 不含 config/PKI，evidence 只含 ref/digest 和脱敏状态。
- 删除 `.qwq_output` 后可仅凭版本控制真相源和显式外部依赖重建。

<a id="req-006"></a>
### REQ-006 Alpha/Beta/Gamma 受管非生产 Provider 与 Prod hosted 分层对接

- `runtime_shared_adapter` 由多个静态组合根共同消费；每个 composition root 必须引用同一公开 Port 与 Adapter 契约，禁止复制实现。
- **Alpha / Beta / Gamma** required 验收必须绑定受管非生产租户的非内存 Provider Adapter，`state: enabled`；endpoint 与 secret 只由受保护环境注入，缺失时在 stackctl preflight 返回 `GATE_BLOCK`，不得生成或回退到 fixture/mock/local recorder/local capture。
- **Gamma（gamma-local 拓扑）** 同时运行 production Remote composition、完整第一方拓扑、黑盒 API 与真机 Journey；禁止 UI Mock、Provider override、进程内 Provider fake 或生产租户凭据。Provider 使用隔离的 sandbox/nonprod tenant，但不得改变 canonical Port。
- **Prod（含 gray）** 只允许真实厂商 Adapter 与生产租户，禁止 fixture/mock/fake/local_* 替代 Adapter；Prod hosted rollout receipt 独立绑定 Prod config/topology，不能由 Gamma receipt 替代。
- Alpha/Beta/Gamma 的 canonical Port、assertionIds 与 ContractGraph 必须一致，Provider receipt 必须绑定同一候选且禁止 UI 假绿。
- Prod 缺正式凭据时 fail-closed 并 GATE_BLOCK；不得用 Alpha/Beta/Gamma sandbox/nonprod receipt 冒充 Prod hosted readiness。
- deadline、cancel、幂等、retry/throttle 必须由能力合同约束，调用方不得猜测 Vendor 行为。
- credential、token、原始 endpoint 与 PII/SECRET 不得进入日志、trace、metric label 或运行证据正文；stackctl 不得自动生成 Provider secrets，所有材料不得写入仓库或 `.qwq_output`。
- 每项 required 能力必须暴露可查询的成功率、错误率、P95/P99、throttle、retry 与 provider 可用性。
- optional 能力只能以结构化 unavailable/degraded 关闭并提供用户指引；禁止假成功或静默回退。
- 切换只允许在两个 ready Adapter 之间进行；必须验证数据与合同兼容、用户旅程连续和回滚可执行。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 能力专属 Port、Adapter 隔离与访问策略

- GIVEN 执行“能力专属 Port、Adapter 隔离与访问策略”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“能力专属 Port、Adapter 隔离与访问策略”对应动作。
- THEN 每项外部能力有唯一 canonical typed Port；Vendor SDK/type/endpoint/error/callback DTO 只存在于登记的 Adapter 路径。
- THEN Adapter 恰属 central_integration、domain_owned_adapter、client_platform_adapter、 data_pipeline_adapter 之一；豁免不绕过注册、合同、测试和商用门禁。
- THEN application/domain/UI 不直接读取第三方配置、环境变量或 Vendor DTO。

<a id="sit-002"></a>
### SIT-002 构建期 Binding、显式装配与逐能力 readiness

- GIVEN 执行“构建期 Binding、显式装配与逐能力 readiness”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“构建期 Binding、显式装配与逐能力 readiness”对应动作。
 - THEN 对象 `operations.yaml` 的 external dependency、服务本地环境 Binding、派生
   receipt/descriptor、SBOM 与 acceptance 双向一致；不得维护全局 registry、binding
   file 或 conformance manifest。
- THEN BindingCompiler 只在构建/门禁阶段运行；运行时不扫描 metadata 或按字符串动态选厂。
- THEN content embedding、user one-tap/social、integration location/SMS/Push、assistant model、 RTC room 与 runtime SLS 各自产出 root-scoped checked-in Go descriptor，并由对应 composition entrypoint fail-closed 消费。
- THEN runtime.message.transport 使用唯一 Redis Adapter Binding；其所有实际 producer/ consumer root 共享同一环境选择、各自产出 descriptor 并在 publisher/consumer 构造前 preflight Redis scene。任何 root 直接构造未校验 transport、静默跳过 consumer 或把 Pub/Sub 当作 durable delivery 均为阻断。
- THEN runtime NATS 与 DNS 显式声明生产消费为 none，仅为资产登记；不得列为 release-required、不得生成 release Binding 或冒充 readiness 证据。
- THEN Alpha/Beta/Gamma 缺受管非生产 Provider 材料、初始化、conformance 或健康探针时启动失败，且不得自动生成 Provider endpoint/secret。
- THEN Prod 缺真实厂商 Provider、外部注入凭据、初始化或健康探针时启动失败，并拒绝本地替代 endpoint。
- THEN optional 能力仅结构化 unavailable/degraded，绝不假成功。
- THEN readiness 只暴露 capability/adapter ID、状态、版本、digest 和 evidence URI，不暴露 endpoint、Secret 或 token。

<a id="sit-003"></a>
### SIT-003 Provider 公共/专项 Conformance 与 Alpha/Beta/Gamma 九格证据

- GIVEN 执行“Provider 公共/专项 Conformance 与 Alpha/Beta/Gamma 九格证据”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“Provider 公共/专项 Conformance 与 Alpha/Beta/Gamma 九格证据”对应动作。
- THEN 公共 suite 覆盖 success、validation、auth、network/DNS、timeout、throttle、retry、 idempotency、redaction 与 observability；能力专项 profile 覆盖本能力协议语义。
- THEN Alpha/Beta/Gamma 各自执行 local_contract、api_integration、user_acceptance；环境不是 第四测试目录层。
- THEN local_contract 对对应环境 Binding 选中的 Adapter 类运行离线协议/故障 harness，永不访问外网；api_integration 连接该环境声明的协议端点：Alpha/Beta/Gamma 连接隔离 sandbox/nonprod tenant，Prod Remote receipt 连接生产厂商租户。
- THEN runtime.message.transport 的 user_acceptance 只能以 production Remote composition 的 原生设备 chat @ assistant journey 取证，并受 stackctl 解析的 endpoint、CI 注入的 auth 和环境 seed 约束；未登记该 harness 时必须输出 PROVIDER.CONFORMANCE.REMOTE_CHAT_ASSISTANT_UAT_HARNESS_REQUIRED 并 GATE_BLOCK， 不得用 memory Redis、fixture consumer、UI mock 或 Provider override 生成 passed。
- THEN 每格报告含当前 commit/image/config/ContractGraph/Adapter digest、断言/skip、网络边界、 数据 digest、acceptance refs 与 logs/traces/metrics 引用。
- THEN NOT_RUN、required skip、零断言、dry-run、旧 digest、缺观测或缺清理回执均阻断。

<a id="sit-004"></a>
### SIT-004 Provider 故障、降级、替换与原子回滚

- GIVEN 执行“Provider 故障、降级、替换与原子回滚”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“Provider 故障、降级、替换与原子回滚”对应动作。
- THEN required Provider 不可用且无 ready 备选时阻断 rollout；optional 能力关闭时返回结构化 指引，禁止切 Mock 或本地合成成功。
- THEN 切换只发生在两个 ready 的 production-grade Adapter 之间，并验证合同/数据兼容、 用户 Journey 连续、指标口径一致和旧 callback 收口。
- THEN config+image 成对发布和回滚；last-good 可恢复且回滚后健康、数据与用户结果一致。

<a id="sit-005"></a>
### SIT-005 输出目录、Secret 与 evidence 隔离

- GIVEN 执行“输出目录、Secret 与 evidence 隔离”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“输出目录、Secret 与 evidence 隔离”对应动作。
- THEN Provider 配置、环境 Binding、schema、policy、endpoint/secret 值、渲染 `.env`、 证书和 TLS 状态均不进入 `.qwq_output`。
- THEN 输出根 `.qwq_output` 只含可删除重建的 runs/observability/process/cache 分类产物
- AND deploy payload、渲染配置、Caddy、TLS 与 env 文件写入 `QWQ_DEPLOY_WORK_ROOT/<target>/`
- AND process 不含 config/PKI，evidence 只含 ref/digest 和脱敏状态。
- THEN 删除 `.qwq_output` 后可仅凭版本控制真相源和显式外部依赖重建。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 能力专属 Port、Adapter 隔离与访问策略

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：每项外部能力有唯一 canonical typed Port；Vendor SDK/type/endpoint/error/callback DTO 只存在于登记的 Adapter 路径。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 构建期 Binding、显式装配与逐能力 readiness

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：对象 `operations.yaml` 的 external dependency、服务本地环境 Binding、派生
  receipt/descriptor、SBOM 与 acceptance 双向一致，且不存在全局 registry、binding
  file 或 conformance manifest。
- 完成判定：`SIT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 Provider 公共/专项 Conformance 与 Alpha/Beta/Gamma 九格证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：公共 suite 覆盖 success、validation、auth、network/DNS、timeout、throttle、retry、 idempotency、redaction 与 observability；能力专项 profile 覆盖本能力协议语义。
- 完成判定：`SIT-003` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-004"></a>
### OPEN-004 Provider 故障、降级、替换与原子回滚

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：required Provider 不可用且无 ready 备选时阻断 rollout；optional 能力关闭时返回结构化 指引，禁止切 Mock 或本地合成成功。
- 完成判定：`SIT-004` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-005"></a>
### OPEN-005 输出目录、Secret 与 evidence 隔离

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：Provider 配置、环境 Binding、schema、policy、endpoint/secret 值、渲染 `.env`、 证书和 TLS 状态均不进入 `.qwq_output`。
- 完成判定：`SIT-005` 对应行为满足且真实测试 `spec_ref` 有效
