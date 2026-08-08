# L3 Story：群聊成员成员表版本同步 (`group-member-roster-version-sync`)

> 所属能力：[`group-creation-member-management`](../spec.md)
>
> Journey / Scenario：[`JNY-007 / SCN-013`](../../../spec.md#scn-013)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为群聊成员，我希望成员列表具有服务端版本并在成员变化后定点刷新，从而在多端看到一致的成员、排序和群资料。

## 2. 范围与非目标

### In Scope

- `ListMembers` 的服务端排序、分页和成员展示字段。
- `membersRosterRevision`、`updatedAt` 与 `ConversationRosterUpdated` 的变更通知。
- App 对受影响 conversation 的定点刷新及 Alpha adapter 契约一致性。

### Out of Scope

- 群成员权限决定由父能力其他 Story 负责；邀请链接、扫码入群和入群审批不在当前发布范围。
- RTC 信令和全量会话列表刷新。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 服务端拥有成员表版本

- `membersRosterRevision` 与 `updatedAt` 只能由 chat-service 在成员表成功变更后更新。
- `ListMembers` 必须遵循 canonical sort、分页和字段契约；App 与 Alpha adapter 不得自建排序或版本语义。

<a id="req-002"></a>
### REQ-002 变更通知触发定点刷新

- 同群同合并窗口最多发布一条 `ConversationRosterUpdated`。
- App 只刷新事件关联的 `conversationId` 及其成员页，不得每次全量刷新会话列表。

## 4. 契约引用

- operation：`chat.conversation_membership.ListMembers`
- event：`ConversationRosterUpdated`
- object/projection：`membersRosterRevision`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 多端按成员表版本收敛

- GIVEN 同一群在两个客户端打开且服务端成员表版本一致。
- WHEN 一个有权限的成员添加或移除群成员。
- THEN chat-service 更新成员表与 `membersRosterRevision` 并发布合并后的 `ConversationRosterUpdated`。
- AND 另一客户端定点读取该群和成员页后得到相同版本、排序与成员集合。

<a id="gwt-002"></a>
### GWT-002 Remote roster 读取与成员搜索保持只读

- GIVEN 已认证群成员打开成员搜索页，production Remote 的 ListMembers 返回 canonical 排序、分页、成员身份与当前 roster revision。
- WHEN 用户输入或清除搜索词、打开某个成员主页，或读取期间发生网络与权限失败。
- THEN 页面只在已读取的 roster 内按展示名或 handle 过滤并导航到该成员的 canonical Persona，搜索本身不写成员事实、不改变排序或推进 roster revision。
- AND 读取失败进入可重试页面终态并保留服务端为唯一真相，不以空搜索结果冒充空成员表，也不发起成员治理命令。

## 6. 依赖

- 前置要求：[`group-creation-member-management`](../spec.md) 的成员权限与群生命周期。
- 上游事实：chat-service 成员 command 成功提交。
- 下游结果：Conversation projection、成员页和群主页失效刷新。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 服务端事件合并证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：App 和 Alpha adapter 已有版本及定点刷新覆盖，仍需以真实 chat-service 集成测试证明同群事件合并窗口。
- 完成判定：`GWT-001` 具有 chat-service `api_integration` 与 App `local_contract` 的双向 `spec_ref`。

<a id="open-002"></a>
### OPEN-002 成员搜索页 production Remote UAT 尚未闭合

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺真实账号从 Remote roster 进入成员搜索、打开 Persona 以及读取失败恢复的页面级证据；本地过滤或 Widget 测试不能替代 production Remote user_acceptance。
- 完成判定：`GWT-002` 由同一候选的 Android 与 iPhone physical ResultBundle 直接绑定，且证明搜索期间成员写调用为零、失败不降级为空 roster。
