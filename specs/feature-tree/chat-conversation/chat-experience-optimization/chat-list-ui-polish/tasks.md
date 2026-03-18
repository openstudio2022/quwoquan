# Tasks: chat-list-ui-polish — 趣信会话列表对齐微信基线

## 当前交付任务

### Metadata

- [ ] M1: 更新 `quwoquan_service/contracts/metadata/messages/conversation/projections/chat_inbox.yaml`，补 `mentionUnreadCount`、`avatarCompositeUrls`，并新增 `client_projection` 生成 `ChatInboxDto` → A2 A5 A8 A10
- [ ] M2: 更新 `quwoquan_service/contracts/metadata/messages/conversation/service.yaml`，明确 `ListInbox` 为会话列表唯一读模型入口，冻结 `@我` / 未读字段语义 → A8 A10
- [ ] M3: 更新 `quwoquan_service/contracts/metadata/messages/openapi.yaml`，补 `/v1/chat/inbox`、`ChatInboxPage`、`ChatInboxItem` schema → A10
- [ ] M4: 更新 `quwoquan_service/contracts/metadata/messages/conversation/tests/mock.yaml`，补 `ChatInboxDto`、mention/unread 减数场景 → A8 A9 A10

### Codegen

- [ ] C1: 执行 `make -C quwoquan_service verify-metadata`，确认 inbox projection 与 openapi / service 契约一致
- [ ] C2: 执行 `make codegen`，刷新服务侧 / metadata 相关产物
- [ ] C3: 执行 `make codegen-app`，生成 `ChatInboxDto` 与相关 app metadata 常量

### 业务逻辑

- [ ] B1: 在 `ChatRepository` 中新增 `listInbox()` typed 接口，并为 Mock / Remote 两套实现接入 `ListInbox` → A10
- [ ] B2: 引入 `ChatListItemViewModel`，统一映射标题、摘要、时间、未读、`@我`、头像模型，禁止 widget 直接读 raw `Map` → A1 A4 A8 A9
- [ ] B3: 将 `ChatPage` 主列表从 `listConversations()` 切换到 `listInbox()`，并保留 feature flag 回滚路径 → A10 A11
- [ ] B4: 重写 `_ConversationTile` 的微信式列表行结构，完成右上时间、两行文字、弱分割线与行节奏 → A1 A3 A4
- [ ] B5: 将 `GroupAvatarGrid` 接入 `avatarCompositeUrls`，校正灰底辨识度和 1~9 宫格稳定布局 → A2 A5
- [ ] B6: 实现 `全部 / @我 / 未读` 胶囊空状态与角标逻辑，统一来自 inbox row 字段 → A7 A8
- [ ] B7: 修复二级胶囊上滑隐藏 / 回滑恢复动画，确保内容区即时补位、无留白 → A6
- [ ] B8: 在已读同步成功后刷新列表缓存与胶囊计数，确保 unread / mention 同步递减 → A8 A9

### 测试

- [ ] T1: 单元测试 `ChatInboxDto.fromMap`、时间格式、摘要映射、角标汇总与减数逻辑 → A1 A4 A8 A9
- [ ] T2: Widget / integration 测试会话列表两行布局、分割线、灰底头像、胶囊显隐和空状态 → A1 A2 A3 A6 A7
- [ ] T3: Contract / staging 级验证 `ListInbox` response contract、codegen DTO、`MarkAsRead` 后 unread / mention 递减 → A5 A8 A9 A10
- [ ] T4: 真机对标微信消息列表，验证首屏扫读感、时间层级、头像辨识度和显隐流畅度 → A2 A3 A4 A6

## 搁置任务（带规划）

- [ ] P1: 密信列表微信化改造单独立项，包含密信 badge、锁态列表、解锁态列表与权限生命周期，不并入本期主链路
- [ ] P2: 群成员头像变更驱动 `avatarCompositeUrls` 实时刷新，若现有事件流不足则补用户资料变更投影链路
- [ ] P3: inbox 增量同步替换当前“缓存 + 全量刷新”策略，降低重度用户列表首刷成本

## 未来演进任务

- [ ] F1: 会话列表滑动操作、归档、置顶管理等 IM 治理能力
- [ ] F2: 会话列表支持更丰富的消息类型摘要，如语音时长、通话状态、卡片摘要
- [ ] F3: `ChatListItemViewModel` 与详情页顶部会话头部统一为同一展示模型，减少重复格式化逻辑
