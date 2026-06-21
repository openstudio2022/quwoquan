# L2 规格：commercial-message-system — 消息体系商用重构

> **层级**：L2_business_capability（隶属 L1 `chat-conversation`）
> **状态**：specified

## 0. 一句话定义

以商用发布为目标，重构消息模块的信息架构和端云数据边界：`消息` 回答“最近发生了什么”，`联系` 回答“我和谁建立了连接”，并通过 `Entity ⇄ Circle ⇄ Discussion ⇄ Message` 的真实云端 read model 打通实体、圈子、讨论、交集和通知。

本能力不保留旧 IA 和旧 Mock 拼接路径。App 只消费 metadata/codegen 产生的 Remote DTO；业务事实由云端聚合服务提供。

## 1. 背景

当前消息体系继承微信式“消息/联系人/聊天/群聊”心智，导致五类商用风险；2026H1 商用口径中，用户前台统一称为「讨论」，机器契约继续使用 `group`。

1. 联系人与趣我圈核心关系“交集”割裂。
2. 群被理解为聊天容器，而不是协作单元。
3. 消息流缺少实体、圈子和通知来源。
4. 联系页退化为通讯录，无法表达“我和谁建立了连接”。
5. App 端仍存在 Mock/占位拼接，无法作为商用真实数据依据。

## 2. 核心对象边界

| 对象 | 回答的问题 | 商用边界 |
|---|---|---|
| `Entity/Homepage` | 什么值得关注 | 对象页不直接拥有 `Conversation`，只通过相关 `CircleGroup.conversationId` 进入讨论。 |
| `Circle` | 哪些人因共同兴趣聚在一起 | 圈子是成员池、内容和活动聚合，不是聊天群。 |
| `Discussion/CircleGroup` | 这些人一起做什么 | 讨论是协作单元，承载公告、相册、文件、活动、成员，并绑定一个 chat `Conversation`。 |
| `Conversation` | 消息如何收发 | 只负责消息、成员、已读、会话状态、讨论头像预合成，不定义兴趣或组织语义。 |
| `Contact` | 我和谁建立了连接 | 由 `FollowEdge`、`BlockEdge`、`GreetingRequest`、`ContactDiscovery`、`ConversationMember`、`CircleMember` 聚合生成。 |
| `Intersection` | 我们有什么具体交集 | 输出最多 2 个可展示交集点和证据来源，不输出“ N 个交集”。 |
| `Notification/AppMessage` | 有哪些非聊天动态 | 持久化 inbox，支持类型、已读水位、未读计数和 dismiss/read 状态。 |

## 3. 信息架构

### 3.1 一级结构

底部导航保持：

```text
首页 / 精品 / 添加 / 消息 / 我
```

`消息` 导航项内承载两个独立一级页面状态：

```text
消息
联系
```

两者不是顶部 Segment Control 的弱切换，也不是独立底栏项。两页都不放内联搜索框；统一使用顶部工具栏搜索按钮入口。

### 3.2 消息页

目标：回答“最近发生了什么”。

顶部：

- 标题：`消息`
- 右侧：现有顶部工具栏搜索入口和小趣入口

二级胶囊：

```text
全部 / 未读 / 讨论 / 私聊 / 通知
```

列表规范：

- 统一两行布局：头像、标题、摘要、时间。
- 未读数字显示在头像右上角。
- 不显示复杂业务标签。
- `通知` 行必须来自 notification / app message 云端 inbox。
- 高保中的“小趣发现新圈子和新讨论”必须是 `AppMessage` 或 assistant insight 类型的真实通知行，不得硬编码运营卡。
- 任一会话从 `全部 / 未读 / 讨论 / 私聊` 任一筛选入口打开并完成已读回执后，所有 `MessageHome` filter 中该会话的未读计数必须同步清零；App 端需失效同一会话的所有聚合引用，服务端以 `MarkAsRead` / read watermark 驱动下一次 `ListMessageHome` 返回一致状态。

### 3.3 联系页

目标：回答“我和谁建立了连接”。

顶部：

- 标题：`联系`
- 右侧：现有顶部工具栏搜索入口和小趣入口

二级胶囊：

```text
全部 / 互相关注 / 圈子 / 讨论
```

列表规范：

