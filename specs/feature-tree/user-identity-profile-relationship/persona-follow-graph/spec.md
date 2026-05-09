# L2 Journey: persona-follow-graph

## 节点定位

- `L1_capability`: `user-identity-profile-relationship`
- `L2_journey`: `persona-follow-graph`

该节点保留记录路径名 `persona-follow-graph`，但本次 PRD baseline 将其正式收口为“分身生命周期、公开身份、关系隔离与跨域透传”的统一 Journey。

产品文案可使用“分身 / 作者分身”，领域实体统一使用 `Persona / SubAccount`，对外展示统一使用 `ProfileSubject`。`作者分身` 不是 content/chat/assistant 的独立实体，而是 user 域 `Persona` 在创作与社交表面的产品化称呼。

## 背景与动机

当前分身能力存在四类结构性问题：

1. **管理入口断裂**：主入口连到 UI mock 的 `persona_management_page`，真实接了 Repository 的 `sub_account_management_page` 没有路由与导航闭环。
2. **领域边界不清**：`Persona / SubAccount / ProfileSubject / userId / subAccountId` 在用户域、内容域、聊天域和主页体验中混用，导致作者身份、管理身份和公开主页身份边界漂移。
3. **跨域只完成了字段预埋，没有完成闭环**：评论已有 `personaId`、聊天已有 `senderPersonaId`、邀请和圈子已有 `subAccountId`，但当前缺少“激活分身 -> 下游动作主体一致”的完整基线。
4. **特性树拆分不够清晰**：现有 `persona-follow-graph` 同时承载生命周期、公开身份、跨域透传和关系网络，缺少可直接进入 `/prd` 的 Scenario 颗粒度。

本次规格冻结的目标不是“新增一个作者子系统”，而是把分身能力明确收口为 user 域主模型，并把与 profile/content/chat/circle/assistant 的消费边界一次性讲清楚。

## 目标用户

- 需要把创作身份、职业身份、匿名表达、圈层运营彼此隔离的重度用户。
- 希望为不同内容语境维护不同作者形象，但不想维护多个登录账号的创作者。
- 只有一个默认身份、但未来可能逐步扩展为多分身的普通用户。
- 需要在不破坏外部隔离感知的前提下做审计、风控、恢复和灰度治理的平台团队。

## 核心旅程

分身完整旅程冻结为：

1. `OwnerAccount` 从“我的主页”或设置进入统一分身管理台。
2. 创建或切换某个分身，并决定其隔离等级、公开身份与资料继承方式。
3. 当前激活分身成为内容创作、评论、聊天、圈子、邀请、助手上下文的默认主体。
4. 外部用户只看到当前 `ProfileSubject`，无法从常规路径推断同一 owner 下的其它分身。
5. 关注关系、社交图谱、互动与通知都按分身隔离；平台内部仅在审计面可追踪 owner 与分身映射。

## 特性树拆分

本 Journey 本次冻结为 5 个 L3 Scenario：

| L3 Scenario | 负责的问题 | 归属域 | 说明 |
|---|---|---|---|
| `persona-management` | owner 视角的创建、切换、停用/删除保护、配额与管理入口 | `user` | 管理台，不承载公开主页壳层 |
| `persona-profile-subject-and-visibility` | 分身公开身份、资料继承/覆写、可见性与记录归因 | `user` | 提供 `ProfileSubject` 契约，供主页/内容消费 |
| `persona-context-propagation` | 激活分身向 content/chat/circle/assistant/invite/notification 透传 | `user` 主导，`content/chat/circle/assistant` 消费 | 保证“谁在发言/创作”始终一致 |
| `follow-relationship` | 关注/回关等关系写入 | `user` | 维持关系建立的分身归属 |
| `social-graph-read` | 粉丝/关注分页读取与图谱读取 | `user` | 维持按分身隔离的图谱读取 |

跨 Journey 的消费边界同时冻结如下：

| 依赖节点 | 本次角色 |
|---|---|
| `profile-homepage-redesign/owner-subaccount-homepage-unification` | 消费 `ProfileSubject` 契约，负责主页壳层与资料编辑体验，不再拥有分身生命周期真相源 |
| `discovery-content/publish-comment-reaction/comment-thread` | 消费 `personaId` / `ProfileSubject`，负责评论体验，不自建 persona 实体 |

## 领域划分

### user 域

唯一真相源。负责：

