# L3 Story：group-candidate-source-orchestration — 建群候选来源编排 (`group-candidate-source-orchestration`)

> 所属能力：[`group-creation-member-management`](../spec.md)
>
> Journey / Scenario：[`JNY-007 / SCN-013`](../../../spec.md#scn-013)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为发起或接收消息的用户，我希望建群/加人候选来源（互关联系人、既有群、圈子）由云侧统一编排，端侧只消费 typed 候选行，从而稳定完成会话、消息或通话协作。

## 2. 范围与非目标

### In Scope

- ListGroupCandidates / ListSelectableGroupConversations / ListSelectableGroupContactMembers 契约
- 互关过滤、已在群锁定、friendMemberCount 云侧计算

### Out of Scope

- 入群申请、邀请链接与扫码进群不在当前发布范围；候选 Reader 不返回相关入口或占位字段。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 候选来源互关过滤与已在群锁定

- Mock 与 Remote 候选行为一致且有端云证据。

<a id="req-002"></a>
### REQ-002 已在群成员在加人模式（chatAddMembers）下由候选源锁定不可再选

- 已在群成员在加人模式（`chatAddMembers`）下由候选源锁定不可再选。
- 图四与图五必须消费服务端 keyset 分页的 `items + nextCursor`。`source` 与 `query` 过滤必须先于分页；端侧只可追加同一 `CursorPage` 的后续页，不得以首屏结果作本地全集再过滤。

## 4. 契约引用

- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml#ListGroupCandidates`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml#ListSelectableGroupConversations`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml#ListSelectableGroupContactMembers`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 候选来源互关过滤与已在群锁定

- GIVEN 当前用户存在互关联系人、非互关联系人与已加入群聊。
- WHEN 打开建群向导或加人模式请求候选来源。
- THEN 候选只含互关联系人
- AND 加人模式下已在群成员被锁定
- AND 可选群列表只含 friendMemberCount>0 的群。

## 6. 依赖

- 前置要求：[`group-creation-member-management`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 候选来源互关过滤与已在群锁定

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：Mock 与 Remote 候选行为一致且有端云证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效