- 全部：人 + 讨论混排，按最近互动时间倒序。
- 互关：仅展示互相关注用户；超过 20 人显示 A-Z 索引，小于等于 20 人不显示。
- 圈子：展示圈子列表，不展示联系人列表；点击进入圈子联系人页。
- 讨论：仅展示已加入的讨论，不展示聊天内容或公告，按最近活跃排序。
- 所有摘要最多展示 2 个具体交集点，如 `摄影圈 · 九寨沟`。

## 4. 云端契约

### 4.1 消息首页聚合

`messages/conversation` 必须提供商用消息首页 read model。实现可复用现有 `ListInbox` 投影，但契约必须明确过滤维度：

- `all`
- `unread`
- `group`
- `direct`
- `notification`

`notification` 维度不得由 App 从标题或摘要猜测，必须来自 `notification-service` / `app-message` inbox。

### 4.2 联系首页聚合

`messages/conversation` 或 chat 聚合服务必须提供联系首页 read model：

- `kind`: `user | circle | group`
- `objectId`
- `conversationId`
- `circleId`
- `circleGroupId`
- `entityId`
- `title`
- `avatarUrl`
- `summaryIntersections`
- `memberCount`
- `lastActiveAt`
- `sortKey`

App 不得在 UI/Provider 中拼接来源、成员数、最近互动或交集文案。

### 4.3 讨论主页与聊天信息

讨论页和聊天信息页必须消费同一个 `GroupHome` 事实源（技术对象名保持 `GroupHome`，用户前台显示「讨论」）：

- 讨论名称
- 来源实体
- 来源圈子
- 成员数
- 公告
- 能力入口：相册、文件、活动、成员
- 讨论治理能力：加成员、移除成员、管理员、转让群主、退出或解散
- 讨论头像资产：云端预合成 `avatarUrl`

### 4.4 交集与通知

- `Intersection` 契约必须独立或明确迁入 `recommendation/intersection`，输出 `IntersectionPoint`、`IntersectionReason`、`ObjectIntersectionSummary`、`ContactIntersectionSummary`。
- `notification-service` 必须实现 `/v1/app-messages`、未读数、标记已读、类型分页和持久化存储。
- `messages/conversation` 的 `ListMessageHome`、`ListContactHome`、`GetGroupHome` 与 `MarkAsRead` 必须由真实持久化 read model / read watermark 支撑，禁止仅靠 App 本地缓存或 Mock 拼接维持筛选状态。

## 5. 商用删除项

以下不得作为商用主路径：

- App 端依赖 `MockChatRepository`、`MockIntersectionRepository`、`MockAppMessageRepository` 或本地 prototype bundle 拼业务列表。
- Remote 返回空的联系人圈子/讨论后由 App 自行拼接。
- 服务端生产默认使用 `mock-user`、memory store、noop resolver 或 baseURL 为空返回空。
- App 消费退役字段 `Circle.conversationId`、`ChatInbox.avatarCompositeUrls`。
- 旧消息筛选 `@我 / @小趣 / 提醒` 作为新首页主 IA。

## 6. 非功能要求

- 生产包默认 Remote，无 Mock/Remote 切换入口。
- 页面首屏 p95 <= 300ms；本地已有缓存时先展示缓存，再用 Remote 刷新。
- 关系门禁必须服务端强校验，不信任 App 筛选。
- 讨论头像新建后可见前必须有非空 `avatarUrl` 或稳定服务端 fallback 资产。
- 所有新增路径、operation、surface、error code 均 metadata-first。

## 7. 测试映射

| 验收意图 | 主证据 | 覆盖 |
|---|---|---|
| SIT | local_contract/api_integration | 消息页、联系页、群主页、通知、交集聚合协同。 |
| contract | local_contract/api_integration | metadata、DTO、Remote/Mock、真实服务 contract 一致。 |
| UAT | user_acceptance | 商用真机旅程：消息、联系、讨论、聊天信息、通知已读。 |

## 8. 关联文档

- `specs/feature-tree/chat-conversation/commercial-message-system/acceptance.yaml`
- `specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md`
- `specs/feature-tree/chat-conversation/group-creation-member-management/spec.md`
- `quwoquan_service/contracts/metadata/messages/conversation/service.yaml`
- `quwoquan_service/contracts/metadata/notification/notification/service.yaml`
