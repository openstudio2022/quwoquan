# L1 Domain Service：圈子与群组社区 (`circle-community`)

> 一句话定位：让用户围绕主题、组织或具体事物加入稳定社区，并把内容与兴趣转化为由单一 Gathering 承载的真实共同活动。

## 1. 目标与用户价值

让用户以清晰的圈子、组织节点与群组边界完成发现、加入、内容参与和成员协作，并让创作者、Circle、Persona 或具备 authority 的 Entity Host 把内容与兴趣发起为可准入、可协作、可完成的 Gathering；1:1、多人和多日行程共享同一活动根。

## 2. 领域边界

### 本领域拥有

- 拥有 `Circle`、`CircleMembership`、圈子分区、圈子文件以及圈子与群单元绑定关系的生命周期与写入决定权。
- 拥有 `Gathering`、root-owned `GatheringParticipation`、`GatheringRevision`、`GatheringOutcome`、Host/Organizer authority binding、容量与准入、活动会话 binding state，以及由这些事实派生的公开详情与活动看板投影。
- 只能通过本领域公开 command 修改其拥有事实。

### 本领域不拥有

- 不拥有 `Conversation`、`ConversationMembership`、`Message`、`Announcement`、已读或文件索引，这些事实由 [`chat-conversation`](../chat-conversation/spec.md) 拥有；活动群聊是加入后的默认主场，但 Gathering 不迁入 Chat。
- 不拥有 `Post`、`MediaAsset` 或 `Report`，这些事实由 [`discovery-content`](../discovery-content/spec.md) 的 Content owner 拥有；本领域只保存 canonical reference 和必要安全处置 reference。
- 不拥有候选排序，Recommendation 只排序本领域签发的合格公开投影，不得写 Gathering、Participation、准入、容量或 Outcome。
- 不拥有 Persona Follow、mutual、Block 或账号治理事实；GatheringParticipation 不自动改变关系。
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
  - 本领域负责：从内容、C 位、主页或会话来源创建并发布 room-ready Gathering，维护 Host、root-owned Participation、Revision、容量/准入、生命周期、Outcome 与 room binding state，并签发公开详情和 Board 活动投影。
  - 进入条件：Host authority、来源引用、披露与风险义务可验证；Recommendation 只交付排序结果，不能直接产生 Participation。
  - 交付给下游的结果：公开可发现或受邀请的 Gathering、可区分准入结果、有效参与与 room access 投影、证据化 Outcome 及可供 Content 关联的 Experience reference。
  - 不负责：不拥有聊天消息/公告、内容正文/媒体/Report、推荐排序或 Persona 关系；加入与完成不自动产生 mutual。

