# chat-list-ui-polish 设计基线

## 设计动因

本次不是简单的头像或间距微调，而是将趣信会话列表从“原型期 UI + 多套本地 Map 形态拼装”升级为“微信式扫描体验 + inbox-first 数据链路”的正式商用方案。

核心问题有三类：

1. UI 断层：第二行摘要、右上时间、组合头像灰底、弱分割线、胶囊滚动显隐都未达到微信消息页基线。
2. 数据断层：当前页面同时消费 `listConversations`、`PrototypeMockData`、本地临时字段，导致 `lastMessagePreview`、时间、未读和 `@我` 没有统一真相源。
3. 生命周期断层：用户读完消息后，列表行未读数、`@我` 角标、`未读` 角标没有统一减数模型，无法保证体验稳定。

本期明确排除密信，只完成 `全部 / @我 / 未读` 三条主链路。

## 上游输入评审

- `L1_capability` 已定位为 `chat-conversation`
- `L2_feature` 已定位为 `chat-experience-optimization`
- `L3_story` 已定位为 `chat-list-ui-polish`
- `spec.md` 已冻结：
  - 微信式两行列表行
  - 组合头像与灰底
  - 弱分割线
  - 二级胶囊显隐无留白
  - `@我` / `未读` 角标
  - inbox-first 端云一致性
- `acceptance.yaml` 已冻结 A1~A11，覆盖 UI、模型、减数、一致性与本期排除项

当前代码/契约现状：

- App 路由已走 codegen：`AppRoutePaths.chatDetail(...)`
- Chat API metadata 已有 `ListInbox` operation / pageId 常量
- `ChatPage` 当前仍以 `listConversations()` + raw `Map` 为主数据源
- `chat_inbox.yaml` 已存在，但尚未生成 app 可直接消费的 `ChatInboxDto`
- `openapi.yaml` 尚未补 `/v1/chat/inbox`

## 对标输入分析

用户提供的微信消息列表示意，关键不是单个像素，而是四个体验原则：

1. **信息层级稳定**：标题、摘要、时间三层权重明确，首屏可高速扫读。
2. **弱对比但清楚**：分割线、组合头像灰底都不抢眼，但能帮助用户快速分辨行边界和头像容器。
3. **交互位移自然**：上滑隐藏导航时，内容必须补位，不能留下导航本身的占位空洞。
4. **提醒语义可信**：`@我` 和未读是用户优先级判断入口，数字必须可信且读后可解释地递减。

本期不照搬微信全部 IA，只对齐其消息列表的核心扫描体验。

## 方案对比

### 方案 A：沿用 `ListConversations`，UI 本地补齐摘要、时间、`@我` 和组合头像

做法：

- 保持列表仍走 `GET /v1/chat/conversations`
- 页面通过本地 `Map` 兼容层补 `lastMessagePreview`
- `@我` 用 `hasMention` 或消息临时遍历计算
- 群头像通过本地 mock 或按需成员请求拼装

优点：

- 变更范围小
- 不需要新增 DTO
- 能较快出视觉结果

缺点：

- 违背单一真相源
- `@我` / 未读减数仍是本地猜测
- 群头像和标题回退规则无法稳定上云
- 未来接真实后端时会再次返工

结论：**拒绝**。该方案只能做 demo 级还原，无法满足本期“端云一致 + 商用品质”的目标。

### 方案 B：`ListInbox` 单一数据源，直接在 UI 层消费 projection `Map`

做法：

- 会话列表切到 `GET /v1/chat/inbox`
- 仓库仍返回 `List<Map<String, dynamic>>`
- UI 用 typed view-model 适配 `title / preview / unread / mention / avatarCompositeUrls`

优点：

- 已切到正确后端入口
- 改动量比新增 DTO 小

缺点：

- 仍保留 raw `Map` 字段名硬编码
- 角标与时间映射缺少类型边界
- 容易再次演变成页面层第二真相源

结论：**不选**。比方案 A 好，但仍不够稳。

### 方案 C：Inbox-first + projection DTO codegen + typed view-model（选定）

做法：

- `GET /v1/chat/inbox` 作为唯一列表数据源
- 扩展 `chat_inbox.yaml`，补齐本期 UI 所需字段与 `client_projection`
- 通过 codegen 生成 `ChatInboxDto`
- App 侧只基于 `ChatInboxDto -> ChatListItemViewModel` 渲染
- 读完消息后，通过统一缓存/状态刷新同源更新列表与角标
- 通过 feature flag 保留旧列表数据源回滚能力

优点：

- 真相源单一
- 兼容 codegen 路径，后续成本最低
- `@我` / 未读减数可和 read model 对齐
- UI 与后端投影语义清晰分层

缺点：

- 涉及 metadata / openapi / codegen / repository / cache / page 全链路
- 需要设计回滚与双读策略

结论：**选定方案 C**

## 选型决策

