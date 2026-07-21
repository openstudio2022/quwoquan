# L2 群内核与协作工具 — 设计方案

## 设计动因

本 L2 的重点不再是“给圈子补几个协作功能”，而是把 `群` 从聊天能力里解耦出来，冻结为真正的子单元模型。没有这一步：

- 公共群 / 自建群 / 组织节点都无法统一建模
- 群主 / 群管的治理边界无法成立
- 资料、公告、聊天会继续散落在多个模型里

## 上游输入评审

| 输入 | 当前结论 |
|---|---|
| `circle-collaboration-tools/spec.md` | 已冻结公共群、自建群、群内空间与组织节点复用 |
| `circle-community/design.md` | 已冻结 `CircleGroup` 是子单元聚合，不再把群等同会话 |
| `circle-homepage-redesign/design.md` | 已冻结群主页与组织节点主页结构 |
| `content/post/*` | 需增加 `groupId/nodeId` 分发上下文 |
| `messages/conversation/*` | 需增加 `circleGroupId` 绑定字段 |

## 对标输入分析

| 对标 | 借鉴点 | 不借鉴 |
|---|---|---|
| 微信群资料页 | 群主页包含聊天、资料、公告，不等于聊天线程 | 不把聊天记录本身当群主页 |
| Discord | 子单元治理、角色边界、频道承载多能力 | 不照搬频道树与语音结构 |
| QQ 群文件 | 资料列表、权限和轻协作 | 不引入复杂版本管理 |

## 方案对比

### 方案 A：继续把 `Conversation` 当成群

优点：

- 复用现有 chat 域，开发量最小

缺点：

- 群主 / 群管、资料、公告、公开/私有都无处表达
- 组织节点无法复用
- 会继续把产品语义压扁成“聊天群”

### 方案 B：群组只有主页，不再拆群子单元

优点：

- 模型最简单

缺点：

- 无法承接多公共群、自建群、班级/部门节点
- 无法实现“加入群组后再申请入群”的明确边界

### 方案 C：引入 `CircleGroup` 子单元，绑定聊天 / 资料 / 公告 / 节点

优点：

- 公共群、自建群、组织节点可以统一建模
- 聊天、资料、公告成为群的能力，而不是群本身
- 角色、审批、搜索和聚合边界都可冻结

缺点：

- 需要 metadata、chat、content 一起补字段与契约

## 选型决策

**选定方案：方案 C**

## 关键设计决策

### DK-1：`CircleGroup` 才是群的聚合根

- `Conversation` 只是交流能力绑定
- `CircleGroup` 才承接：
  - 群主 / 群管
  - 公开 / 私有
  - 公共群 / 自建群 / 组织节点
  - 资料
  - 公告
  - 加入审批

### DK-2：加入群组与加入群严格分离

- 加入群组后不自动加入任何群
- 公共群一律 `申请加入`
- 默认公共群也不自动加入

### DK-3：公共群手动创建与扩容

- 公共群由圈主 / 圈管或组织负责人 / 管理员手动创建
- 不做系统自动分裂
- 多个公共群必须先命名后展示

### DK-4：自建群默认公开，私有群只在圈内精确/模糊搜索

- 默认公开
- 私有群不出现在默认列表
- 私有群搜索规则：
  - `groupId` 精确匹配
  - `groupName` 模糊匹配
- 搜索范围只限已在该群组中的成员

### DK-5：群治理权边界

- 上位治理者仅对公共群有最终处置权
- 不处置私有自建群
- 私有自建群由群主 / 群管自行治理

### DK-6：群资料与公告跟着群走

- 资料默认挂在 `CircleGroup`
- 公告也挂在 `CircleGroup`
- 文件上传仍采用预签名 URL 直传对象存储

### DK-7：组织节点复用同一模型

- 班级、院系、部门、团队都落在 `CircleGroup`
- 通过 `groupType=org_node` 与 `nodeType` 区分前台表现