- [`JNY-009 / SCN-034`](../spec.md#scn-034)
  - 本领域负责：提供 Circle 管理员与共享场景事实供 Assistant Placement 授权。
  - 进入条件：Circle 可见且主体拥有相应治理权限。
  - 交付给下游的结果：typed circle/admin reference。
  - 不负责：不保存 Skill policy。
- [`JNY-013 / SCN-030`](../spec.md#scn-030)
  - 本领域负责：为既有多人多日 Gathering 创建或挂接可选 Plan，并以 Organizer authority 提交当前 Plan Revision。
  - 进入条件：Gathering 已发布且操作者具有未撤销管理权。
  - 交付给下游的结果：活动群聊 Board 可消费的 current Plan reference。
  - 不负责：不创建长期公共 Trip 根，不把 Chat Message 或 Assistant proposal 当计划事实。
- [`JNY-013 / SCN-031`](../spec.md#scn-031)
  - 本领域负责：提交 Plan Revision、计算受影响 Participation，并发布可供 Chat/Assistant 去重提醒的变化事实。
  - 进入条件：expected revision 与 Organizer authority 有效。
  - 交付给下游的结果：新的 current Plan reference 与 typed change event。
  - 不负责：不拥有通知频控、消息或 Provider 事实。
- [`JNY-013 / SCN-032`](../spec.md#scn-032)
  - 本领域负责：把用户确认的 Experience/Post reference 关联到 Gathering/Plan item，并签发 Timeline/Map 所需 canonical reference。
  - 进入条件：Gathering、Plan item 与引用对象对调用方可见。
  - 交付给下游的结果：可重建的 Experience/Timeline/Map 投影来源。
  - 不负责：不复制 Post/Media，不保存连续位置。
- [`JNY-013 / SCN-033`](../spec.md#scn-033)
  - 本领域负责：承载多人多日 Gathering、有效 Participation、Plan/Experience 关联与 Outcome，并为旅行后回顾提供 canonical activity reference。
  - 进入条件：分享和参与者可见范围有效。
  - 交付给下游的结果：Gathering/Outcome 公开 command receipt 与隐私裁剪后的引用。
  - 不负责：不拥有 Content 分享结果、Chat 消息或 Follow；可选旅行能力不创建第二活动根。

## 4. 业务能力

- [`activity-member-governance`](./activity-member-governance/spec.md)：让圈子 owner 管理圈子生命周期与成员角色，并让成员以稳定分页读取圈内动态。
- [`circle-client-platform`](./circle-client-platform/spec.md)：统一圈子端侧领域模型、Repository 边界与页面状态
- [`circle-collaboration-tools`](./circle-collaboration-tools/spec.md)：以圈子或组织主页内的群为协作单元，统一交流、资料与公告
- [`circle-experience-redesign`](./circle-experience-redesign/spec.md)：按群组类型提供一致的发现、详情与协作入口
- [`circle-management-and-stats`](./circle-management-and-stats/spec.md)：为圈子治理与运营提供权限受控的处置、固定口径指标和可下钻运营视图。
- [`gathering-coordination`](./gathering-coordination/spec.md)：让内容或兴趣成为可公开发现、可准入、可在活动群聊与看板协作并形成 Outcome 的单一 Gathering。
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

<a id="req-004"></a>
### REQ-004 Gathering 聚合、参与和跨域 owner 单轨

- 创作者、Circle、Persona 与具备 authority 的 Entity Host 发起的 1:1、多人和多日活动必须复用同一 Gathering；`Activity`、`Meet`、`Trip` 只作为文案或体验组合，不形成第二活动聚合。
- 每位 Persona 在每个 Gathering 下只有一条 root-owned GatheringParticipation；公开加入、申请与邀请是不同准入来源，必须使用语义明确的 owner operation，禁止通用状态写。
- GatheringRevision 冻结重大承诺变更，Outcome 与 lifecycle 分离；容量已满、进行中和 admission closure 均从 owner 事实派生，不得成为可漂移的第二生命周期。
- Host/Organizer 管理权与 Participation 分离；不参加的 organizer 不占席位，真实参加时必须拥有独立有效 Participation。
- Chat 只拥有活动群聊访问与消息事实，Recommendation 只排序，Content 只拥有 Post/Media/Report；所有字段、operation、route、surface、event、error 与 metric 只引用所属 canonical contracts。

<a id="req-005"></a>
### REQ-005 Gathering 安全、权利与关系独立

- 发布、增加 organizer 与 Host 转移必须验证 owner authority 和风险义务；依赖不可用或证据无效时 fail-closed，不信任客户端角色结论。
- 参与者在加入前可查看允许披露的 Host、时间地点范围、容量、费用/要求、风险与取消规则；精确地点、参与名单、附件和活动群聊按 canonical disclosure 与 Participation 状态开放。
- 开场前取消、开场后提前结束、安全终止与完成必须可区分；Block、移除或安全退出触发 room、计划、文件和精确地点访问收敛，并保留裁剪后的通知、举报与申诉入口。
- GatheringParticipation、CircleMembership、ConversationMembership 和 Persona 关系相互独立；加入、到场、完成或共同发布均不得自动建立 mutual。

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

<a id="dom-003"></a>
### DOM-003 Gathering 所有权、生命周期与跨域投影

- 条件：Host 从内容、Circle、Persona、Entity 或 C 位创建并发布 Gathering，参与者经开放加入、申请或邀请响应进入活动协作。
- 可观察结果：Gathering、root-owned Participation、Revision、Outcome 与 room binding state 只由 Circle command 改变；Chat membership 只是访问投影，Recommendation 只排序，Content 只接收 canonical activity reference。
- 可观察结果：并发准入不超员，Organizer 与 Participation 分离，重大变更逐人确认，取消/提前结束/安全终止/完成可区分，occurred 具有独立证据，退出与撤权最终收敛。
- 禁止结果：不得用裸建群、ConversationMembership、Feed card、Assistant artifact、旅行 Trip 或 App cache 代替 Gathering 真相；不得因参与自动建立 mutual。

## 7. 工程归属

- App：`quwoquan_app/lib/service/circle_service`
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

<a id="open-003"></a>
### OPEN-003 Gathering 目标所有权与跨域闭环尚未准出

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺从旧 Gathering 五态与名单/Chat 绑定收敛到 root-owned GatheringParticipation、Revision、Outcome、Host authority、正交准入/容量、room+board、证据化完成、安全撤权及不自动 mutual 的 contracts 与验收证据。
- 完成判定：`DOM-003` 由对象级 local_contract、真实 api_integration 与跨域 user_acceptance 直接覆盖；四场景复用同一合同且无超员、半加入、未授权 room access、第二活动根或跨域直写。
- 依赖：[`gathering-coordination`](./gathering-coordination/spec.md) 的阻断 OPEN，以及 Circle/Chat/Content/Recommendation/User owner contracts 后续准入。
