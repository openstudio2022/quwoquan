# L3 Story：群聊圈子共享 Skill 挂载 (`shared-surface-skill-placement`)

> 所属能力：[用户 Skill 产品与集成平台](../spec.md)
>
> Journey / Scenario：[`JNY-009 / SCN-018`](../../../spec.md#scn-018)、[`SCN-034`](../../../spec.md#scn-034)
>
> 设计归属：[`L2 DEC-001`](../design.md#dec-001)

## 1. 用户价值

作为群主或圈主，我希望只添加一次小趣，就能默认使用全部适合共享场景的官方 Skill，并能清楚禁用不需要的能力，从而不必为每项能力重复拉机器人或维护单 Skill 成员。

## 2. 范围与非目标

### In Scope

- SkillSurfacePlacement、`all_shared_eligible` policy、disabledSkillIds、管理员权限、active package 变更提示与共享隐私。

### Out of Scope

- Chat/Circle 成员真相、个人设置覆盖群内其他成员、共享读取个人记忆/Connector。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 一个小趣按 Placement 路由多个共享安全 Skill

- 添加小趣到 Conversation/Circle 时创建 `all_shared_eligible` Placement；可用集合为 active package 中 shared-safe 且未被管理员禁用的 Skill。
- 新发布 shared-safe Skill 自动进入该 policy，并向管理员提供可见变更提示；管理员修改必须 revision/CAS、可审计且立即对新 Run 生效。
- Chat Membership/Invite/AssistantMentioned 不得携带或绑定 `assistantSkillId`；共享回答不得读取任何成员的个人记忆、个人 Connector 或私密动作 receipt。

## 4. 契约引用

- object / projection：`assistant.SkillSurfacePlacement`
- event / metric：`chat.AssistantMentioned`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 管理员禁用共享 Skill 后立即生效且无私人泄漏

- GIVEN 群内小趣可使用 travel_companion 与另一个 shared-safe Skill，一名成员个人连接了日历。
- WHEN 管理员禁用 travel_companion，普通成员再次 @小趣并要求修改旅行日历。
- THEN Router 不选择 travel_companion，普通成员不能修改 Placement，个人日历 connection/receipt 不进入群消息或共享 Context。
- AND 管理员重新启用后新 Run 可使用 Skill，旧 Run 在安全边界按最新 Placement 停止不再允许的能力。

## 6. 依赖

- 前置要求：Chat/Circle assistant placement event、active package shared-safe profile 和管理员 authority。
- 上游事实：assistant member、surface、active Skill package 与管理员 policy。
- 下游结果：Run routing set、管理员 UI 与 audit activity。
- 父级设计：`DEC-001`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 Placement 管理体验与 Circle 验收尚未完成

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺群聊/圈子管理员维护禁用 Skill 的 App 入口、Circle placement event 和共享场景 user acceptance。ConversationMembership、Invite、AssistantMentioned 与 App member wire 的 `assistantSkillId` 已物理删除，SkillSurfacePlacement 已具有 canonical object、管理员 authority、PostgreSQL CAS/outbox、Chat membership projector 和路由许可门。
- 完成判定：补齐 Circle placement event 与管理员 UI，`GWT-001` 具有 Assistant/Chat/Circle local_contract、api_integration 与群聊/圈子 user_acceptance 直接 `spec_ref`；旧字段保持物理不存在，无 alias/dual read。
- 依赖：Chat contract/codegen 单轨迁移与 App group admin surface。