### DK-8：节点内容归内容域，聚合归 circle 域编排

- 内容仍由 content 域存储
- `groupId/nodeId` 进入内容分发表
- 父节点聚合按 `lastActiveAt` 排序

### DK-9：CircleGroup → Chat 使用双向 durable event，而非同步 RPC 或页面拼装

`CircleGroup` 是群单元与成员治理的聚合根，`Conversation` 只是其交流能力。因此绑定与名册使用下列单一链路：

```text
CircleGroupCreated
  → events.circle.groups
  → chat circle-group provisioner
  → Conversation(circleId, circleGroupId) + owner ConversationMember + ConversationUserState
  → CircleGroupConversationProvisioned
  → events.chat.circle-group-bindings
  → circle binding projector
  → CircleGroup.conversationId

CircleGroupMembershipActivated / Left / Removed / RoleChanged
  → events.circle.group-memberships
  → chat circle-group membership projector
  → ConversationMember / ConversationUserState / ChatInbox
```

- 每个 Stream consumer 通过独立 consumer group、checkpoint、pending reclaim、幂等事件键和 7 天 TTL DLQ 运行；**Chat 持久化成功后才 ACK**。
- `CircleGroupCreated` 与 `CircleGroupMembershipActivated` 可以乱序到达：名册事件在 conversation 未建好时保留 pending，不允许 ACK 后丢弃；重放完成后按 source event id 精确幂等。
- `CircleGroupArchived` 必须令绑定 Conversation 进入终态，删除所有成员的 `ConversationUserState`，并投递终态 realtime 事件；不留可发送、可见 Inbox 或可被重新投影复活的半终态。
- `Conversation.circleGroupId` 是一对一唯一索引，绑定事件会回写 `CircleGroup.conversationId`。`Circle.conversationId` 不承担任何群绑定或兼容读取职责。

### DK-10：成员容量、角色与治理权不跨域分叉

- `CircleGroup` 与绑定 Chat Conversation 都固定 **1000 active human members** 上限。成员激活命令在 circle-service 的真实事务内获取容量；容量满时在上游返回 `CIRCLE.USER.group_membership_full`，不能先让 Circle 成员 active 再由 Chat 异步拒绝。
- Circle role 到 Chat role 只有一个映射：`owner → owner`、`manager → admin`、`member → member`。Chat 不保留可独立编辑的圈群角色。
- 对 `circleGroupId` 非空的会话，Chat HTTP 成员/治理命令统一拒绝为 `CHAT.USER.circle_group_managed_by_circle`；App 隐藏转让群主、管理员、移除成员、解散等入口，并跳转 CircleGroup 权威治理页。
- 私建 Chat group 仍维持 chat 自治；是否圈群绑定必须由服务端存储字段判定，不能只依赖前端按钮隐藏。

## metadata / codegen 方案

### `social/circle/fields.yaml`

新增：

- `CircleGroup`
- `CircleGroupMember`
- `CircleGroupNotice`
- `CircleGroupType`
- `CircleGroupVisibility`
- `CircleGroupJoinPolicy`
- `OrganizationNodeType`

### `social/circle/service.yaml`

新增或扩展：

- `ListCircleGroups`
- `CreateCircleGroup`
- `ApplyJoinCircleGroup`
- `ApproveCircleGroupJoin`
- `RejectCircleGroupJoin`
- `ListCircleGroupFiles`
- `CreateCircleGroupFile`
- `ListCircleGroupNotices`

### `messages/conversation/*`

- 增加 `circleGroupId`
- chat-service 只负责 Conversation 生命周期与消息，并通过 durable projector 消费 CircleGroup 的权威成员事实
- `Conversation.circleGroupId` 建唯一索引；普通 `CreateConversation` 不接受 `circleId/circleGroupId` 作为用户可写字段
- 声明 `CircleGroupConversationProvisioned` 事件及 circle binding consumer

### `content/post/*`

