# group-creation-member-management 设计方案

## 设计动因

发起群聊不是单页视觉问题，而是一个跨 `chat / circle / user` 的生命周期能力：

- 入口层需要新的 route / surface / sheet 结构
- 数据层需要真实群聊、真实圈子与互关关系的统一候选源
- 创建层需要原子建群与消息列表一致性
- 治理层需要私建群与圈子群的危险操作分叉

如果继续沿用现在的 `chatAddMembers + 本地 mock + 前端拼关系` 路径，进入 `/dev` 后会同时出现 IA 漂移、端云不一致和权限绕过三类风险，因此必须在 baseline 阶段一次收口。

## 上游规格评审

| 输入 | 当前结论 |
|---|---|
| `/explore` 结果 | 已明确 `L1 chat-conversation / L2 group-creation-member-management / L3 group-create-flow` |
| 用户新增澄清 | 已冻结 3 个微信对标页面、互关准入、500 人上限、圈子群不可解散、一把升级 |
| `specs/02_IOS_NATIVE_FRONTEND_UX_SPEC.md` | 图一可为正式页面；图二/图三必须是贴底非全屏 sheet；浅色/深色双模为硬约束 |
| 现有实现 | `StartGroupChatPage`、`GlobalQuickActionSheet`、`chatAddMembers` 均为待替换原型，不是目标态 |

## 方案对比

### 方案 A：继续复用 `chatAddMembers`，由端侧聚合群聊/圈子/联系人并本地过滤

优点：

- 现有页面和 route 可以少改。

缺点：

- 发起群聊与会后加人成为同一语义，路由与 surface 错位。
- 端侧需要自己拼真实群、圈子、互关关系，容易产生 N+1 和第二真相源。
- 私建群/圈子群危险操作边界难以在服务端强约束。

### 方案 B：新增独立 `startGroupChat` Journey，由 chat 域统一聚合候选源并原子建群

优点：

- 发起群聊拥有独立 route / surface / contract，IA 清晰。
- 候选源、互关过滤、500 人上限与危险操作边界都可由云侧统一执行。
- 建群、消息列表、聊天信息页可以共享一套数据真相源。

缺点：

- 需要新增 metadata、聚合接口与前端页面状态模型。

## 选型决策

**选定方案：方案 B**

## 关键设计决策

### KD-1：入口 IA 与路由分层

- 全局加号点击“发起群聊”进入独立正式页面 `startGroupChat`
- 图一为全屏导航页
- 图二“选择群聊”、图三“选择群成员”为贴底非全屏 sheet
- 不再复用 `chatAddMembers` 作为建群入口；`chatAddMembers` 只保留后续加人语义

### KD-2：候选源统一由 chat Journey 聚合，不让端侧多源拼装

建议由 chat 域提供统一候选 contract，内部再去调用：

- `messages/conversation`：真实群会话列表
- `social/circle`：用户已加入且已有 `conversationId` 的真实圈子列表
- `user` 关系能力真相源：互关判定

端侧只消费“已过滤后的来源列表 + 可选成员列表 + 可选人数”，不自己逐个查关系能力。

### KD-3：私建群采用原子建群 contract

不采用“先建空群、再逐个 AddMembers”的旧流程。

目标态：

- `CreateConversation` 扩展为支持 `initialMemberIds`
  或
- 新增专用 `CreateGroupConversation`

无论选哪种具体命名，都必须满足：

- 创建动作原子完成
- 校验 500 人上限
- 对 `initialMemberIds` 统一做互关校验与去重
- 成功后消息列表立即可见

### KD-4：圈子群与私建群生命周期明确分叉

| 类型 | 创建方式 | 解散能力 | 生命周期 |
|---|---|---|---|
| `group` 私建群 | 全局入口手动创建 | 仅群主可解散 | `active -> dissolved` |
| `group`（`circleId` 非空）圈子绑定默认群 | 由圈子绑定/事件同步 | 禁止单独解散 | 绑定 `Circle.conversationId` |

危险操作的服务端校验必须基于“是否绑定 `circleId`”这类生命周期真相源，而不是只靠前端隐藏按钮。

### KD-5：后续加人与初始建群复用同一成员资格规则

- 聊天信息页继续加人时，仍只允许加入互关成员
- 从圈子群继续拉人时，只能选该圈中与当前用户互关的成员
- 去重逻辑统一按 `userId`
- 私建群与圈子群都受 500 人上限约束

### KD-6：已选成员反馈优先于微信

图一新增正式“已选成员头像带”：

- 位于搜索框下方
- 默认最多显示三行
- 超过三行折叠
- 点击展开后显示全部
- 每个头像右上角可单独删除

该区域与聊天信息页成员网格采用同一圆角方形头像语言，但布局更偏选择反馈而不是信息展示。

### KD-7：iOS 原画质体验落点

按 `specs/02_IOS_NATIVE_FRONTEND_UX_SPEC.md` 执行：

- 图一使用正式页面语义，不做安卓式列表页
- 图二/图三使用 `AppBottomModalSurface` 等贴底 sheet 语义
- 浅色/深色必须成对设计
- 主题以蓝色强调，但分割线、圆角、背景层次比微信更轻、更干净
- 若缺少用于“已选头像折叠区”或“蓝色主按钮 disable/enable 态”的 token，先补 token 再写业务 UI

### KD-8：成员展示名端云 / Mock 一致

