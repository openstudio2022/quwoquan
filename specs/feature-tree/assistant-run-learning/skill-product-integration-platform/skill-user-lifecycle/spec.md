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

- Skill detail/setup/activity、SkillUserSetting、SkillConsent、SkillSubscription、connector refs、权限撤销和数据删除入口。

### Out of Scope

- 群/圈管理员策略、Connector 凭证、第三方 Skill 和付费订阅。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 启用、授权、主动规则与连接必须独立表达

- 官方响应式 Skill 默认可用，个人 `SkillUserSetting.status` 可停用并保存 schema-bound configuration；配置 schema digest 变化时必须显式迁移或重新设置。
- Skill Center 创建首个显式 Setting 时，必须使用同一 active Catalog 目录项返回的 `configurationSchemaDigest` 与 setup 元数据；不存在显式 Setting 表示采用 package 默认状态，不得伪造空对象已持久化。
- Skill Center 必须一次有界读取账号已显式保存的 Setting 并与 Catalog 按 `skillId` 合并；禁止为目录每项发起独立请求或将未返回项物化成伪 Setting。
- `ListSkills` 只返回轻量目录与 schema digest；用户进入某个 Skill 详情后才调用 `GetSkillCatalogItem`，读取同一 active package digest 的安全 JSON Schema 并生成受控 setup 表单。App 不得按 `skillId` 硬编码字段，未知或不安全 schema 必须 fail-closed，服务端仍执行最终校验。
- SkillConsent 只表达数据/能力授权；SkillSubscription 只表达 Trigger、频控、静默、去重和投递，不能充当启用开关。
- SkillConsent 每个 Skill 必须以单一 active 聚合保存用户当次明确确认的完整 `grantedScopes[]`；Run 只有在所有 required scope 均命中时才可读取。package 新增 scope 时必须要求用户撤销旧授权并重新确认，不得静默扩权。
- 对声明为 proactive/hybrid 且尚无 Subscription 的 Skill，用户开启主动提醒时必须先设置关注内容和本地触发时刻，再通过 `CreateSkillSubscription` 创建独立聚合；cron 必须绑定显式 IANA timezone 并由服务端按该时区计算 UTC `nextAttemptAt`，App 不得向用户暴露 cron 或把本地时刻当 UTC。
- Skill Center 必须显示最近 Run、后台任务、失败、授权/撤权和连接活动，以及权限撤销、连接断开和数据删除入口。
- 已声明的 Setting/Consent typed operation 必须允许候选环境执行以产生 Remote/UAT 证据；operation `ready` 只表达运行可达性，最终发布仍必须由本 Story 的环境、真机、SLI/SLO 与回滚 OPEN 准出，禁止形成“缺证据所以禁止调用、又因禁止调用无法取得证据”的循环门。

## 4. 契约引用

- object / projection：`assistant.SkillUserSetting`、`assistant.SkillConsent`、`assistant.SkillSubscription`

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
- 影响或价值：当前 Skill Center 已在本地实现 Catalog + Setting + Subscription + Consent 一次并行读取、按需 Skill detail、active package schema 驱动的通用 setup 表单、首次 daily schedule 主动规则创建及 fail-closed 降级。响应式开关只写 Setting、主动提醒只写 Subscription、完整 scope 授权只写 Consent。Connector 分区已接入脱敏目录、连接状态、最近活动和撤权确认。权限与记忆入口复用现有云端 Consent/Preference 管理页执行撤权与忘记。尚缺事件/上下文变化类主动规则、Connector native 建连/重连、完整授权/Run 活动历史和数据删除旅程，以及受管 Remote、SLI/SLO、回滚和 Android/iPhone 物理真机收据。
- 尚缺实现：`event/context_change/follow_up` Trigger 的用户 setup、Connector native 建连/重连、授权/Run 完整活动历史和数据删除入口尚未接入 Skill Center；detail/setup 与显式 IANA timezone 的 daily schedule 创建，以及 Connector 目录/状态/撤权 UI，已完成本地 contract、generated client、Remote adapter 与 Widget 链路，但尚未取得环境准出证据。
- 尚缺验收证据：核心读写链已有 local_contract、真实存储 api_integration、generated Remote 与 Flutter widget 回归；Connector 另有脱敏 response、内部字段 fail-closed 和 commercial block 零 HTTP 断言。但尚无同一候选的受管 Remote 回执、主动规则 setup 物理真机 user_acceptance、撤权后 Run 安全边界验证、SLI/SLO 读回和回滚收据。
- 完成判定：`GWT-001/GWT-002` 具有 Setting/Consent/Subscription/Catalog detail 的 local_contract、api_integration 与 Flutter user_acceptance 直接 `spec_ref`；完成事件/上下文主动规则、activity、connector 和数据删除管理，并取得同一候选双端物理真机和受管环境回执。
- 依赖：Assistant contracts/codegen、Skill Center 重构与 trigger/runtime policy。
