# L1 Domain Service：圈子与群组社区 (`circle-community`)

> 一句话定位：让用户围绕主题、组织或具体事物发现并加入圈子，在圈内参与内容、群组和成员协作。

## 1. 目标与用户价值

让用户以清晰的圈子、组织节点与群组边界完成发现、加入、内容参与和成员协作，并保持圈子主页、默认群与共享主页之间的唯一关系语义。

## 2. 领域边界

### 本领域拥有

- 拥有 `Circle`、`CircleMembership`、圈子分区、圈内活动、圈子文件以及圈子与群单元绑定关系的生命周期与写入决定权。
- 只能通过本领域公开 command 修改其拥有事实。

### 本领域不拥有

- 不拥有其他 L1 的事实；跨域协作必须使用对方公开 command、query、projection 或 event。
- 不复制 metadata 中的字段、path、错误码和 wire 语义。

### 上下游协作

- 上游：AppRoot Journey 与公开输入事实。
- 下游：直接 L2 能力以及协作 L1 的公开结果。
- 跨域写入：目标领域公开 command；禁止直写目标存储。
- 跨域读取：目标领域公开 query/projection。

## 3. Journey / Scenario 职责

- [`JNY-004 / SCN-001`](../spec.md#scn-001)
  - 本领域负责：在“写文字创建、可靠发布与结果回流”中，维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果。
  - 进入条件：`user-identity-profile-relationship` 已交付其公开结果。
  - 交付给下游的结果：维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果，供 `runtime` 继续处理。
  - 不负责：不拥有聊天消息、内容正文、主页或用户关系事实。
- [`JNY-004 / SCN-002`](../spec.md#scn-002)
  - 本领域负责：在“照片创建、像素编辑、原图可靠上传与发布回流”中，维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果。
  - 进入条件：`user-identity-profile-relationship` 已交付其公开结果。
  - 交付给下游的结果：维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果，供 `runtime` 继续处理。
  - 不负责：不拥有聊天消息、内容正文、主页或用户关系事实。
- [`JNY-004 / SCN-003`](../spec.md#scn-003)
  - 本领域负责：在“视频创建、转码处理、发布与结果回流”中，维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果。
  - 进入条件：`user-identity-profile-relationship` 已交付其公开结果。
  - 交付给下游的结果：维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果，供 `runtime` 继续处理。
  - 不负责：不拥有聊天消息、内容正文、主页或用户关系事实。
- [`JNY-005 / SCN-011`](../spec.md#scn-011)
  - 本领域负责：在“全局搜索查询与筛选”中，维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果。
  - 进入条件：`discovery-content` 已交付其公开结果。
  - 交付给下游的结果：维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果，供 `chat-conversation` 继续处理。
  - 不负责：不拥有聊天消息、内容正文、主页或用户关系事实。
- [`JNY-007 / SCN-013`](../spec.md#scn-013)
  - 本领域负责：在“私建群、圈子群、组织节点群与主页相关群入口”中，维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果。
  - 进入条件：`chat-conversation` 已交付其公开结果。
  - 交付给下游的结果：维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果，供 `shared-homepage-network` 继续处理。
  - 不负责：不拥有聊天消息、内容正文、主页或用户关系事实。
- [`JNY-008 / SCN-014`](../spec.md#scn-014)
  - 本领域负责：在“实体主页到圈子、组织节点、群单元与会话协作”中，维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果。
  - 进入条件：用户发起“实体主页到圈子、组织节点、群单元与会话协作”且身份、输入与权限前置成立。
  - 交付给下游的结果：维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果，供 `shared-homepage-network` 继续处理。
  - 不负责：不拥有聊天消息、内容正文、主页或用户关系事实。
- [`JNY-010 / SCN-023`](../spec.md#scn-023)
  - 本领域负责：在“对象对外分享分发”中，维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果。
  - 进入条件：`user-identity-profile-relationship` 已交付其公开结果。
  - 交付给下游的结果：维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果，供 `shared-homepage-network` 继续处理。
  - 不负责：不拥有聊天消息、内容正文、主页或用户关系事实。
- [`JNY-011 / SCN-027`](../spec.md#scn-027)
  - 本领域负责：在“附近同趣·结伴同行·线下局”中，维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果。
  - 进入条件：用户发起“附近同趣·结伴同行·线下局”且身份、输入与权限前置成立。
  - 交付给下游的结果：维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果，供 `recommendation-platform` 继续处理。
  - 不负责：不拥有聊天消息、内容正文、主页或用户关系事实。

## 4. 业务能力

- [`activity-member-governance`](./activity-member-governance/spec.md)：让圈子 owner 管理圈子生命周期与成员角色，并让成员以稳定分页读取圈内动态。
- [`circle-client-platform`](./circle-client-platform/spec.md)：统一圈子端侧领域模型、Repository 边界与页面状态
- [`circle-collaboration-tools`](./circle-collaboration-tools/spec.md)：以圈子或组织主页内的群为协作单元，统一交流、资料与公告
- [`circle-experience-redesign`](./circle-experience-redesign/spec.md)：按群组类型提供一致的发现、详情与协作入口
- [`circle-management-and-stats`](./circle-management-and-stats/spec.md)：为圈子治理与运营提供权限受控的处置、固定口径指标和可下钻运营视图。
- [`in-circle-recommendation-loop`](./in-circle-recommendation-loop/spec.md)：把圈内行为事实转为权限受控的候选排序，并将曝光与反馈归因回评估链路。

## 5. 领域要求

<a id="req-001"></a>
### REQ-001 circle community 领域边界验收

- 领域边界、上下游依赖、工程映射和服务治理清晰。
- 9 个业务对象（circle 含 section_config、membership、group、group_membership、file、post_placement、behavior_fact、search_item_view）按对象 packet 治理：state/receipt/outbox 同事务、命名迁移服务端 CAS、no-op receipt 持久化、If-Match 仅 group/file 快照覆盖两处（封闭清单）。
- Circle 聚合本体命令仅圈主/管理员（BOLA fail-closed）；展示位（pin/feature）唯一写入口是 CirclePostPlacement，feed 读模型由 placement outbox 投影回写。

<a id="req-002"></a>
### REQ-002 圈子发现聚合读模型契约

- ListCircleDiscoveryFeed 是圈子频道唯一聚合读接口；服务端完成 category、subCategory、scope、可见性和成员范围过滤，App 不得 listCircles 后逐圈拉取 feed。
- 默认 recommended 首屏只有一次 discovery-feed 请求；mine 仅由已认证 Persona 主动切换后按需请求，匿名 mine 不返回成员数据。
- CircleDiscoveryFeedPageSlice 与 CircleFeedPageSlice 均为 metadata 生成的强类型 Slice；排序、keyset cursor、同分 tie-breaker、placement 归属与必填字段可由 ContractGraph 验证。
- discovery feed 读缓存 TTL 为 60 秒，缓存键按 persona、scope、category、subCategory、sort、cursor 隔离；Circle、Membership、Post、Placement 变化会失效相关切片。
- 聚合查询具有索引/explain 与 10k/100k 数据集 P95 不超过 800ms 的证据，不得以单 HTTP 请求掩盖存储 N+1。

<a id="req-003"></a>
### REQ-003 全局入口层统一叫 群组

- 全局入口层统一叫 `群组`
- **群组发现者**：希望在一个统一入口里找到兴趣圈子、学校、班级、公司或部门等可加入的关系主页。
- **群组**：首页与搜索中的统一一级入口，表示所有“可加入、可沉淀关系”的主页集合。
- **内容**：群组层的公开表达单元，统一动作叫 `发布内容`。
- R1.1：首页一级入口与全局搜索一级筛选统一从 `圈子` 收口为 `群组`。
- R1.3：群组卡片使用统一信息骨架（名称、类型徽章、简介、成员数、最近活跃、是否已加入）。
- R1.4：群组分类与推荐继续由统一领域标签体系驱动，兼容现有 circle taxonomy 与推荐链路。
- R3.1：用户在群组内的统一动作叫 `发布内容`，不再全局统一叫“发帖”。
- R3.5：`口碑` 必须绑定 1 个主具体事物；`笔记 / 作品 / 提问` 可绑定也可不绑定具体事物。
- R4.4：群级统一使用 `群主 / 群管`。

## 6. 领域验收

<a id="dom-001"></a>
### DOM-001 circle community 领域边界验收

- 条件：本领域收到有效输入且前置领域事实成立。
- 可观察结果：领域边界、上下游依赖、工程映射和服务治理清晰。
- 9 个业务对象（circle 含 section_config、membership、group、group_membership、file、post_placement、behavior_fact、search_item_view）按对象 packet 治理：state/receipt/outbox 同事务、命名迁移服务端 CAS、no-op receipt 持久化、If-Match 仅 group/file 快照覆盖两处（封闭清单）。
- Circle 聚合本体命令仅圈主/管理员（BOLA fail-closed）
- 展示位（pin/feature）唯一写入口是 CirclePostPlacement，feed 读模型由 placement outbox 投影回写。
- 禁止结果：Circle↔MediaAsset 引用完整性由 tombstone 关系承载，不得声明不存在的 `MediaAssetDeleted` 消费者；hub 多圈发现 feed 只能使用有界并发扇出，聚合 API 变化必须先更新规格。

<a id="dom-002"></a>
### DOM-002 圈子发现聚合读模型契约

- 条件：本领域收到有效输入且前置领域事实成立。
- 可观察结果：ListCircleDiscoveryFeed 是圈子频道唯一聚合读接口
- 服务端完成 category、subCategory、scope、可见性和成员范围过滤，App 不得 listCircles 后逐圈拉取 feed。
- 默认 recommended 首屏只有一次 discovery-feed 请求
- mine 仅由已认证 Persona 主动切换后按需请求，匿名 mine 不返回成员数据。
- CircleDiscoveryFeedPageSlice 与 CircleFeedPageSlice 均为 metadata 生成的强类型 Slice
- 排序、keyset cursor、同分 tie-breaker、placement 归属与必填字段可由 ContractGraph 验证。
- discovery feed 读缓存 TTL 为 60 秒，缓存键按 persona、scope、category、subCategory、sort、cursor 隔离
- Circle、Membership、Post、Placement 变化会失效相关切片。
- 聚合查询具有索引/explain 与 10k/100k 数据集 P95 不超过 800ms 的证据，不得以单 HTTP 请求掩盖存储 N+1。
- 禁止结果：CircleDiscoveryFeed 只读 Circle、CircleMembership、Post、CirclePostPlacement 的投影，不加载 Circle 聚合或维护第二套成员/内容事实。
- GetCircleFeed 与 discovery feed 共用 CircleFeedItemView 的 placement/post 强类型表达
- 不得以 Post.toMap 或动态 wire map 补展示字段。

## 7. 工程归属

- App：`quwoquan_app/lib/ui/circle`、`quwoquan_app/lib/cloud/services/circle`
- Service：`quwoquan_service/services/circle-service`
- 测试：
  - `local_contract`：`quwoquan_service/services/circle-service/tests`
  - `api_integration`：`quwoquan_service/services/circle-service/tests`
  - `user_acceptance`：`quwoquan_ops/tests/acceptance/user_acceptance`

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 circle community 领域边界验收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：领域边界、上下游依赖、工程映射和服务治理清晰。
- 完成判定：`DOM-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 圈子发现聚合读模型契约

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：ListCircleDiscoveryFeed 是圈子频道唯一聚合读接口；服务端完成 category、subCategory、scope、可见性和成员范围过滤，App 不得 listCircles 后逐圈拉取 feed。
- 完成判定：`DOM-002` 对应行为满足且真实测试 `spec_ref` 有效