- `ConversationMember.displayName`（及 `avatarUrl`）由 **chat-service 写入时 enrichment**（用户展示名真相源在 user 域），端侧 **禁止** 长期依赖裸 `userId` 当展示名。
- **重名允许**；列表与 UI 去重、跳转、权限一律以 **`userId` 唯一键**。
- `MockChatRepository` 必须使用与云侧相同的字段语义（如 `nameFor(userId)`），不得再写入 `displayName: userId` 作为常态。

### KD-9：ListMembers 排序

- Query `sort` 枚举 `MemberListSort`：`joined_asc`（**默认**）、`display_name_asc`。
- `display_name_asc` 第二排序键为 `userId` 升序。
- 建群批量初始成员在同一事务内须写入 **严格单调** 的 `joinedAt`（或后续 CR 引入 `joinSequence`），保证 `joined_asc` 稳定。

### KD-10：版本与时间戳仅云端

- `Conversation.membersRosterRevision` 与 `Conversation.updatedAt` **只在服务端事务内**更新；影响面包括成员集合变化与聊天信息页可见群设置项变更（`aspects` 在设计中枚举）。
- 客户端仅用其做 **缓存失效与拉取决策**，禁止本地伪造 revision。

### KD-11：推送合并与拉取

- 对外实时主事件：**`ConversationRosterUpdated`**，合并窗口 **50–100ms**（可配置），窗口内多条变更合并为 **一条** 推送，payload 携带最新 `membersRosterRevision`、`updatedAt`、`aspects`。
- `MemberJoined`/`MemberLeft` 保留域内/审计；客户端主路径迁移至 `ConversationRosterUpdated`。
- 拉取：`ListConversationTimestamps` / `GetConversation` 与 `updatedAt` 对齐；revision 变化则定点 `ListMembers` + 必要设置接口。

### KD-12：建群事务 vs 并发更新

- **CreateConversation**：单事务创建会话 + 群主 + 初始成员 + `ConversationUserState` + **首版 revision / updatedAt**。
- **建群后更新**（`AddMembers`、`RemoveMember`、群名/管理员/规则等）：**独立事务**，允许多端并发；每事务内递增 revision 并刷新 `updatedAt`。
- **其他成员**不参与创建事务；仅通过推送 + 拉取达到一致。

## metadata / codegen 方案

本次 `/dev` 前的 metadata 真相源建议如下：

### 共享路由 / surface

- `contracts/metadata/_shared/app_routes.yaml`
  - 新增 `startGroupChat`
- `contracts/metadata/_shared/ui_surfaces.yaml`
  - 新增 `startGroupChat`
  - 维持 `chatAddMembers` 作为后续加人成员页
- `contracts/metadata/_shared/request_context.yaml`
  - 新增发起群聊相关 operation request context

### chat contract

- `contracts/metadata/messages/conversation/service.yaml`
  - 扩展原子建群 contract
  - 新增候选源/候选成员查询 operation
  - 冻结 `DissolveConversation` 仅对私建群生效
  - `ListMembers` 增加 `sort` query（`MemberListSort`）
- `contracts/metadata/messages/conversation/fields.yaml`
  - `Conversation.membersRosterRevision`
- `contracts/metadata/messages/conversation/events.yaml`
  - `ConversationRosterUpdated`（合并推送）；`MemberJoined` 标注为域内/审计向
- `contracts/metadata/_shared/types.yaml`
  - `MemberListSort` 枚举

### circle contract

- 继续使用 `Circle.conversationId`
- 继续使用 `autoSyncChat`
- 明确圈子群不可解散的消费边界

### user contract

- 复用 `GetRelationshipCapability` 或等价互关读模型
- 不允许前端继续按联系人 mock 自行推导“是否互关”

## 字段演进、迁移与升级方案

- 本次不做记录兼容字段
- 本次不保留旧发起群聊页
- 本次不做 feature flag 双轨
- 若旧 route / widget 仍存在，仅作为实施过渡代码；目标态统一切到新 route / new model

## feature flag、观测、SLO 验证与回滚方案

### feature flag

- 无业务 feature flag

### 观测

建议最少埋点：

- `group_create_entry_open_count`
- `group_create_candidate_source_latency_ms`
- `group_create_submit_success_count`
- `group_create_submit_failure_count`
- `group_dissolve_success_count`
- `group_dissolve_blocked_circle_group_count`

### SLO 验证

- 发起页首屏壳层
- 来源 sheet 首批可见耗时
- 建群成功回流消息列表耗时
- 私建群解散后 inbox 清理成功率

### 回滚

- 产品内不设计兼容回滚
- 工程层只保留整版发布回退，不做双轨逻辑

## T1~T4 证据矩阵

| Slice/对象 | T1 | T2 | T3 | T4 |
|---|---|---|---|---|
| route / surface / request context | schema contract | — | metadata verify | — |
| 发起页 / 已选区 / 三行折叠 | — | widget + journey | — | 真机交互 |
| 群来源 / 成员来源 sheet | schema contract | widget | integration | 真机交互 |
| 原子建群 | contract | journey | API + storage + inbox | 主路径旅程 |
| 后续加人 / 解散边界 | contract | widget | API + inbox cleanup | 主路径旅程 |
| 成员 roster / revision / 合并推送 | metadata + contract | provider + handler | API + Redis + 双账号 | 主路径旅程 |

## 未来演进

- 企业联系人来源
- 群二维码分享
- 多圈子群频道
- 候选源更大规模分页与增量索引优化
