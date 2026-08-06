# L3 Story：领域 Reader 与 Connector 授权装配 (`domain-reader-connector-grant`)

> 所属能力：[用户 Skill 产品与集成平台](../spec.md)
>
> Journey / Scenario：[`JNY-009 / SCN-017`](../../../spec.md#scn-017)、[`JNY-013 / SCN-030`](../../../spec.md#scn-030)
>
> 设计归属：[`L2 DEC-001`](../design.md#dec-001)

## 1. 用户价值

作为 Skill 用户，我希望小趣在获得明确授权后读懂站内 Gathering、协作计划、群聊、圈子、内容和公开网页，并能连接日历、提醒、地图或受控外链完成动作，从而不必手工复制信息，同时确保私人数据不会进入错误场景。

## 2. 范围与非目标

### In Scope

- DomainReaderDescriptor、两阶段 Context loading、ContextSegment provenance、Public Web evidence、Connector capability grant、ActionProposal 和 device continuation。

### Out of Scope

- World Model、数据库直读、凭证存储、任意 HTTP、预订支付、邮件/网盘发布和第三方代码。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 Reader 与 Connector 必须声明权威、可见性和能力边界

- Reader descriptor 必须声明 owner operation、schema、对象/可见范围、authority、sensitivity、freshness/cache、surface applicability 和 artifact/citation 规则。
- Context 第一阶段只加载入口、目标对象、共享 surface 与短 Skill 索引；确定 Skill 后只执行 ContextProfile 声明的 Reader/Resolver，大结果进入 Artifact Store。
- Skill 只引用 `calendar.event.create`、`map.route.open` 等 canonical capability，不引用厂商；Assistant 只能看到 connectionRef/capability state，凭证和 Provider 错误归一化由 Integration Service 拥有。
- ActionTool/DeviceAction 必须 proposal→confirmation→owner/native receipt→continuation；酒店餐饮交通只允许经验证的公开外链，不继承 Cookie/Authorization，不执行预订或支付。

## 4. 契约引用

- object / projection：`assistant.DomainReaderDescriptor`、`integration.ConnectorDefinition`、`integration.ConnectorAuthorization`、`integration.ConnectorConnection`、`integration.ConnectorInvocation`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 同一旅行请求只读取允许的 Gathering 上下文并安全完成设备动作

- GIVEN 用户在个人会话具有目标 Gathering 访问资格并授权 Content Reader 和系统日历，群聊 Placement 仅允许 shared Context。
- WHEN 用户个人请求创建行程提醒，随后在群聊请求相同动作并撤销日历连接。
- THEN 个人 Run 只加载声明的最小 Context，生成确认提案并凭 native receipt 续接；群 Run 不可见个人 connection，群内只显示中性进度。
- AND 撤权后下一个安全边界拒绝调用；日志、Artifact、Presentation 与消息不含 credential、token 或私人回执正文。

## 6. 依赖

- 前置要求：领域公开 Reader、Public Web Runtime、Integration Connector contracts、App native action bridge。
- 上游事实：ContextProfile/CapabilityProfile、surface、Consent 和 Connector grant。
- 下游结果：ContextSnapshot、ToolObservation、ActionProposal、native/external receipt reference。
- 父级设计：`DEC-001`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 Reader/Connector 覆盖与设备续接未闭环

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺新的 immutable package 激活与外部 Connector 完整装配；虽然站内 Reader 已进入统一运行时和官方 Skill source，本地安全实现仍不能证明用户请求可在真实环境持续完成。
- 已完成实现：Circle/Content/Entity Reader 已通过 generated operation metadata 绑定 owner public GET，以独立 observed client、投影 allowlist、来源 digest 和唯一对象目标 fail-closed。生产组合根已将其与 Conversation Resolver 装入同一 RuntimeRegistry。
- Assistant 日落：旧 Trip Reader、Resolver、配置、健康检查和 deploy upstream 已物理删除。
- Skill source：官方 `travel_companion` 不再声明 Trip Context requirement，改为只声明既有七个 `gathering.*` typed tools（含 `gathering.read_public`、`gathering.read_private` 与 `gathering.propose_plan`）。
- Gathering 阻断：Circle Gathering/GatheringPlan generated client 的 production delegated transport 尚未装配，当前 `NewCircleGatheringDomainOperationBinding` 未注入 transport，故真实环境调用仍会结构化 unavailable。
- Owner 边界阻断：Circle owner 尚未装配 delegated operation admission，且 Assistant grant 使用 generated canonical request/object target，现有通用 HTTP guard 使用 HTTP body/path target；两端契约统一前不得用 service credential 或手写 HTTP 绕过 persona authority。
- 其余缺口：还需从 current source 生成并激活新的 immutable Skill package，并完成 ConnectorAuthorization native/OAuth verifier、地图 typed intent 与旅行外链代理。Reader 必须继续只读 owner public query，Connector 必须继续在每个安全边界实时求权限交集。
- 尚缺验收证据：各 Reader 的真实服务 adapter API integration、真实 Provider adapter API integration、Alpha/Beta/Gamma binding/conformance、Android/iPhone device continuation、并发撤权竞态、SLI/SLO、告警与回滚收据。
- 完成判定：`GWT-001` 具有 Reader/Connector/Tool local_contract、真实 adapter api_integration 与 Android/iPhone user_acceptance 直接 `spec_ref`。
- 依赖：Integration Service Connector、各领域 Reader、Assistant Tool Fabric 与 Flutter native bridge。