- `OwnerAccount / Persona(SubAccount)` 聚合
- 分身创建、切换、停用/删除保护、配额、主分身与激活态
- `SubAccountProfileView / SubAccountProfileMutation`
- 可见性、继承/覆写、审计映射
- 对外只暴露 `profileSubjectId / subAccountId`，不暴露 owner 映射

### content 域

消费 user 域分身身份。负责：

- 发帖、评论、互动活动的作者归属
- 内容侧作者展示与记录快照
- 基于当前激活分身或显式选择分身写入 `personaId / profileSubjectId`

禁止：

- 在 content 域自建“作者分身”主实体
- 直接维护 owner 与分身映射

### chat 域

消费 user 域分身身份。负责：

- `senderPersonaId`、会话发言主体、消息记录快照
- 基于激活分身决定谁在发消息、谁承接邀请与实时通话入口

### circle 域

消费 user 域分身身份。负责：

- 分身加入圈子、创建圈子、圈内身份展示
- 按分身维度隔离成员关系与圈层参与

### assistant 域

只消费 user 域分身上下文。负责：

- 读取当前激活分身与其资料/权限边界
- 在问答、工具调用、记忆写入中带上当前 `profileSubjectId`

禁止：

- 在 assistant runtime 内再维护第二套“persona”实体
- 把提示词层 `stack.persona` 误当成用户分身模型

## 业务对象、元数据与数据划分

本 Journey 严格按 DDD 的“领域 -> 业务对象 -> 契约 -> 存储”拆分，不允许在 UI 或下游域中再维护第二套分身/关系真相源。

| 领域 | 业务对象 | 元数据目录 | 主职责 | 存储/缓存 |
|---|---|---|---|---|
| `user` | `UserProfile` | `contracts/metadata/user/user_profile/` | owner 管理平面、Persona 聚合、`ProfileSubject`、公开资料、同步范围 | PostgreSQL + Redis |
| `user` | `Persona(SubAccount)` | `contracts/metadata/user/user_profile/` | 分身生命周期、active persona、公开身份继承/覆写 | PostgreSQL |
| `user` | `FollowEdge` | `contracts/metadata/user/follow_edge/` | follow/unfollow 写入、粉丝/关注图谱主数据源 | MongoDB |
| `user` | `BlockEdge` | `contracts/metadata/user/block_edge/` | block 门禁、图谱/消息/推荐过滤 | PostgreSQL + Redis |
| `content` | `Post / Comment` | `contracts/metadata/content/post/` | 以 `personaId / profileSubjectId` 记录作者归属与快照 | content 域自有存储 |
| `chat` | `Message` | `contracts/metadata/messages/conversation/` | 以 `senderPersonaId` 记录发送主体与消息快照 | chat 域自有存储 |
| `assistant` | 会话上下文 | `assistant` metadata + user request context | 消费当前 persona 上下文，不自建 persona 实体 | assistant 域自有存储 |

### 写侧与读侧边界

- `UserProfile + Persona` 负责 owner plane 与公开身份读模型 `ProfileSubject`。
- `FollowEdge` 负责社交图谱 write/read 的主对象，但计数冗余通过事件同步回 `UserProfile`。
- `BlockEdge` 是独立门禁对象，不与 `FollowEdge` 或 `Persona` 混成单一聚合。
- `content/chat/circle/assistant` 只保存 user 域下发的稳定身份标识与记录快照，不回写 owner 映射。

### metadata SSOT 边界

- 分身生命周期、公开身份、同步范围、`GetMeProfile / GetSubAccountProfile / CreateSubAccount / ActivateSubAccount`：
  - 真相源归 `contracts/metadata/user/user_profile/*`
- follow/unfollow、followers/following、`GetRelationship / GetRelationshipCapability`：
  - 真相源归 `contracts/metadata/user/follow_edge/*`
- block/unblock 与 block list：
  - 真相源归 `contracts/metadata/user/block_edge/*`
- 评论作者身份：
  - 真相源归 `contracts/metadata/content/post/*`，消费 user 域提供的 `personaId / profileSubjectId`
- 聊天发送者身份：
  - 真相源归 `contracts/metadata/messages/conversation/*`，消费 user 域提供的 `senderPersonaId`
- 若涉及 `path / operation / request_context / route / page_id`，必须按业务对象所在 metadata 目录定义，不允许在 App Repository、Router 或 assistant runtime 中再维护 override map。

## 数据生命周期与存储合同

