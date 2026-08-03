# L2 Design：运行时外部集成 (`runtime-external-integration`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“以能力专属 typed Port、Provider Adapter、构建期 BindingCompiler、统一 Conformance Suite、3×3 证据和双层 readiness 隔离第三方差异；integration-service 只是 runtime 治理的一种部署形态”需要 `capability-provider-commercial-readiness-gate`、`integration-service-foundation`、`provider-adapter-conformance-suite`、`user-connector-capability-gateway` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：以能力专属 typed Port、Provider Adapter、构建期 BindingCompiler、统一 Conformance Suite、3×3 证据和双层 readiness 隔离第三方差异；integration-service 只是 runtime 治理的一种部署形态。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`capability-provider-commercial-readiness-gate`](./capability-provider-commercial-readiness-gate/spec.md)：替代 Adapter 通过、旧 digest、不同 commit/image/config 或缺目标厂商证据均不能提升目标 adapter_ready。
- [`integration-service-foundation`](./integration-service-foundation/spec.md)：对外只暴露标准化接口，禁止端侧直接调用供应商 API。
- [`provider-adapter-conformance-suite`](./provider-adapter-conformance-suite/spec.md)：success、validation、auth、network/DNS、timeout、throttle、retry、idempotency、callback ordering、redaction、observability 均被同一 Adapter 执行。
- [`user-connector-capability-gateway`](./user-connector-capability-gateway/spec.md)：把官方 Connector 定义、账号连接、受保护凭证、能力授权和 invocation receipt 留在 Integration Service，Assistant 只消费厂商无关 capability。

## 3. 端云与数据流

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 外部能力以 typed Port 和显式 Adapter 在 composition root 装配
- 决策：外部能力以 typed Port 和显式 Adapter 在 composition root 装配。
- 理由：以能力专属 typed Port、Provider Adapter、构建期 BindingCompiler、统一 Conformance Suite、3×3 证据和双层 readiness 隔离第三方差异；integration-service 只是 runtime 治理的一种部署形态。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`capability-provider-commercial-readiness-gate`](./capability-provider-commercial-readiness-gate/spec.md)、[`integration-service-foundation`](./integration-service-foundation/spec.md)、[`provider-adapter-conformance-suite`](./provider-adapter-conformance-suite/spec.md)、[`user-connector-capability-gateway`](./user-connector-capability-gateway/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 共享 capability 的消费者与 Binding 从对象路径派生
- 决策：capability owner 仅在其对象 `operations.yaml.externalDependencies` 声明 canonical
  Port、操作和 conformance profile；其他对象以本地 capability-use 声明同一 Port 的实际
  消费语义。BindingCompiler 从这些对象路径和各服务的
  `environments/<env>/config.yaml.externalBindings` 派生 root-scoped descriptor。
- 理由：Redis Streams/PubSub 等平台能力有多个真实 producer/consumer。把 consumer
  root、endpoint、secret 或 adapter 复制到全局 registry、manifest 或 path 清单会重新
  建立第二真相源，也会允许调用方绕开 Binding 和启动预检。
- 约束：consumer 不得声明 endpoint、secret、adapter 或外置 root list；每个 generated
  descriptor 都绑定具体对象与环境，composition root 必须消费 descriptor 并 fail-closed。
  `runtime.message.transport` 的 durable fact 使用 Streams，Pub/Sub 只用于显式 ephemeral
  hint；任何本地硬编码 enabled/adapter/timeout 选择均不属于可发布 Binding。
- 被否决方案：按 service 命令入口维护消费者清单；由 runtime helper 默认选择 Redis
  adapter；以 Pub/Sub 替代 durable Stream；用 fixture 或 memory transport 补写
  **Prod** evidence。

<a id="dec-003"></a>
### DEC-003 Alpha/Beta/Gamma 受管非生产 Provider 与 Prod hosted receipt
- 决策：Alpha、Beta、Gamma 的 required 验收由环境 Binding 显式选择受管 `protocol_fixture/local_*` Port 对等 Adapter；Assistant/Content 通过 integration-service 独立内部 listener 走真实 HTTP/wire decoder，SMS/Push/Location/User 在服务端 typed Port 边界替代，RTC 运行真实本地 LiveKit。App 不含 Mock 或 Provider 选择器。Gamma 仍运行完整第一方 Remote composition、黑盒 API 与真机 Journey。Prod 只选择真实厂商 Adapter 和生产租户，非生产内部 listener 不启动。
- 理由：Alpha/Beta/Gamma 需要无生产凭据、可重复、可故障注入的端云功能闭环；显式替代 Adapter 仍执行正式 Port、命令、事件、HTTP 与观测链，而 Prod hosted receipt 另行证明真实 SDK、鉴权、限流、回调、推送与 RTC 媒体链。
- 被否决方案：以 nonprod evidence 提升 Prod readiness、在 Gamma 注入生产租户凭据、缺 Provider 时运行时 fallback、App/UI Mock，以及不经 Binding 的临时环境变量 override。
- 约束与影响：governance 要求 Alpha/Beta/Gamma 选择 fixture/local_* Port 对等 Adapter；Prod 禁止 mock、fixture、recorder 与本地替代 Adapter。
- 约束与影响：Alpha/Beta/Gamma 的替代 endpoint 只由 stackctl 从 local topology 投影，LiveKit key/secret 仅存放在 target-scoped deploy secret root；Prod 验证外部注入的生产 Provider 材料并拒绝替代 Adapter。
- 约束与影响：九格证据绑定当前环境 config、candidate image、ContractGraph、Adapter digest 与真实 CaseResult；Gamma nonprod receipt 不能替代 Prod hosted receipt。Object Storage 与四环境 Elasticsearch Log sink 都必须登记 capability 并走 Binding。
- 关联要求：`REQ-006`
- 关联验收：`SIT-002`、`SIT-003`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 本能力把第三方依赖治理为编译期可验证、启动时 fail-closed、运行时可观测、发布时可回滚的受控能力。
- NOT_RUN、required skip、零断言、dry-run、缺观测或旧 digest 都阻断。
- 配置、binding、schema、policy、构建规则在受版本控制目录。
- 本地渲染配置、临时 `.env`、Secret 与证书位于仓外。
