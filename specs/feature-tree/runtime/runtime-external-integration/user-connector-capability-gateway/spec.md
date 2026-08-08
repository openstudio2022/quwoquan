# L3 Story：用户 Connector 能力网关 (`user-connector-capability-gateway`)

> 所属能力：[运行时外部集成](../spec.md)
>
> Journey / Scenario：[`JNY-013 / SCN-030`](../../../spec.md#scn-030)、[`SCN-031`](../../../spec.md#scn-031)
>
> 设计归属：[`L2 DEC-001`](../design.md#dec-001)

## 1. 用户价值

作为小趣用户，我希望在清楚授权后连接系统日历/提醒、地图和受控旅行外链，并能随时查看、撤权和重连，从而让助手真正执行下一步，同时保证凭证不会暴露给 Skill、群聊或 App 业务页面。

## 2. 范围与非目标

### In Scope

- `integration.connector_definition`、`integration.connector_authorization`、`integration.connector_connection`、`integration.capability_grant` 与 `integration.connector_invocation` 五个对象的单轨协作，以及 OAuth/native grant 状态、受保护 credentialRef、capability readiness、调用/撤权/刷新/重试/幂等与审计。
- `integration.capability_grant` 只解析 `public_provider`、`user_connector`、`device_capability`、`domain_operation` 四类 typed binding；调用方显式提交有序 `bindingPriority`，解析结果 exactly-one、固定五分钟过期且读取不续期。
- final input 冻结后的 capability 授权、input digest/confirmation/permit/idempotency 绑定，以及真正调用 Provider、设备桥或 owner operation 前的 authority revalidation。
- 首期 capability：系统日历/提醒、地图导航、酒店/餐饮/交通受控公开外链。

### Out of Scope

- 预订支付、任意浏览器写操作、邮件/网盘/文档发布、第三方 Skill、凭证进入 Assistant/App 或共享消息。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 五对象分别拥有目录、授权、连接、短期解析与调用事实

- `integration.connector_definition` 声明厂商无关 capability、授权方式、数据分类、确认/幂等/超时/恢复与环境可用性；Skill 只引用 capability。
- `integration.connector_authorization` 拥有一次性 grant proof 与 Provider subject，`integration.connector_connection` 拥有 account 连接、授权状态与 protected credentialRef；Assistant 只能读取 connectionRef、capability/state/freshness，不得获取 secret/token。
- `integration.capability_grant` 是四类 binding 的易失 `runtime_session`，只保存脱敏 exactly-one 解析结果，不拥有 Provider、设备、operation 或 credential 的长期事实。
- `integration.connector_invocation` 拥有调用主体、final input digest、幂等键、确认/continuation、执行状态和脱敏 receipt；撤权、过期、binding 漂移或 input 不一致均 fail-closed。

<a id="req-002"></a>
### REQ-002 首期旅行动作必须限制为受控只读或用户确认

- 地图只接收 canonical PlaceRef/RouteRef 的 `OpenRouteIntent`，App 决定可用地图；不接收任意 scheme/provider 参数。
- 酒店、餐饮、交通 URL 必须经过公开 HTTPS 与来源策略校验，不携带 Cookie/Authorization，不提交表单、不预订、不支付。
- 日历/提醒必须 ActionProposal→用户确认→native/external receipt→Assistant continuation；群内不显示个人详情。

<a id="req-003"></a>
### REQ-003 四类 binding 必须按显式优先级解析为固定五分钟的 exactly-one 结果

- `bindingPriority` 是调用上下文提交的完整有序序列，不存在全局隐藏顺序；resolver 只能选择第一个满足 capability、region、状态、probe、scope、permission 与 owner contract digest 的候选。
- 四类 binding 的事实来源分别为：`public_provider` 只引用环境 adapter/config/contract digest 与 probe，`user_connector` 只来自当前 account 已验证且未撤销的 Connection，`device_capability` 只来自当前 installation 的 bridge attestation/permission，`domain_operation` 只引用 owner operationId 与 contract digest。
- 高优先候选一旦 unavailable、denied、revoked 或配置无效必须结构化失败，不得静默回退到次优 binding；四类 payload 必须 exactly-one，禁止 universal Connector map。
- `ResolvedCapabilityGrant` 自 `resolvedAt` 起固定 300 秒失效，读取不得刷新 TTL；过期只能重新解析全部 authority 与 capability signals，禁止沿用旧 session 或只续时间。

<a id="req-004"></a>
### REQ-004 final input 授权必须绑定解析结果并在执行边界重验

- capability resolution 必须发生在 final input 已冻结之后，绑定 account、capability、selected binding、input digest、confirmation、permit 与 idempotency；解析后任何输入或 binding identity 变化都必须重新解析。
- `integration.connector_invocation`、设备 bridge 与 owner operation 只接受同一 `resolutionId` 和 input digest 的 typed authorization，不得从 ConnectorConnection、Tool metadata 或请求 body 重新推导第二份授权。
- 真正产生外部副作用前必须复核 Connection revoke/expiry、设备 permission/attestation、permit consumption、Provider probe 与 owner contract digest；五分钟未过不代表这些事实可以跳过重验。
- 执行 receipt 必须绑定 resolution、Invocation、最终输入和实际 Provider/device/owner 结果；失败、取消与 continuation 不得伪造成功或泄露 credential、proof、permit 与原始输入。

## 4. 契约引用

- object：`integration.connector_definition`、`integration.connector_authorization`、`integration.connector_connection`、`integration.capability_grant`、`integration.connector_invocation`
- capability binding：`CapabilityBindingKind.public_provider`、`CapabilityBindingKind.user_connector`、`CapabilityBindingKind.device_capability`、`CapabilityBindingKind.domain_operation`
- surface / route：`runtime.OpenRouteIntent`、`assistant.ActionProposal`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 连接撤销立即阻止旅行日历动作且不泄露凭证

- GIVEN 用户连接系统日历并授权 `calendar.event.create`，AssistantRun 已生成待确认提案，final input 已绑定一个尚未过期的 `ResolvedCapabilityGrant`。
- WHEN 用户在确认前撤销 Connector，再尝试继续同一动作。
- THEN 执行边界重新验证 Connection 后 fail-closed，不得因五分钟 TTL 尚有效而继续；Invocation 返回重新连接恢复动作，日历无事件，Run 只记录脱敏失败并可续接。
- AND credential/token 不出现在 Assistant context、App DTO、群消息、日志、trace、metric label 或 evidence 正文。

<a id="gwt-002"></a>
### GWT-002 地图与旅行外链只执行受控意图

- GIVEN Skill 返回 canonical Place/Route 引用及公开酒店/餐饮/交通来源。
- WHEN 用户确认打开路线或外链。
- THEN App 只按 typed intent 选择已安装地图，外链经公共 HTTPS policy 代理/验证；私网、危险协议、重定向逃逸、认证继承或写操作均被拒绝。

<a id="gwt-003"></a>
### GWT-003 四类 binding 的优先级、过期与 final-input 绑定保持单轨

- GIVEN 同一 capability 存在多个不同 kind 的候选，调用方提交显式 `bindingPriority`，且 final input、confirmation、permit 与 idempotency 已冻结。
- WHEN resolver 解析、缓存并在 Invocation/设备/owner 执行边界消费结果。
- THEN 只返回优先序列中第一个合法候选的 exactly-one typed binding，固定 300 秒且读取不续期；优先候选失败时结构化拒绝而不静默 fallback。
- AND 输入 digest、selected binding、revoke/permission/permit/probe/contract digest 任一漂移，或 session 过期，均要求重新解析并拒绝旧授权；receipt 只确认实际执行的同一 final input 与结果。

## 6. 依赖

- 前置要求：integration-service protected credential store、Provider adapters、Public Web policy 与 App native continuation。
- 上游事实：account、Consent、ConnectorAuthorization、ConnectorConnection、ActionProposal、device attestation 和 canonical owner operation。
- 下游结果：短期 ResolvedCapabilityGrant、Invocation receipt、native continuation 与 audit activity。
- 父级设计：`DEC-001`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 用户 Connector 平台尚未完成端到端准出

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺 production delegation、Invocation worker 与真实 receipt 链的单轨闭合；五对象 contract 已声明边界，但本地 resolver、Mongo store 或 typed UI 存在均不得误报为用户可用或 commercial-ready。
- 尚缺 production delegation：ConnectorConnection 的旧 internal capability 解析必须原子委托 `CapabilityGrantSessionFacade`，Assistant/Tool Fabric 只能传递同一 final-input typed authorization；旧 resolver、body accountId 赋权或并行求交路径必须为零。
- 尚缺 production worker：ConnectorInvocation 必须消费同一 `ResolvedCapabilityGrant`，在外部副作用前完成 revoke/permission/permit/probe/contract-digest revalidation，并由正式 Provider、device bridge 或 owner-operation executor 执行；credential refresh、continuation、取消与受控重试必须由唯一 composition 装配。
- 尚缺真实 receipt：仍需 Alpha/Beta/Gamma binding/conformance、真实 Provider/native execution receipt、并发撤权与过期竞态、Android/iPhone continuation、SLI/SLO、告警、回滚与同候选 digest 绑定；失败、跳过或本地替代均不计通过。
- 完成判定：`GWT-001`、`GWT-002`、`GWT-003` 具有 Integration/Assistant/App local_contract、真实 adapter api_integration 与 Android/iPhone user_acceptance 直接 `spec_ref`；四环境 delegation/binding/conformance、执行 receipt、撤权、审计和回滚收据绑定同一候选。
- 依赖：Integration contracts/persistence/provider adapter、Assistant Tool Fabric 和 App native bridge。

<a id="open-002"></a>
### OPEN-002 ConnectorInvocation 长流程缺取消与失败恢复入口

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺取消与失败恢复入口使 `integration.ConnectorInvocation` 无法履行长流程编排器（`process_manager`）语义。它当前只有发起（`InvokeConnectorCapability`）、确认续跑（`ContinueConnectorInvocation`）与状态读取（`GetConnectorInvocation`、`ListConnectorInvocations`）四个 operation，用户无法终止一次已发起的 Provider 调用，运营也无法在 Provider 瞬时故障后受控重放。
- 尚缺实现：`object.yaml#lifecycle.states` 与 `domain/model.StatusCancelled` 均声明了 `cancelled` 终态，但全服务没有任何写入路径，该状态在契约面不可达。`StatusFailed` 由 worker 单向写入后即终态，`ContinueConnectorInvocation` 只接受 `awaiting_confirmation`，不覆盖失败重放。缺 `CancelConnectorInvocation` 与失败重放入口，以及对已提交 Provider 副作用的补偿约定。
- 尚缺验收证据：缺「执行中取消到达 `cancelled` 并释放 lease、清理 protected payloadRef」与「Provider 瞬时故障后受控重放且不重复产生外部副作用」两条路径的 local_contract 与真实 adapter api_integration。
- 完成判定：`cancelled` 由至少一个声明入口可达，`failed` 具备声明的恢复入口或显式不可恢复裁定，两条路径各有 `spec_ref` 直接绑定的 local_contract 与 api_integration 收据。
- 依赖：正式 Provider adapter（本节点 `OPEN-001`），补偿语义取决于 Provider 是否提供可撤销的调用面。
