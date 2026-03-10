# Tasks: chat-list-ui-polish — 聊天列表 UI 打磨

## Phase A — 通用组件

- [ ] A1: 新建 `RoundedSquareAvatar` 组件（`lib/components/avatar/rounded_square_avatar.dart`），支持 size/imageUrl/name/borderRadius/onTap，使用 `ClipRRect` + 错误占位 → A3
- [ ] A2: 新建 `GroupAvatarGrid` 组件（`lib/components/avatar/group_avatar_grid.dart`），按 1~9+ 人布局算法渲染九宫格组合头像 → A5~A7

## Phase B — 趣聊列表页改造

- [ ] B1: Tab 居中修复 — `chat_page.dart` `_buildMainTabs` 中 `leadingActions` 添加与 trailing 等宽的透明占位 → A1
- [ ] B2: 移除小趣助理条目 — 删除 `_buildMessagesContent` 中 `showAssistant` 条件渲染块及 `_openAssistantHalfSheet` 引用 → A2
- [ ] B3: `_ConversationTile` 头像替换 — `CircleAvatar` → `RoundedSquareAvatar`；1v1 显示对方头像，群聊接入 `GroupAvatarGrid` → A3~A5
- [ ] B4: 同好列表头像替换 — `_ContactsListWithIndex` 和 `_buildContactsContent` 中 `CircleAvatar` → `RoundedSquareAvatar` → A3

## Phase C — 对话设置页头像

- [ ] C1: `ChatSettingsPage._MemberAvatar` 中 `CircleAvatar` → `RoundedSquareAvatar`，尺寸 52px → A3

## Phase D — 测试

- [ ] D1: T2 Widget test — `RoundedSquareAvatar` 圆角渲染
- [ ] D2: T2 Widget test — `GroupAvatarGrid` 各人数布局（3/4/5/6/7/8/9）
- [ ] D3: T2 Widget test — Tab 居中验证
- [ ] D4: T2 Widget test — 列表无助理条目
- [ ] D5: `make gate`
