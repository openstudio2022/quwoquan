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

- `ConnectorDefinition`、`ConnectorAuthorization`、`ConnectorConnection`、`ConnectorInvocation`、OAuth/native grant 状态、受保护 credentialRef、capability readiness、调用/撤权/刷新/重试/幂等与审计。
- 首期 capability：系统日历/提醒、地图导航、酒店/餐饮/交通受控公开外链。

### Out of Scope

- 预订支付、任意浏览器写操作、邮件/网盘/文档发布、第三方 Skill、凭证进入 Assistant/App 或共享消息。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 Connector 状态、凭证与调用回执由 Integration Service 唯一拥有

- Definition 必须声明厂商无关 capability、授权方式、数据分类、确认/幂等/超时/恢复与环境可用性；Skill 只引用 capability。
- Connection 必须属于 account，凭证只存 protected store 并以 credentialRef 关联；Assistant 只读取 connectionRef、capability/state/freshness，不得获取 secret/token。
- Invocation 必须绑定 connection、capability、调用主体、幂等键、确认/continuation 和脱敏结果；撤权或过期后 fail-closed。

<a id="req-002"></a>
### REQ-002 首期旅行动作必须限制为受控只读或用户确认

- 地图只接收 canonical PlaceRef/RouteRef 的 `OpenRouteIntent`，App 决定可用地图；不接收任意 scheme/provider 参数。
- 酒店、餐饮、交通 URL 必须经过公开 HTTPS 与来源策略校验，不携带 Cookie/Authorization，不提交表单、不预订、不支付。
- 日历/提醒必须 ActionProposal→用户确认→native/external receipt→Assistant continuation；群内不显示个人详情。

## 4. 契约引用

- object / projection：`integration.ConnectorDefinition`、`integration.ConnectorConnection`、`integration.ConnectorInvocation`
- surface / route：`runtime.OpenRouteIntent`、`assistant.ActionProposal`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 连接撤销立即阻止旅行日历动作且不泄露凭证

- GIVEN 用户连接系统日历并授权 `calendar.event.create`，AssistantRun 已生成待确认提案。
- WHEN 用户在确认前撤销 Connector，再尝试继续动作。
- THEN invocation fail-closed 并返回重新连接恢复动作，日历无事件；Run 在安全边界记录脱敏失败并可续接。
- AND credential/token 不出现在 Assistant context、App DTO、群消息、日志、trace、metric label 或 evidence 正文。

<a id="gwt-002"></a>
### GWT-002 地图与旅行外链只执行受控意图

- GIVEN Skill 返回 canonical Place/Route 引用及公开酒店/餐饮/交通来源。
- WHEN 用户确认打开路线或外链。
- THEN App 只按 typed intent 选择已安装地图，外链经公共 HTTPS policy 代理/验证；私网、危险协议、重定向逃逸、认证继承或写操作均被拒绝。

## 6. 依赖

- 前置要求：integration-service protected credential store、Provider adapters、Public Web policy 与 App native continuation。
- 上游事实：account、Consent、connection grant、ActionProposal 和 canonical object reference。
- 下游结果：capability state、Invocation receipt、native continuation 与 audit activity。
- 父级设计：`DEC-001`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 用户 Connector 平台尚未完成端到端准出

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前尚缺正式 Provider/native adapter 与双端 continuation，不能把本地对象、worker、capability 求交或 App typed UI 测试误报为用户可用。ConnectorDefinition、ConnectorAuthorization、ConnectorConnection、ConnectorInvocation 四对象的 canonical contract 已声明权限边界、一次性 grant receipt、凭证隔离、幂等与审计。Authorization/Connection/Invocation 已有 HTTP composition、Mongo authoritative store、transactional outbox 和真实 Mongo API integration。Connection 消费一次性 grant，撤权同步终止 authorization/credential lifecycle。Invocation worker 具备 lease/CAS claim、执行前授权复核、脱敏终态与 protected payloadRef 事务清理。Assistant 已在每次 PreToolUse 通过 service-auth internal query 求交 Tool metadata、SkillConsent、SkillUserSetting、surface 与当前 Connector grant，失败按 canonical error fail closed。
- 尚缺实现：ConnectorAuthorization 当前 native attestation/OAuth callback verifier 默认明确不可用，仍缺真实 Provider adapter、credential refresh worker 和真实 adapter API integration；Invocation capability executor 仍缺正式 Provider adapter与进程装配。App 仍缺连接创建/重连的 native continuation、地图 typed intent 与旅行外链 policy。Integration internal capability operation 保持 commercial blocked，不能据本地 runtime wiring 提升状态。
- 尚缺验收证据：四对象的本地/真实 Mongo transaction tests 与 Assistant capability gateway local_contract 已存在；仍缺 Alpha/Beta/Gamma binding/conformance、真实 Provider/native receipt、并发撤权竞态、Android/iPhone continuation、SLI/SLO、告警和回滚收据。
- 完成判定：`GWT-001`、`GWT-002` 具有 Integration/Assistant/App local_contract、真实 adapter api_integration 与 Android/iPhone user_acceptance 直接 `spec_ref`；四环境 binding/conformance、撤权、审计和回滚收据成立。
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