选定 **方案 C：Inbox-first + projection DTO codegen + typed view-model**。

理由：

- 这是唯一同时满足“微信式体验”和“端云一致性”的方案。
- 现有项目已经支持 projection → app DTO codegen，技术路径成熟。
- `@我` / 未读 / 组合头像都属于 per-user inbox 视角，不应继续绑定在 `Conversation` 或 UI 本地推断上。

## 关键设计决策

### KD-1：会话列表唯一数据源切到 `ListInbox`

- `ChatPage` 的主列表不再直接消费 `listConversations()`
- 页面统一调用 `ChatRepository.listInbox(limit: 100)`
- `全部` 展示所有 inbox 项
- `@我` 过滤 `mentionUnreadCount > 0`
- `未读` 过滤 `unreadCount > 0`

### KD-2：引入 `ChatInboxDto`，页面不再读 raw `Map`

- 在 `messages/conversation/projections/chat_inbox.yaml` 上增加 `client_projection`
- codegen 生成 `quwoquan_app/lib/cloud/runtime/generated/chat/chat_inbox_dto.g.dart`
- UI 再从 `ChatInboxDto` 映射到本地渲染用 `ChatListItemViewModel`

分层：

- metadata / projection：定义字段与别名
- DTO：负责 `fromMap`
- view-model：负责展示级格式化
- widget：纯渲染

### KD-3：本期新增 inbox 字段

为满足 PRD，本期在 `ChatInbox` 读模型中新增或冻结以下字段：

- `mentionUnreadCount: int`
- `avatarCompositeUrls: []string`
- `title: string` 作为列表展示标题，允许 projector 在群名为空时回退为成员名称摘要
- `lastMessagePreview: string` 作为唯一摘要字段
- `lastMessageTime: timestamp`
- `unreadCount: int`
- `pinned: bool`
- `muted: bool`

约束：

- `title` 在列表语义上是“display title”，不是必须等于原始会话 title
- `avatarCompositeUrls` 仅用于群聊；单聊仍读 `avatarUrl`

### KD-4：组合头像完全由 inbox row 驱动，不在列表中额外请求成员

- 群聊 1~9 宫格所需头像 URL 由 inbox 投影直接提供
- UI 不在列表页逐行调用 `listMembers`
- 成员排序规则以 joinedAt 顺序为准，由 projector 负责稳定输出

### KD-5：`@我` 采用 per-user 提及未读数，而不是“是否出现过 mention”

- `@我` 胶囊显示 `mentionUnreadCount` 汇总
- `@我` Tab 仅展示 `mentionUnreadCount > 0` 的会话
- 进入会话并完成已读同步后，该会话的 `mentionUnreadCount` 归零或按 readSeq 重新计算

### KD-6：列表显隐动画通过“高度收缩”实现，不允许仅做视觉位移

- 二级胶囊隐藏必须通过高度变化 + clip 方式完成
- 列表内容区要即时补位
- 避免出现上滑后保留原高度的白色空洞

### KD-7：摘要与时间格式在 view-model 层统一，不在 widget 内散写规则

- 时间格式化独立为纯函数
- 非文本消息摘要映射独立为纯函数
- widget 只消费 `title / subtitle / timeLabel / badgeCount / avatarModel`

## metadata / codegen 方案

### 1. metadata 变更

需要更新：

- `quwoquan_service/contracts/metadata/messages/conversation/projections/chat_inbox.yaml`
- `quwoquan_service/contracts/metadata/messages/conversation/service.yaml`
- `quwoquan_service/contracts/metadata/messages/openapi.yaml`
- `quwoquan_service/contracts/metadata/messages/conversation/tests/mock.yaml`

设计要点：

1. 在 `chat_inbox.yaml` 中新增 `client_projection`
2. 在 projection fields 中补 `mentionUnreadCount`、`avatarCompositeUrls`
3. `service.yaml` 的 `ListInbox` 描述与 response contract 与 projection 语义对齐
4. `openapi.yaml` 补 `/v1/chat/inbox` 与 `ChatInboxPage` / `ChatInboxItem` schema

### 2. codegen 产物

预期新增/更新：

- `quwoquan_app/lib/cloud/runtime/generated/chat/chat_inbox_dto.g.dart`
- `quwoquan_app/lib/cloud/runtime/generated/chat/chat_api_metadata.g.dart`（如 metadata 说明变更触发）
- `quwoquan_app/lib/cloud/runtime/generated/chat/chat_request_page_ids.g.dart`（如有 pageId 说明补充）

### 3. Repository 设计

`ChatRepository` 增加：

```dart
Future<List<ChatInboxDto>> listInbox({
  String? cursor,
  int limit = CloudApiDefaults.pageLimit,
});
```

Remote 实现：

- 使用 `ChatApiMetadata.listInboxPath`
- 使用 `ChatRequestPageIds.listInbox`
- 统一走 `CloudResponseDecoder.asCursorPage`

Mock 实现：

