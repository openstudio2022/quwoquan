# Tasks: chat-group-admin-govern — 群聊管理与权限治理

## Phase A — 数据模型与接口

- [ ] A1: 新建 `ConversationGroupSettings` DTO（`lib/cloud/chat/models/conversation_group_settings.dart`）→ A2
- [ ] A2: `ChatRepository` abstract 新增 `getGroupSettings`、`updateGroupSettings`、`transferOwnership`、`updateGroupAdmins`、`dissolveConversation` 方法 → A8~A9
- [ ] A3: `MockChatRepository` 实现新增方法（本地状态模拟）→ A8~A9
- [ ] A4: `RemoteChatRepository` 实现新增方法（HTTP 调用）→ A8~A9

## Phase B — 角色 Provider

- [ ] B1: 新建 `currentUserRoleProvider`（基于 conversationId 返回 owner/admin/member）→ A1
- [ ] B2: `ChatSettingsPage` 集成角色 Provider，控制"群管理"入口可见性 → A1

## Phase C — 群管理页

- [ ] C1: 新建 `GroupManagePage`（`lib/ui/chat/pages/group_manage_page.dart`），含二维码进群/进群需确认/仅管理员改群名开关 + 群主转让/管理员入口 + 解散群聊 → A2
- [ ] C2: 路由注册（`app_router` 新增 `/chat/{id}/manage`）→ A2
- [ ] C3: `ChatSettingsPage` 底部新增"群管理"行（仅 owner/admin 可见），点击跳转 `GroupManagePage` → A1

## Phase D — 群主转让页

- [ ] D1: 新建 `TransferOwnershipPage`（`lib/ui/chat/pages/transfer_ownership_page.dart`），成员列表+搜索+字母索引+选中确认弹窗 → A3
- [ ] D2: 确认弹窗居中实现（`CupertinoAlertDialog`）→ A3
- [ ] D3: 转让成功后 pop 并刷新角色 → A3

## Phase E — 管理员设置页

- [ ] E1: 新建 `GroupAdminsPage`（`lib/ui/chat/pages/group_admins_page.dart`），多选列表+已选头像顶栏+最多 3 人限制 → A4
- [ ] E2: 超过 3 人提示逻辑（`showCupertinoDialog`）→ A4
- [ ] E3: "完成(N)"按钮调用 `PUT /admins` → A4

## Phase F — 权限控制集成

- [ ] F1: `ChatSettingsPage` 群名称点击加权限判断（`nameEditableByAdminOnly` + 非管理员弹提示）→ A5
- [ ] F2: `ChatSettingsPage` 隐私屏障 Switch 对非管理员 `onChanged: null`（disabled）→ A6
- [ ] F3: `ChatSettingsPage` 解散入口仅群主可见（替换原"退出群聊"文案）→ A7
- [ ] F4: `ChatSettingsPage._MemberAvatar` → `RoundedSquareAvatar`（size=52）→ A10

## Phase G — WebSocket 事件

- [ ] G1: 监听 `conv.settings.updated` / `conv.owner.transferred` / `conv.admins.updated` / `conv.dissolved` 事件 → A8/A11

## Phase H — 测试

- [ ] H1: T1 — `ConversationGroupSettings` 序列化契约测试
- [ ] H2: T2 — GroupManagePage Widget test（角色可见性）
- [ ] H3: T2 — TransferOwnershipPage 确认弹窗 Widget test
- [ ] H4: T2 — GroupAdminsPage 多选限制 Widget test
- [ ] H5: T2 — 群名称权限拦截 Widget test
- [ ] H6: T2 — 隐私屏障 disabled Widget test
- [ ] H7: T1 — 新增 API 契约测试
- [ ] H8: `make gate`