- `Persona` 仍归属 `user_profile` 聚合，主存储在 user 域 PostgreSQL；热数据可走 Redis 缓存与失效。
- 每个 owner 默认且至少持有 1 个分身；同一时刻恰有 1 个 active persona。
- 分身创建时默认继承 owner 基线资料；仅覆写字段持久化到 persona 侧。
- 用户可见“删除分身”的领域语义分两类：
  - **无记录数据的空白分身**：允许物理删除。
  - **已有内容/评论/聊天/圈子/邀请记录的分身**：第一版按“停用/退役”处理，禁止继续作为新动作主体，但保留记录归因与内部审计链。
- 记录内容、评论、聊天消息与通知必须保留不可变作者快照，不因分身停用而改绑到 owner 或其它分身。
- 普通读接口不得返回 owner 与分身映射；审计与风控链路允许内部追踪。

## 范围

- 分身管理台：创建、切换、停用/删除保护、配额、低打扰入口。
- 分身公开身份：作者资料、公开主页主体、继承/覆写、可见性、记录归因。
- 分身上下文透传：发帖、评论、聊天、圈子、邀请、助手、通知。
- 分身关系隔离：关注、粉丝、分页读取、推荐上下文与展示边界。

## 不做什么（Out of Scope）

- 手机号、微信、Apple 登录绑定与认证流程本身。
- 主页壳层视觉、滚动吸顶、统一 Tab 结构与动效实现。
- 合规删除、物理清除与客服工单处置细则。
- 创作者商业化、品牌页或多团队协作后台。
- 在 content/chat/assistant 域派生新的 persona 主实体。

## 对标输入与吸收结论

| 对标 | 借鉴点 | 本次吸收 |
|---|---|---|
| 微信 | 登录容器与应用身份分离、强关系链路稳态 | 吸收 owner 管理平面与应用主体分离 |
| 小红书 | 创作者主页经营、评论身份感知、内容人格化 | 吸收作者分身作为公开创作身份 |
| 微博 | 公开社交、运营账号、粉丝关系传播 | 吸收分身作为关系网络独立主体 |

## 商业与非功能目标

### SLO

- 分身切换到新上下文后，端侧可见生效 P95 < 1s。
- 分身创建、激活、停用/删除保护主路径 P95 < 1.5s。
- 评论、聊天、圈子、邀请、助手链路不得出现身份串号；灰度期目标为 `0` 个 P0 串号事故。

### KPI

- 分身管理主路径完成率 > 95%。
- 激活分身后的首次关键动作绑定正确率 > 99.9%。
- 外部可见路径推断同 owner 多分身的缺陷数在灰度期为 `0`。

### 弱网与恢复

- 分身切换、follow 写入、图谱读取和评论/聊天提交在弱网超时后必须保留“当前 active persona 未变 / 动作主体未确认”的明确语义。
- persona 上下文未确认时，关键动作必须阻断或要求重试，不允许在弱网场景静默回退到 owner。
- follower/following 分页重试不得跨 persona 串页或把旧 persona 的缓存结果回放到新 persona 上下文。
- 通知和助手会话在恢复时必须带回最近一次稳定 active persona 快照。

### 并发与容量假设

- 单 owner 第一版默认上限 5 个 persona，但设计上不得把“只有 5 个”写死进下游对象模型。
- `FollowEdge`、`Comment`、`Message` 等高频对象需支持分身级高频切换后的并发写入，不得依赖 owner 级串行锁。
- follower/following 列表按社交图谱对象量级设计，默认支持创作者级粉丝规模与分页稳定读取。
- `UserProfile` 冗余计数、`FollowEdge` 主对象与下游作者快照允许最终一致修正，但不允许动作主体串号。

### 灰度与回滚

- 必须支持按功能面灰度：管理台、公开身份、跨域透传可分别开关。
- 任一开关关闭后，必须退回“单 active persona + 只读记录归因”安全基线。
- 发生串号、公开映射泄露或停用后记录归因丢失时，必须可单独回退相关开关。

## 验收重点

1. 分身的 owner 管理平面、公开身份契约和跨域透传边界清晰，不再在多个域重复定义。
2. “作者分身”被明确冻结为 user 域 `Persona/SubAccount` 的产品化表面，而非新建独立业务对象。
3. 主页、内容、聊天、圈子、助手都基于 `ProfileSubject / subAccountId / personaId` 消费，不直接暴露 owner 映射。
4. 特性树拆分可直接进入 `/prd`：生命周期、公开身份、跨域透传、关系写入、图谱读取的 Scenario 边界已经冻结。