- 使用同结构 mock row 映射为 `ChatInboxDto`
- 不再让 `ChatPage` 直接依赖 `PrototypeMockData.chatMockConversations`

## 字段演进、迁移 / 回填与双读双写方案

### 字段演进

- `mentionUnreadCount`：新增，服务端 projector 维护
- `avatarCompositeUrls`：新增，服务端 projector 输出前 9 个成员头像 URL
- `title`：在 inbox 中定义为 display title，可由 projector 做群名为空时的成员名回退

### 数据迁移 / 回填

- 不对 `Conversation`、`Message`、`ConversationUserState` 做破坏性 schema 迁移
- 采用 **read model 重建 / 回填**：
  - 从现有 Conversation / Message / ConversationMember / ConversationUserState 重投影 `rm_chat_inbox`
  - 为历史会话补齐 `mentionUnreadCount` 和 `avatarCompositeUrls`

### 双读双写

- 服务端保持旧 `ListConversations` 不下线
- App 端采用 **双读择一**：
  - flag 开启：优先 `listInbox`
  - flag 关闭：回退 `listConversations`
- 不做长期双写逻辑；read model 是投影结果，本质为单写源多视图

## Feature Flag、观测、SLO 验证与回滚方案

### Feature Flag

建议新增客户端开关：

- `chatInboxListEnabled`

行为：

- `true`：会话列表走 `listInbox`
- `false`：继续走旧会话列表实现

退出条件：

- staging 验证通过且线上 1 周内无 badge 错数 / 排序错误 / 组合头像缺失后，删除旧路径

### 观测

客户端埋点 / 日志建议：

- `chat_list_source = inbox | conversation`
- `chat_inbox_row_missing_preview`
- `chat_inbox_row_missing_time`
- `chat_badge_count_rendered`
- `chat_subtab_hide_show_latency_ms`

服务端指标建议：

- `chat_inbox_query_latency_ms`
- `chat_inbox_projection_lag_ms`
- `chat_inbox_backfill_rows_total`
- `chat_inbox_mention_unread_mismatch_total`

### SLO 验证

- 缓存首屏可见时间
- inbox 请求返回时间
- 100 条列表滚动流畅度
- 进入会话后 badge 递减传播时延

### 回滚

- 保留旧 `listConversations` 路径
- 保留旧 `ChatPage` 数据源切换开关
- 如出现 inbox 缺字段、badge 错数、排序异常：
  - 关闭 `chatInboxListEnabled`
  - 回退到旧列表
  - 不影响详情页、发消息、已读接口

## TDD / ATDD 策略

### T1

- `ChatInboxDto.fromMap` 解析测试
- 时间格式纯函数测试
- 摘要映射纯函数测试
- `@我` / 未读汇总与减数逻辑测试

### T2

- `ChatPage` widget / integration 测试：
  - 两行列表行
  - 右上时间
  - 组合头像灰底与布局
  - 弱分割线
  - 空状态文案
  - 上滑隐藏 / 回滑恢复无留白

### T3

- contract / metadata 测试：
  - `ListInbox` response contract
  - `ChatInboxDto` codegen 对 projection 对齐
  - `mentionUnreadCount` / `avatarCompositeUrls` 字段存在
  - `MarkAsRead` 后 unread / mention 递减语义一致

### T4

- staging / 真机对比微信：
  - 扫读效率
  - 头像辨识度
  - 分割线弱存在感
  - 胶囊显隐平滑度
  - badge 可信度

## Task 与 T1~T4 证据矩阵

| Task | 目标 | 对应验收 | 证据层 |
|---|---|---|---|
| M1 | 补 inbox projection 字段与 client_projection | A8 A10 | T3 |
| M2 | 补 service/openapi/mock contract | A10 | T3 |
| C1 | verify-metadata / codegen / codegen-app | A10 | T3 |
| B1 | 新增 `ChatRepository.listInbox` | A10 | T2 T3 |
| B2 | 列表切到 inbox-first + feature flag | A8 A10 A11 | T2 T3 |
| B3 | `ChatListItemViewModel` 统一 title/preview/time/badge | A1 A4 A8 A9 | T1 T2 |
| B4 | `_ConversationTile` 微信式行结构 | A1 A3 A4 | T2 T4 |
| B5 | `GroupAvatarGrid` 接入 inbox composite avatars | A2 A5 | T2 T4 |
| B6 | 空状态与胶囊显隐修复 | A6 A7 | T2 T4 |
| B7 | 已读同步后列表与胶囊减数刷新 | A8 A9 | T1 T2 T3 |

## 未来演进

- 密信单独作为后续 story 设计，不与本期主链路混做
- 群头像可进一步接入成员头像变更事件，提升组合头像实时性
- inbox 可进一步演进为增量 sync，而非当前“缓存 + 全量刷新”模式
- 后续可补会话滑动操作、归档、置顶管理等更重的 IM 治理能力