- 增加 `groupId/nodeId`
- 支持节点内容聚合与最近活跃排序

## 字段演进与一次性回填

### 字段演进

- `Circle.conversationId` 不再代表群本身
- 群相关权限迁到 `CircleGroup / CircleGroupMember`

### 迁移 / 回填

- 记录 `Circle.conversationId` 迁为默认公共群的 `CircleGroup.conversationId`
- 原有群文件与群公告能力若落在圈级，迁移到默认公共群
- 无法准确归属的记录资料可先保留在圈级并逐步清理
- 所有 active CircleGroup 必须拥有唯一 `conversationId`，所有绑定 Conversation 必须填充同一 `circleGroupId`；回填校验通过后才能启用消费者。
- 禁止双读、双写、旧 `Circle.conversationId` fallback 或运行时兼容分支。

## feature flag、观测、SLO 验证与回滚方案

### feature flag

- 不新增用户可见 feature flag

### 观测

- `circle_group_create_count`
- `circle_group_apply_count`
- `circle_group_apply_decision_latency_ms`
- `circle_group_private_search_hit_count`
- `circle_group_file_upload_success_count`
- `circle_group_chat_projection_duration_ms`（按 created/membership_activated/left/removed/role_changed/archived 与 outcome）
- `circle_group_chat_projection_pending_age_ms`、`circle_group_chat_projection_dlq_total`
- `circle_group_chat_binding_lag_ms`、`circle_group_chat_roster_divergence_total`
- consumer group pending 数、reclaim 次数、DLQ 率和 source-event replay 率必须进入 health、Prometheus 与告警。

### SLO 验证

- 入群申请链路稳定
- 文件与公告能力不阻塞群主页
- 群内搜索与节点聚合符合性能约束
- CircleGroup 创建至 `conversationId` 回写 P95 ≤ 3 秒；成员 active/left/removed/role_changed 至 Chat 名册收敛 P95 ≤ 3 秒；超过 30 秒的 pending 或任意 DLQ 记录均为告警。

### 回滚

- 仅允许整版部署回退到已验证镜像；outbox、Stream 和幂等事件键保留，恢复后从 checkpoint 继续消费。
- 不允许回退到 `Circle.conversationId` 兼容读、同步 RPC、页面本地拼装或 Chat 直接写圈群成员的旧路径。

## TDD / ATDD 策略

- `T1_schema`
  - CircleGroup contract
  - conversation `circleGroupId`
  - content `groupId/nodeId`
- `T2_module_interaction`
  - 公共群 / 自建群列表
  - 申请入群
  - 私有群搜索
  - 群资料与公告
- `T3_cross_service_integration`
  - CircleGroup 与 chat
  - CircleGroup 与 content
  - 节点聚合
- `T4_user_journey`
  - 加入群组 -> 申请公共群
  - 圈内建私有群
  - 组织节点查看资料与交流

## plan slice 与 三层测试 证据矩阵映射

| Slice | 目标 | 主要证据 |
|---|---|---|
| `P1` | 冻结 CircleGroup 元数据与角色/审批模型 | `T1_schema` |
| `P2` | 完成 codegen 与 conversation/content 关联字段 | `T1_schema`, `T3_cross_service_integration` |
| `P3` | 落地公共群 / 自建群 / 私有群搜索流程 | `T2_module_interaction`, `T4_user_journey` |
| `P4` | 落地群资料、公告与节点内容聚合 | `T2_module_interaction`, `T3_cross_service_integration`, `T4_user_journey` |
| `P5` | CircleGroup 创建/绑定、成员与角色投影、归档终态、容量与治理边界 | `local_contract`, `api_integration`, `user_acceptance` |

## 未来演进

- 若未来协作编辑需求变强，再把群资料抽成更完整的文件协作域。
- 若大型群组需要更多公共群分区，再在 `CircleGroup` 上扩展排序与推荐，而不是重新建模。
- 若群治理需要审计流水，再补 `CircleGroupAuditLog`。
