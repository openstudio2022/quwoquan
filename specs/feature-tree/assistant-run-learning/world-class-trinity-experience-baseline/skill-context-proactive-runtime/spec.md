# L3 Story：Skill 上下文与主动运行统一 (`skill-context-proactive-runtime`)

> 所属能力：[小趣统一体验](../spec.md)
>
> Journey / Scenario：[`JNY-009 / SCN-020`](../../../spec.md#scn-020)
>
> 设计归属：[L2 DEC-003](../design.md#dec-003)

## 1. 用户价值

作为使用或订阅垂类助理能力的用户，我希望每个 Skill 只读取完成任务所需且已获授权的上下文，并让主动提醒与现场提问保持同一质量和隐私边界。

## 2. 范围与非目标

### In Scope

- 不可变 Skill Package、渐进披露、typed Context Requirement/Snapshot 与主动 Trigger。
- 响应式和主动式运行共享 Skill、Context、Tool、Presentation 与 Run 主线。

### Out of Scope

- Skill 商店交易、未授权的跨用户记忆、由 Scheduler 生成领域内容。

## 3. 行为要求

### REQ-001 垂类 Skill 通过资产包扩展

- Skill 必须引用独立的激活、上下文、能力、展示、评测和提示资产；只有选中后才加载正文与完整能力声明。
- 新增垂类能力不得要求修改通用编排器，除非确实增加新的领域 Reader 或 Tool Adapter。

### REQ-002 上下文按需求、权限和预算装配

- 每个上下文槽位必须声明来源、权威、敏感等级、时效、预算与缺失恢复策略。
- Skill 不得扩大平台隐私上限；公共或群聊渠道不得注入私密长期记忆。

### REQ-003 主动 Trigger 复用标准 Run

- schedule、event、context change 与 follow-up Trigger 必须转换为带触发原因和去重语义的标准 AssistantRun。
- Scheduler 只负责到期、租约、静默、频控、去重和投递，不得维护第二套领域文案或答案生成路径。

## 4. 契约引用

- object / projection：`AssistantSkillManifest`、`AssistantContextProfile`、`AssistantContextSnapshot`、`AssistantTriggerEnvelope`
- event / metric：`assistant_skill_activation`、`assistant_context_resolution`、`assistant_proactive_delivery`
- error / recovery：`ASSISTANT.USER.context_consent_required`、`ASSISTANT.DEPENDENCY.context_unavailable`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 旅行主动 Skill 无专用编排分支

- GIVEN 用户订阅旅行风险提醒并授权所需行程与偏好上下文。
- WHEN 天气或交通信号触发主动运行。
- THEN 标准 Run 按 Skill Profile 装配行程、偏好、天气、交通与证据并生成投递内容。
- AND 未授权或过期上下文不会进入模型或投递。

<a id="gwt-002"></a>
### GWT-002 公共渠道隐私收敛

- GIVEN 同一 Skill 可在私人会话与群聊中触发。
- WHEN Context Resolver 组装两种渠道的快照。
- THEN 群聊快照不包含私人长期记忆，Skill 声明不能覆盖该限制。

## 6. 依赖

- 前置要求：Skill Catalog、Consent、Subscription 与 immutable release activation 可用。
- 上游事实：Trigger、用户授权、会话渠道与领域 Reader。
- 下游结果：Context Snapshot、标准 Run 与投递回执。
- 父级设计：`DEC-003`

## 7. 开放事项

### OPEN-001 受管主动投递与真机撤权验收尚未闭环

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前仍缺 Gamma/Prod Provider readiness 证据、Alpha 受保护 Provider material、旅行主动 Skill 的真实投递收据，以及 Android/iPhone 真机撤权收据。Skill activation/context/capability/presentation/evaluation/replay 已绑定不可变 release digest，Catalog 原子 activate/rollback、Context Resolver/Consent fail-closed、渠道隐私上限、Trigger→canonical AssistantRun、Mongo Subscription、Redis lease 去重和真实 Run Worker API integration 已有 direct 证据；Skill Center 撤权/恢复 Patrol UAT 已定义。
- 完成判定：在受管候选身份和同一 baseline 上执行 release→consent→subscription→trigger→context→run→delivery→unsubscribe；重复 tick 不重复投递、撤权下一次运行生效、public/shared 私密记忆泄漏为 0，并由 Android/iPhone 真机 UAT 直接引用本 GWT。
