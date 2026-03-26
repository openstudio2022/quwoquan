# group-create-flow 设计方案

## 设计动因

本 Scenario 直接决定用户对“趣聊能不能优雅拉群”的第一印象。它同时约束：

- 全局入口 IA 是否正确
- 选人来源是不是来自真实数据
- 互关准入是否可被绕过
- 建群后消息列表是否立即一致

所以它必须在 `/dev` 前冻结成可执行设计，而不是继续停留在 mock 原型阶段。

## 输入评审

| 输入 | 结论 |
|---|---|
| 用户微信对标图一/图二/图三 | 三页结构已明确，且要求蓝色主题、iOS 原画质、整体观感优于微信 |
| UX 规范 | 图一用正式页面；图二/图三用贴底 sheet |
| 当前代码 | `StartGroupChatPage`、`create_action_sheet.dart`、`app_router.dart` 都需要重定语义 |
| 生命周期要求 | 创建成功后消息页可见；后续加人与私建群解散由同 Journey 延伸 |

## 方案对比

### 方案 A：保留现有 `StartGroupChatPage` 结构，逐步把 mock 替换成真数据

优点：

- 页面代码改动看似较少。

缺点：

- 入口和 route 仍然错误。
- 现有页面状态模型围绕 mock 设计，补真数据后复杂度更高。
- 仍然缺少原子建群 contract。

### 方案 B：以新 route + 新 provider + 新 candidate contract 重建发起群聊主路径

优点：

- IA、状态、contract 都一次性回到正轨。
- 可直接围绕三个正式页面和新 metadata 落地。
- 能让后续加人能力复用相同 candidate engine。

缺点：

- 需要新增 route、surface、provider 和服务端 candidate 读模型。

## 选型决策

**选定方案：方案 B**

## 关键设计决策

### KD-1：入口使用独立 route / surface

- 新增 `startGroupChat` route
- 全局加号直接跳转到 `StartGroupChatPage`
- `chatAddMembers` 只为已有群的“继续加人”保留

### KD-2：三页结构固定

| 页面 | 形态 | 责任 |
|---|---|---|
| 图一发起群聊页 | 正式全屏页面 | 承载搜索、来源入口、互关同好列表、已选反馈 |
| 图二来源选择 | 贴底 sheet | 选择群来源或圈来源 |
| 图三成员选择 | 贴底 sheet | 在具体来源内多选成员并确认 |

### KD-3：候选源 contract 分层

建议拆成三类读操作：

1. `ListStartGroupChatContacts`
   - 返回互关同好列表
   - 含搜索与字母索引字段
2. `ListStartGroupChatSources`
   - 按 `conversation` / `circle` 返回来源对象
   - 每项带 `eligibleMemberCount`
3. `ListStartGroupChatSourceMembers`
   - 传入来源 id，返回可选成员列表
   - 已完成互关过滤

这样做的原因：

- 图一、图二、图三各自只关心单一数据形态
- 端侧可避免自己用 `listMembers + capability` 做 N+1
- 后续“继续加人”可以复用第 3 类 contract

### KD-4：已选成员采用统一 view model

建议端侧统一成：

- `userId`
- `displayName`
- `avatarUrl`
- `sourceKinds`
- `sortKey`

这样可以稳定处理：

- 跨来源去重
- 同一用户来自多个来源时的保留策略
- 已选区顺序
- 搜索结果高亮/回填

### KD-5：原子建群采用单提交模型

提交 payload 至少包含：

- `title`（可为空，由服务端按成员名兜底生成）
- `type=group`
- `initialMemberIds`
- `maxGroupSize=500`

提交成功后，服务端需要完成：

- 去重
- 互关校验
- 上限校验
- 创建 `Conversation`
- 建立 owner/member 关系
- 更新用户会话列表可见性

### KD-6：消息页回流采用“创建成功后返回上一层并刷新”策略

优先策略：

- 提交成功后返回消息页
- 消息页 conversation provider 主动 refresh
- 若后端已返回新会话摘要，优先本地插入并与 refresh 结果对齐

这样能保证：

- 视觉上即时看到新群
- 不必依赖整页重启

### KD-7：图一视觉优于微信的具体落点

- 已选头像区提供更强反馈
- 主按钮使用更清晰的 blue filled/disabled 分层
- 分组标题、分割线、背景层级更轻
- A-Z 索引触达区适配 iOS 单手滑动
- 深色模式避免过高对比度和纯黑底

## metadata / codegen 方案

### 需要冻结的 metadata

- `_shared/app_routes.yaml`
  - `startGroupChat`
- `_shared/ui_surfaces.yaml`
  - `startGroupChat`
  - `startGroupChatSelectSourceSheet`
  - `startGroupChatSelectMembersSheet`
- `_shared/request_context.yaml`
  - 上述页面/operation 的 request context
- `messages/conversation/service.yaml`
  - 建群提交 operation
  - 来源查询 operation
  - 来源成员查询 operation

### codegen 目标

- App router path builder
- surface id / page id 常量
- chat repository operation metadata

## 字段与状态演进

- 旧的 `_contacts`、`_mockCircles`、`_groupConversations` 原型状态全部下线
- 新的 provider 统一维护：
  - 搜索词
  - 当前已选成员集合
  - 来源 sheet 状态
  - 当前来源成员列表状态
  - 提交中/失败态

## 失败与降级

- 同好列表失败：图一保留来源入口与已选区，提示用户稍后重试
- 来源列表失败：仅阻塞该来源 sheet，不影响其它来源
- 提交失败：保留已选成员，不清空页面状态

## T1~T4 证据矩阵

| 能力 | T1 | T2 | T3 | T4 |
|---|---|---|---|---|
| route / surface / operation | metadata contract | — | verify/codegen | — |
| 图一页面壳层与已选区 | — | widget | — | 旅程验收 |
| 图二/图三 sheet | source/member contract | widget | integration | 旅程验收 |
| 原子建群与消息页回流 | create contract | journey | API + repository | 真机主路径 |

## 未来演进

- 支持最近建群模板
- 支持更大规模联系人增量索引
- 支持成员来源标签可视化
