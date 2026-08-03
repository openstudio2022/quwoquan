# L2 Business Capability：产品运营控制面基础 (`product-control-plane-foundation`)

> 所属领域：[`product-ops-growth`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

统一产品事件、实验、反馈优化与发布治理

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“product-control-plane-foundation”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-001 / SCN-004`](../../spec.md#scn-004)
  - 本能力接收：受信 operator 的账号治理输入，以及正式申诉入口形成的 intake 引用。
  - 本能力处理：以唯一 `AccountEnforcementCase` 聚合完成 moderation/appeal 双人复核、不可变 decision 与可靠投递。
  - 本能力输出：只通过 UserAccount 公开 internal command 交付 Suspend/Restore；不拥有账号状态、用户申诉入口或 App 受限体验。
  - 失败时终态：幂等冲突、前置冲突、terminal DLQ 与依赖不可用均 fail-closed，不生成或替换 decision。

- [`JNY-002 / SCN-005`](../../spec.md#scn-005)
  - 本能力接收：客户端显式提交的平台、版本与 Build，以及 runtime 已确认并脱敏的恢复异常事实。
  - 本能力处理：按 canonical app release contract 查询唯一已发布版本与官方恢复路由，并通过控制面治理其发布事实。
  - 本能力输出：当前平台可信的版本、PWA/APK/Web 恢复事实及对应发布审计，直属 Story 失败时不生成版本结论或非官方地址。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`app-release-recovery-routing`](./app-release-recovery-routing/spec.md)：公开版本查询只按平台、可见版本和 Build 返回已发布事实；公众 iOS 指向趣我圈 PWA 安装与网页版通道，Android 指向趣我圈官网签名 APK 下载通道。
- [`account-moderation-and-appeal-enforcement`](./account-moderation-and-appeal-enforcement/spec.md)：以唯一 case 聚合完成 moderation/appeal 双人复核、不可变 Suspend/Restore decision、持久化 HTTP outbox、无 PII DLQ 与同 decision 恢复。
- [`product-control-plane-contract`](./product-control-plane-contract/spec.md)：每个控制面动作必须声明 operation scope；危险动作必须记录操作者、目标、原因、revision 与结果，失败时不得生成成功审计。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 product control plane foundation 能力 SIT

- 本能力必须组合直属 Story 与公开契约，交付“统一产品事件、实验、反馈优化与发布治理”所定义的业务结果；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 各领域 product-control-plane 的统一接口契约

- `product-ops-service/contracts/**` 是 Product Ops 控制面 operation、scope、case、decision、错误与存储的唯一契约来源；禁止页面、脚本或通用 Document 复制业务状态机。
- 治理处置使用具名领域聚合表达审核、处罚、申诉复核、恢复、SLA、双签与审计；增长/实验/推荐运营使用各自 owner 的具名 command，不共享可任意扩展的万能 workflow payload。
- 推荐运营必须分别声明召回、粗排、精排/重排的受控干预边界；`ops.*` 业务配置与端侧 IA/体验配置必须由 owner contract 分离。
- 统一控制面的直接使用者包括运营、内容治理、客服与推荐策略维护者；即使同一人员兼职多个角色，危险动作仍执行 scope 隔离、独立审批身份与不可变审计。

<a id="req-003"></a>
### REQ-003 账号治理决定生产者与 UserAccount 执行者单轨协作

- Product Ops 拥有 `AccountEnforcementCase`、review、decision、command receipt、delivery outbox/application receipt 与 terminal DLQ；User 领域只拥有 `UserAccount` 状态、auth epoch、session revoke 和账号终态事件。
- Product Ops 不直写 User 存储、不复制 UserAccount 状态机、不通过 MQ 与 HTTP 双发；User Service 不反向拥有 moderation/appeal 审批工作流。
- moderation/appeal 必须使用同一个聚合与同一投递恢复机制，但 case 类型与 Suspend/Restore 动作保持显式、不可互换。

## 6. 契约与依赖

- 上游能力：[`product-ops-growth`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 product control plane foundation 能力 SIT

- GIVEN 执行“product control plane foundation 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“product control plane foundation 能力”对应动作。
- THEN 直属 Story 共同交付“统一产品事件、实验、反馈优化与发布治理”，失败终态可区分且不产生伪成功事实。

<a id="sit-002"></a>
### SIT-002 账号治理决定生产与执行投递单轨 SIT

- GIVEN 受信 operator、正式 intake 引用、真实 PostgreSQL 与 UserAccount public internal command 已按环境装配。
- WHEN moderation/appeal 被创建、并发双签、拒绝、幂等重放、投递失败、terminal DLQ 与人工恢复发生。
- THEN Product Ops 只产生一个 `AccountEnforcementCase` 状态轨、一个不可变 decision 与一个持久化 HTTP outbox；UserAccount 只执行该受信 decision。
- THEN 冲突与依赖失败均 fail-closed；无 PII DLQ、readiness、SLO 与同 decision 恢复可观测，且不以 generic workflow Document、直写 User 或第二消息通道旁路。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 product control plane foundation 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：统一产品事件、实验、反馈优化与发布治理。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 首发内容供给、创作者激活与客服运营

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：校园、旅行、住宿、路线和对象点评内容包仍需明确负责人和真实生产；种子创作者、激活规则、FAQ、客服入口与值班表需要运营执行。
- 完成判定：内容 release 通过数据工程验收并绑定对象
- 创作者任务和影响力反馈可观测
- FAQ/客服入口可达且处置 SLA、值班 owner 明确。
- 依赖：内容运营、种子创作者与客服人力。

<a id="open-003"></a>
### OPEN-003 账号治理真实环境与正式申诉入口

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺 Gamma target-scoped operator conformance、scope、服务身份、UserAccount、双端 Journey、正式申诉 intake、跨域收敛和受保护 Prod OIDC/恢复演练；仓内 contract/实现不能替代这些证据。
- 完成判定：`SIT-002` 具有直属 Story local_contract、api_integration、Gamma user_acceptance 和受保护 Prod 运行证据，且对应 P0 OPEN 全部关闭。
