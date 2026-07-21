# L2 规格：圈子协作工具

## 背景与动机

新的群组基线已经明确：群不是纯聊天群，而是圈子或组织主页内可加入的子单元，至少承载 `交流 / 资料 / 公告` 三类能力。当前协作层仍存在三类缺口：

- 群还没有被定义为稳定的协作单元，只剩“群聊入口”心智。
- 公共群、自建群、组织节点还没有统一的协作能力边界。
- 群组层公开内容与群层交流/资料之间仍缺少清晰分工。

本 L2 的目标，是冻结群协作工具的基础能力边界：资料、交流以及与群组层内容发布的协同关系。

## 目标用户

- 群组成员：加入公共群或自建群后，希望在群里交流、看资料、接收公告。
- 圈主 / 圈管、负责人 / 管理员：配置公共群、管理资料权限、控制成员同步规则。
- 群主 / 群管：管理单个群的交流秩序、资料与公告。

## 功能范围

### L3: circle-storage（资料能力）

- 资料能力是群的核心协作能力之一，可挂载在公共群、组织节点和允许开启资料能力的自建群上。
- 支持基础 CRUD：创建文件夹、上传文件（≤50MB 单文件）、下载、删除、重命名。
- 文件列表支持按类型 / 时间 / 大小排序，支持搜索。
- 资料能力默认对公共群和组织节点开启，自建群可由创建者或上位治理者决定是否开启。
- 文件元数据存 MongoDB（CircleFile 实体），文件本体存对象存储。

### L3: circle-group-chat（群交流能力）

- 群是圈子或组织主页中的子单元；群内默认开启 `交流`，交流复用 chat 域 Conversation 能力。
- 群分为 `公共群` 与 `自建群`。
- 单个 CircleGroup 的 active 成员上限与其绑定 Chat Conversation 统一为 **1000**；大型群组通过多个命名公共群或组织节点分流，禁止以异步投影静默丢失第 1001 名成员。
- 组织型群组优先通过组织节点分流，而不是简单生成“大厅 2 / 大厅 3”。
- CircleGroup 是成员、角色与归档生命周期的唯一写入者。它的 transactional outbox 依次驱动 Chat 名册投影，Chat 反向以 durable binding event 回写 `CircleGroup.conversationId`；不得由页面、同步 RPC 或 Chat HTTP 命令直接拼装/篡改绑定。
- `CircleGroupMembership.active / left / removed / role_changed` 必须分别同步为 Chat 的成员加入、离群清理、角色更新；`CircleGroupArchived` 必须终止绑定会话并清理所有 ChatInbox 可达性。

### L3: circle-publishing-zone（群组层内容发布区）

- 群组详情页仍然承接公开内容主 feed，聚合该群组下发布的 `笔记 / 作品 / 提问 / 口碑`。
- 群层不作为公开内容主时间线，主要承接交流、资料和公告。
- 发布入口统一为 `发布内容`，从群组层入口发起；需要时可带默认 groupId 或 nodeId 作为上下文，但不改变公开内容的归属层级。
- 复用 content 域的统一内容模型，不新建群内容实体。

## 不做什么（Out of Scope）

- 不做在线文档编辑、版本管理和复杂协作工作流。
- 不做 IM 协议层改造，继续依赖 chat 域能力。
- 不把群层升级为第二条公开内容时间线。
- 不在本 L2 内冻结多级组织树的完整治理细节。

## 约束

- 资料能力仍由 `contracts/metadata/social/circle_file/` 下的 typed contract 驱动；列表、单项读取和命令回执分别使用 `CircleFilePageSlice`、`CircleFileSlice` 和 `CircleFileCommandResult`，禁止以聚合存储模型或单项切片替代分页响应。
- 群交流同步必须通过事件驱动而非同步 RPC。
- 事件链必须是可重放的 Redis Stream + consumer group：`CircleGroupCreated/Archived` 和 `CircleGroupMembership*` 由 circle-service outbox relay 投递；chat-service 成功持久化后才 ACK；Chat 的 `CircleGroupConversationProvisioned` 由独立 durable relay 回写 circle-service。失败不得 ACK，达到受控重试上限必须写入有 TTL 的 DLQ 并触发健康检查/告警。
- Chat 的普通 `AddMembers / RemoveMember / LeaveConversation / TransferOwnership / UpdateMemberRole / DissolveConversation` 不得成为圈群成员或角色的写入口；圈群场景统一返回 metadata 定义的“由圈群管理”结构化错误。Chat 可以保留消息级设置，但不得反向改变 CircleGroup 权威成员集合。
- 绑定会话一律使用 `Conversation.circleGroupId` 作为唯一索引；`Circle.conversationId` 不是群绑定真相源。
- 公共群由圈级或组织级治理者管理，自建群由成员发起并由群主治理。
- 文件上传必须有大小校验和类型白名单。
- 群协作能力必须与 `发布内容 + 笔记/作品/提问/口碑` 的群组层内容模型保持边界清晰。

## 验收重点

- A1~A2：资料能力与权限模型可用。
- A3~A5：公共群 / 自建群 / 自动同步规则可用；创建、成员激活、离开/移除、角色变更、归档、重复投递和乱序到达均能收敛到同一 Chat 名册与 CircleGroup 绑定。
- A6：群组层公开内容发布区与群层协作边界清晰。
