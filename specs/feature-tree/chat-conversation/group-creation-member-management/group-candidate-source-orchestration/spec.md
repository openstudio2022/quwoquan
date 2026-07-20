# L3 规格：group-candidate-source-orchestration — 建群候选来源编排

> **层级**：L3_story（隶属 L2 `group-creation-member-management`）
> **状态**：specified

## 0. 一句话定义

建群与加人流程的候选来源（互关联系人、既有群聊内互关成员、圈子内互关成员）由云侧统一编排：互关判定、可选人数与去重在服务端完成，端侧只消费 typed 候选行，禁止逐群多次拉成员在端上求交集。

## 1. 业务对象与真相源

| 数据 | 唯一真相源 | operation |
|---|---|---|
| 互关联系人候选 | user 关系能力 + chat 候选投影 | `ListGroupCandidates` |
| 含互关成员的群列表（图四） | `messages/conversation` + membership | `ListSelectableGroupConversations` |
| 指定群内互关成员（图五） | membership + user 关系能力 | `ListSelectableGroupContactMembers` |

规则：

- 三个候选源均为具名 Reader/typed Slice（`ChatContactRowDto` / `SelectableGroupConversationRowDto`），端侧不拼装。
- `friendMemberCount == 0` 的群由云侧过滤，不下发。
- 候选跨来源按 `userId` 去重由发起页 ViewModel 承担；互关/拉黑校验最终由 `CreateConversation` / `AddMembers` 服务端强制（见 member-add-remove-policy）。
- 已在群成员在加人模式（`chatAddMembers`）下由候选源锁定不可再选。

## 2. 页面承载

- `start_group_chat_page`（建群/加人复用）：候选主列表 + 来源入口。
- `start_group_chat_group_picker_sheet`（图四）：可选群列表。
- `start_group_chat_member_sheet`（图五）：群内互关成员多选。

## 3. 验收重点

### local_contract

- Mock 与 Remote 候选行为 parity：互关过滤、已在群锁定、`friendMemberCount` 一致。

### api_integration

- `ListGroupCandidates` / `ListSelectableGroupConversations` / `ListSelectableGroupContactMembers` 契约（互关过滤、成员排除、query 过滤）。

### user_acceptance

- 建群向导从三类来源选人并成功建群的旅程。
