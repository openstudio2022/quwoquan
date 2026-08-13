# L3 Story：Skill 用户设置、授权与主动订阅 (`skill-user-lifecycle`)

> 所属能力：[用户 Skill 产品与集成平台](../spec.md)
>
> Journey / Scenario：[`JNY-009 / SCN-034`](../../../spec.md#scn-034)
>
> 设计归属：[`L2 DEC-001`](../design.md#dec-001)

## 1. 用户价值

作为小趣用户，我希望在使用前看懂 Skill 的价值、示例、数据/记忆/写操作和连接需求，并分别控制是否使用、授权什么、是否主动提醒，从而获得持续服务而不失去控制。

## 2. 范围与非目标

### In Scope

- Skill detail/setup/activity、SkillUserSetting、SkillConsent、SkillSubscription、connector refs、权限撤销和数据控制入口。

### Out of Scope

- 群/圈管理员策略、Connector 凭证、第三方 Skill 和付费订阅。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 启用、授权、主动规则与连接必须独立表达

- 官方响应式 Skill 默认可用，个人 `SkillUserSetting.status` 可停用并保存 schema-bound configuration；配置 schema digest 变化时必须显式迁移或重新设置。
- Skill Center 创建首个显式 Setting 时，必须使用同一 active Catalog 目录项返回的 `configurationSchemaDigest` 与 setup 元数据；不存在显式 Setting 表示采用 package 默认状态，不得伪造空对象已持久化。
- Skill Center 必须一次有界读取账号已显式保存的 Setting 并与 Catalog 按 `skillId` 合并；禁止为目录每项发起独立请求或将未返回项物化成伪 Setting。
- `ListSkills` 只返回轻量目录与 schema digest；用户进入某个 Skill 详情后才调用 `GetSkillCatalogItem`，读取同一 active package digest 的安全 JSON Schema 并生成受控 setup 表单。App 不得按 `skillId` 硬编码字段，未知或不安全 schema 必须 fail-closed，服务端仍执行最终校验。
- Skill 详情中的分组、目标用户、适用场景、授权用途和成果示例必须来自同一 active package 的已解析安全语义；App 不得把 domain/category、surface 或 scope 映射为垂类专用文案，也不得展示内部 asset reference。
- SkillConsent 只表达数据/能力授权；SkillSubscription 只表达 Trigger、频控、静默、去重和投递，不能充当启用开关。
- SkillConsent 每个 Skill 必须以单一 active 聚合保存用户当次明确确认的完整 `grantedScopes[]`；Run 只有在所有 required scope 均命中时才可读取。package 新增 scope 时必须要求用户撤销旧授权并重新确认，不得静默扩权。
- 对声明为 proactive/hybrid 且尚无 Subscription 的 Skill，用户开启主动提醒时必须先设置关注内容和本地触发时刻，再通过 `CreateSkillSubscription` 创建独立聚合；cron 必须绑定显式 IANA timezone 并由服务端按该时区计算 UTC `nextAttemptAt`，App 不得向用户暴露 cron 或把本地时刻当 UTC。
- Skill Center 必须显示最近 Run、后台任务、失败、授权/撤权和连接活动，以及权限撤销、连接断开和数据控制入口。Assistant-owned 活动以 `SkillActivityView` 脱敏联邦读取；Connector 活动继续读取 Integration owner，不得复制凭证、调用正文或外部响应。
- Skill 数据控制必须先建立待确认 `SkillDataControlRequest`，再由用户显式确认；首期 action 只允许 `hide_activity_history`、`revoke_consent`、`archive_subscriptions`。隐藏仅推进活动可见性 watermark，完成回执不得冒充 Connector、Run 法定审计或其他领域数据已删除。
- 失败或中断的数据控制活动必须返回 owner-scoped typed `dataControlRequestId`；App 先读取最新 revision，再对同一请求执行确认恢复并保留 `completedActions`，不得从 `sourceObjectRef` 拆 ID、另建请求或重做已完成 action。
- 确认后的请求进入 durable execution；Worker 必须以 lease、heartbeat、fencing token 与 CAS 认领，并在进程中断或 lease 过期后只继续 `completedActions` 之外的 action。所有 owner command 使用 `requestId+action` 派生的稳定幂等键。
- 同一 Skill 可以同时拥有多个不同触发条件或目的地的 Subscription；Skill Center 必须以稳定 `subscriptionId` 列表展示与操作，不得按 `skillId` 覆盖或折叠。
- 已声明的 Setting/Consent typed operation 必须允许候选环境执行以产生 Remote/UAT 证据；operation `ready` 只表达运行可达性，最终发布仍必须由本 Story 的环境、真机、SLI/SLO 与回滚 OPEN 准出，禁止形成“缺证据所以禁止调用、又因禁止调用无法取得证据”的循环门。

<a id="req-002"></a>
### REQ-002 Skill Center 必须以 production Remote 完成多对象生命周期与失败恢复

- `assistant.skill_center` 必须从同一 active package 读取 Catalog，并分别通过各 owner 的 production Remote 读取和修改 Setting、Consent、Subscription、Activity、DataControl 与 Connector 状态；任一局部失败不得把其他对象状态改写为默认值，也不得把单个 toggle 当成整个 Skill 生命周期。
- Setting、Consent、Subscription 与 DataControl mutation 只有在 typed receipt 或对象结果返回并经 owner 重新读取收敛后才显示成功；授权不足、Consent 撤销、Connector 断开或不可用必须阻止相关能力并保留用户可恢复的设置或请求，不得保存 Connector credential、伪造连接成功或绕过 Integration owner。

## 4. 契约引用

- object / projection：`assistant.SkillUserSetting`、`assistant.SkillConsent`、`assistant.SkillSubscription`、`assistant.SkillActivityView`、`assistant.SkillDataControlRequest`
- page：`assistant.skill_center`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 用户停用响应式 Skill 不等同于退订或撤权

- GIVEN 用户已授权旅行数据并创建天气变化主动 Subscription，travel_companion 当前 enabled。
- WHEN 用户分别执行停用 Skill、暂停 Subscription、撤销 Consent。
- THEN 三个动作只修改各自对象并产生不同用户可见结果；任何动作不得隐式改写另两个对象。
- AND 撤权在下一个 Run 安全边界立即阻止相关 Reader/Tool，活动页记录原因且不泄露数据正文。

<a id="gwt-002"></a>
### GWT-002 首次开启主动提醒会创建时区正确的独立订阅

- GIVEN proactive/hybrid Skill 已启用但当前没有未归档 Subscription。
- WHEN 用户填写关注内容、选择每天本地触发时刻并确认开启。
- THEN Skill Center 通过 generated `CreateSkillSubscription` 创建 active Subscription，不改写 Setting 或 Consent。
- AND trigger 保存显式 IANA timezone，调度器按该时区匹配 cron 并将 `nextAttemptAt` 记录为 UTC；UI 不显示原始 cron。

<a id="gwt-003"></a>
### GWT-003 活动与数据控制保持 owner、确认和多订阅边界

- GIVEN 同一 Skill 有两个不同 subscriptionId 的主动规则，并已有 Run、Consent 与 Subscription 活动。
- WHEN 用户查看该 Skill 活动并创建数据控制请求，随后明确确认隐藏活动、撤权和归档订阅。
- THEN 活动 Slice 不泄露正文或 Connector secret。
- AND 两个 Subscription 分别展示，并全部通过各自 owner command 归档。
- AND 数据控制请求以稳定幂等回执完成。
- AND 失败后刷新仍以 typed request ID 读取最新 revision，并在同一请求上恢复未完成 action。
- AND 未确认时无任何副作用，完成结果不声称 Connector、Run 法定审计或其他领域数据已删除。

<a id="gwt-004"></a>
### GWT-004 Skill Center 以 production Remote 完成分轨控制与 Connector 恢复

- GIVEN 已认证用户打开 `assistant.skill_center`，同一 active package 的 Catalog 与该用户现有 Setting、Consent、Subscription、Activity、DataControl 和 Connector owner 状态可读取。
- WHEN 用户查看 Skill 详情、保存 Setting、授权或撤销 Consent、创建或暂停 Subscription、创建并确认或恢复 DataControl 请求，并在 Connector 断开后执行受控重连与刷新。
- THEN 每个动作只经对应对象 owner 的 generated production Remote operation 生效，页面重新读取后分别展示收敛状态，任何对象不得冒充另一个对象的启用、授权、主动投递或数据控制事实。
- AND 授权不足、Consent 撤销、Connector 断开或 Provider 不可用时，相关 Reader/Tool 保持 fail-closed，页面保留最后一次已确认状态与待处理意图，并提供登录、授权、重连或重试入口，不泄露 credential、调用正文或外部响应。
- AND DataControl 未知结果只使用原 typed request ID 重新读取和续接，Setting、Consent、Subscription 与 Connector mutation 也不得通过本地成功、重复创建或跨 owner fallback 消除失败。

## 6. 依赖

- 前置要求：active package profiles、generated Facade 和 account authority。
- 上游事实：用户设置/授权/订阅动作与 connector reference。
- 下游结果：Run routing/policy intersection、Trigger scheduler 与 Skill Center activity。
- 父级设计：`DEC-001`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 Skill Center 分轨生命周期尚缺完整产品与环境准出

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺 `assistant.skill_center` 同一候选上的完整 Catalog、Setting、Consent、Subscription、Activity、DataControl 和 Connector 恢复旅程，用户目前无法在一个入口以 production Remote 完成并验证这些分轨控制。
- 尚缺实现：仍缺 `event/context_change/follow_up` Trigger setup、Connector native 建连/重连、SkillActivity/DataControl generated App 接线，以及相关 SLI/SLO 和回滚装配。
- 验收数据供给现状：
  - `assistant.skill_center` 的 Catalog/Subscription 分轨已由 `assistant-skill-subscription` typed capability 供数（依赖环境 skill package，目录为空时 fail-closed）。
  - SkillActivity 子面依赖 assistant run 历史累积（`assistant-prompt` capability 可部分供给）。
  - Connector 子面依赖用户主动三方授权流程，测试数据控制面不伪造授权，首访空态为合法验收态。
- 尚缺验收证据：仍缺同一候选的受管 Remote、撤权后 Run 安全边界、主动规则物理真机、数据控制恢复、双端物理真机和回滚收据。
- 完成判定：`GWT-001/GWT-002/GWT-003/GWT-004` 具有 Catalog/Setting/Consent/Subscription/Activity/DataControl/Connector 的对象 local_contract、真实 api_integration 与 Flutter user_acceptance 直接 `spec_ref`，并完成事件/上下文主动规则、Connector 和数据控制 generated App 管理。
- 环境证据：绑定同一 commit、ContractGraph、candidate、production Remote composition 和环境 Provider 的 Android 实机与 iPhone 实机 `ReadinessResultBundle` 均为 passed，并取得受管环境 activate/readback/rollback 回执。
- 阻断规则：缺任一结果、存在动态 skip 或结果不属于同一候选时继续阻断。
- 依赖：Assistant contracts/codegen、Skill Center 重构、Integration Connector native continuation、trigger/runtime policy、受管环境与 Android/iPhone 物理设备。
