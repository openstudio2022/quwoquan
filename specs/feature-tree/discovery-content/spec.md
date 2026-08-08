# L1 Domain Service：内容发现与发布 (`discovery-content`)

> 一句话定位：发现流、推荐排序、内容发布、评论互动、媒体处理与帮读能力。

## 1. 目标与用户价值

发现流、推荐排序、内容发布、评论互动、媒体处理与帮读能力。

## 2. 领域边界

### 本领域拥有

- 拥有内容作品、发布状态、评论、互动、内容行为、内容投影和内容媒体处理结果的生命周期与写入决定权。
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

- [`JNY-003 / SCN-007`](../spec.md#scn-007)
  - 本领域负责：在“从内容流打开详情”中，维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态。
  - 进入条件：用户发起“从内容流打开详情”且身份、输入与权限前置成立。
  - 交付给下游的结果：维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态，形成该场景中本领域负责的终态。
  - 不负责：不拥有账号关系、圈子成员、主页身份或推荐模型版本。
- [`JNY-003 / SCN-009`](../spec.md#scn-009)
  - 本领域负责：在“内容详情跳转作者主页”中，维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态。
  - 进入条件：用户发起“内容详情跳转作者主页”且身份、输入与权限前置成立。
  - 交付给下游的结果：维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态，供 `user-identity-profile-relationship` 继续处理。
  - 不负责：不拥有账号关系、圈子成员、主页身份或推荐模型版本。
- [`JNY-003 / SCN-008`](../spec.md#scn-008)
  - 本领域负责：在“评论互动与回流”中，维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态。
  - 进入条件：用户发起“评论互动与回流”且身份、输入与权限前置成立。
  - 交付给下游的结果：维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态，供 `chat-conversation` 继续处理。
  - 不负责：不拥有账号关系、圈子成员、主页身份或推荐模型版本。
- [`JNY-004 / SCN-001`](../spec.md#scn-001)
  - 本领域负责：在“写文字创建、可靠发布与结果回流”中，维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态。
  - 进入条件：用户发起“写文字创建、可靠发布与结果回流”且身份、输入与权限前置成立。
  - 交付给下游的结果：维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态，供 `user-identity-profile-relationship` 继续处理。
  - 不负责：不拥有账号关系、圈子成员、主页身份或推荐模型版本。
- [`JNY-004 / SCN-002`](../spec.md#scn-002)
  - 本领域负责：在“照片创建、像素编辑、原图可靠上传与发布回流”中，维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态。
  - 进入条件：用户发起“照片创建、像素编辑、原图可靠上传与发布回流”且身份、输入与权限前置成立。
  - 交付给下游的结果：维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态，供 `user-identity-profile-relationship` 继续处理。
  - 不负责：不拥有账号关系、圈子成员、主页身份或推荐模型版本。
- [`JNY-004 / SCN-003`](../spec.md#scn-003)
  - 本领域负责：在“视频创建、转码处理、发布与结果回流”中，维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态。
  - 进入条件：用户发起“视频创建、转码处理、发布与结果回流”且身份、输入与权限前置成立。
  - 交付给下游的结果：维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态，供 `user-identity-profile-relationship` 继续处理。
  - 不负责：不拥有账号关系、圈子成员、主页身份或推荐模型版本。
- [`JNY-005 / SCN-011`](../spec.md#scn-011)
  - 本领域负责：在“全局搜索查询与筛选”中，维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态。
  - 进入条件：`global-search-experience` 已交付其公开结果。
  - 交付给下游的结果：维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态，供 `circle-community` 继续处理。
  - 不负责：不拥有账号关系、圈子成员、主页身份或推荐模型版本。
- [`JNY-006 / SCN-021`](../spec.md#scn-021)
  - 本领域负责：在“沉浸式媒体浏览器边缘滑动返回”中，维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态。
  - 进入条件：`runtime` 已交付其公开结果。
  - 交付给下游的结果：维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态，形成该场景中本领域负责的终态。
  - 不负责：不拥有账号关系、圈子成员、主页身份或推荐模型版本。
- [`JNY-008 / SCN-014`](../spec.md#scn-014)
  - 本领域负责：在“实体主页到圈子、组织节点、群单元与会话协作”中，维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态。
  - 进入条件：`chat-conversation` 已交付其公开结果。
  - 交付给下游的结果：维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态，形成该场景中本领域负责的终态。
  - 不负责：不拥有账号关系、圈子成员、主页身份或推荐模型版本。
- [`JNY-009 / SCN-017`](../spec.md#scn-017)
  - 本领域负责：在“内容与页面上下文感知问答”中，维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态。
  - 进入条件：`runtime` 已交付其公开结果。
  - 交付给下游的结果：维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态，供 `user-identity-profile-relationship` 继续处理。
  - 不负责：不拥有账号关系、圈子成员、主页身份或推荐模型版本。
- [`JNY-009 / SCN-019`](../spec.md#scn-019)
  - 本领域负责：在“搜索 handoff 与统一 grounding”中，维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态。
  - 进入条件：`global-search-experience` 已交付其公开结果。
  - 交付给下游的结果：维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态，供 `chat-conversation` 继续处理。
  - 不负责：不拥有账号关系、圈子成员、主页身份或推荐模型版本。
- [`JNY-010 / SCN-023`](../spec.md#scn-023)
  - 本领域负责：在“对象对外分享分发”中，维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态。
  - 进入条件：`product-ops-growth` 已交付其公开结果。
  - 交付给下游的结果：维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态，供 `user-identity-profile-relationship` 继续处理。
  - 不负责：不拥有账号关系、圈子成员、主页身份或推荐模型版本。
- [`JNY-010 / SCN-025`](../spec.md#scn-025)
  - 本领域负责：在“公开 Web SEO 与安装转化”中，维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态。
  - 进入条件：`runtime` 已交付其公开结果。
  - 交付给下游的结果：维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态，形成该场景中本领域负责的终态。
  - 不负责：不拥有账号关系、圈子成员、主页身份或推荐模型版本。
- [`JNY-012 / SCN-010`](../spec.md#scn-010)
  - 本领域负责：在“我的主页转发互动双向历史”中，维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态。
  - 进入条件：`user-identity-profile-relationship` 已交付其公开结果。
  - 交付给下游的结果：维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态，形成该场景中本领域负责的终态。
  - 不负责：不拥有账号关系、圈子成员、主页身份或推荐模型版本。

- [`JNY-013 / SCN-030`](../spec.md#scn-030)
  - 本领域负责：提供可见 Post/Media/收藏内容 Reader，供计划引用真实内容事实。
  - 进入条件：viewer 权限和对象可见性有效。
  - 交付给下游的结果：typed content/media reference 与来源事实。
  - 不负责：不拥有 GatheringPlan 或复制计划。
- [`JNY-013 / SCN-032`](../spec.md#scn-032)
  - 本领域负责：保持 Post/MediaAsset 真相并接受 Circle Experience reference 的采用归因读取，不由 Circle 修改内容正文。
  - 进入条件：引用对象存在且可见。
  - 交付给下游的结果：可解析引用、媒体状态与采用反馈。
  - 不负责：不决定 Experience reference 的计划归属。
- [`JNY-013 / SCN-033`](../spec.md#scn-033)
  - 本领域负责：接收经确认的 LocalPostDraft/发布 command，并承载旅行分享内容。
  - 进入条件：用户确认、来源快照与媒体引用有效。
  - 交付给下游的结果：草稿或已发布 Post receipt。
  - 不负责：不自动发布，不保存 Gathering/GatheringPlan 快照正文副本。

## 4. 业务能力

- [`content-display-consistency`](./content-display-consistency/spec.md)：统一文章、圈子流、沉浸式浏览器与作者主页之间的展示和状态交接
- [`content-service-cloud-production`](./content-service-cloud-production/spec.md)：让经数据生产和审核的文章、图片、视频及主页内容以不可变发布物进入 content-service，并由 App 通过正式远端契约读取。
- [`content-service-contract-foundation`](./content-service-contract-foundation/spec.md)：内容服务端云一体化契约基础层。将业务对象（Post 及其子类型）的所有横切关注点——接口契约、存储、领域模型、错误码、行为采集与推荐特征、隐私安全、端侧可配置化、三层测试契约——统一纳入以业务对象为中心的元数据目录，并通过 codegen 工具链确保端云双侧代码从同一 YAML 真相源派生，消除人工协调。
- [`content-type-framework`](./content-type-framework/spec.md)：**定位**：content_feed 场景下对四种媒体类型（微趣 micro、图片 image、视频 video、文章 article）的通用内容模型与按类型扩展的约定，不拆表、不拆场景。
- [`dual-rail-discovery-redesign`](./dual-rail-discovery-redesign/spec.md)：让用户在“作品”沉浸轨与“点滴”社交轨之间按浏览意图切换，而不是先按图片、视频或文章格式选择入口。
- [`exposure-governance`](./exposure-governance/spec.md)：推荐曝光治理的商用成熟度能力：served/impressed 双轨、疲劳、频控、动态预算、复活、活跃度自适应与曝光健康。
- [`feed-orchestration-recommendation`](./feed-orchestration-recommendation/spec.md)：发现流推荐编排的端云行为、流式体验、交集解释、曝光治理集成边界与推荐 SLO 基线。
- [`media-processing-helper-read`](./media-processing-helper-read/spec.md)：图片/视频从上传完成事实到 ready/rejected 终态、归一化公开切片与可预览读取的商用闭环。
- [`object-homepage-coverage-scaling`](./object-homepage-coverage-scaling/spec.md)：可复用实体主页与多载体内容供给、发布和环境消费闭环。
- [`publish-comment-reaction`](./publish-comment-reaction/spec.md)：publish-comment-reaction 能力级 SIT，验证文字/照片发布、图片本地编辑、评论、回复、反应计数、行为上报和端云状态协同。

## 5. 领域要求

<a id="req-001"></a>
### REQ-001 discovery content 领域边界验收

- 领域边界、上下游依赖、工程映射和服务治理清晰。

<a id="req-002"></a>
### REQ-002 为端侧首页与内容详情提供统一发现流与内容读取能力，支持按用户画像和行为进行推荐排序

- 为端侧首页与内容详情提供统一发现流与内容读取能力，支持按用户画像和行为进行推荐排序。
- **四类内容**（文章、微趣、美图、视频）统一支持全量用户反馈：关注作者、赞、收藏、转发、评论，以及不感兴趣、不想看此作者、不想看此类内容、举报；反馈端云契约与推荐过滤逻辑见 `feed-orchestration-recommendation/design.md`。
- 端侧 UI 必须遵从语义 token（`AppSpacing`/`AppColors`/`AppTypography`），禁止硬编码视觉值。
- 发现流与内容列表响应统一 `items` + `nextCursor`。
- 行为事件必须可被 `product-ops` 消费，且可关联 `traceId/requestId/pageId`。

<a id="req-003"></a>
### REQ-003 标签体系以闭环效力而非定义规模计量

- 标签的商用价值由五级基线度量，唯一口径是 `python3 quwoquan_data/scripts/cli.py governance taxonomy closure-scorecard`：
 `defined`（节点存在）、`collectible`（声明 `collectionChannel`）、`published`（canonical `publish/posts/**` 的 `tagRefs` 真实使用）、
 `consumed`（声明 `consumedBy`）、`verified`（前述采集、供给、消费三者同时成立）。
- 五级的语义边界由 `quwoquan_data/schema/governance/_definition.schema.json` 拥有：该 schema 已声明
 「没有采集通道的标签是孤儿」「采集到但无人消费的标签同样是孤儿」。计量脚本读取该 schema 的枚举，
 不得在脚本或规格内复制第二份采集通道与消费方取值。
- `verified` 取三者交集而非加权分：有采集无消费是白采，有消费无供给是空转，任一级断开该标签对用户即为零价值，不可互相补偿。
- 规模指标（`quwoquan_data/scripts/cli.py governance taxonomy stats`）只描述定义广度，不得用于论证标签体系可用。
- canonical 发布物引用的 `tagRef` 必须在 taxonomy 中存在；悬空引用既不进召回也不进搜索筛选，按缺陷处理。

<a id="req-004"></a>
### REQ-004 声明采集通道即必须存在生产写入点

- 标签声明 `collectionChannel` 只表达意图；该通道必须有 App 生产代码真的去调用其解析器，标签才会被写到内容或用户上。
- 每个被标签使用的通道必须在 `quwoquan_ops/gate/verify_tag_collection_wiring.py` 的 `PRODUCERS` 登记生产写入点与责任说明；
 新增通道而不登记即阻断。
- 「已接通」的唯一判定是生产符号在 `quwoquan_app/lib/**` 中于定义文件之外被非注释引用；仅被测试树引用不算接通。
- 存量未接通通道进 `UNWIRED_BASELINE` 且只减不增：接通后必须同步删除基线条目，禁止基线退化为永久豁免。

<a id="req-005"></a>
### REQ-005 扩定义受孤儿棘轮约束，先接管道后扩标签

- 无采集通道的标签数由 `closure_scorecard.ORPHAN_NO_CHANNEL_CEILING` 封顶且只减不增：
 新增零采集声明的叶子会抬高该数并被 `closure-scorecard --gate` 阻断。
- 棘轮双向收紧：接通一批后实测值低于上限时同样阻断，必须同步下调上限；留出余量等于允许悄悄退回。
- 商用判定（`verified > 0`）取决于内容供给，不作为门禁条件；门禁只挡确定性退化：孤儿变多、悬空 `tagRef`、取值漂出 schema 枚举。
- 新增语义轴的叶子必须在提交时即声明 `collectionChannel` 与 `consumedBy`，且该通道已在 `PRODUCERS` 登记；
 「先建定义、后补通道」不成立，它正是当前 1732 个孤儿的成因。

## 6. 领域验收

<a id="dom-001"></a>
### DOM-001 discovery content 领域边界验收

- 条件：本领域收到有效输入且前置领域事实成立。
- 可观察结果：领域边界、上下游依赖、工程映射和服务治理清晰。
- 禁止结果：不得绕过本领域公开 command/query/event 写入其拥有事实。

<a id="dom-002"></a>
### DOM-002 标签闭环五级基线可复跑且自洽

- 条件：taxonomy 与 canonical 发布物均可读。
- 可观察结果：`closure-scorecard` 输出五级计数、孤儿三分类、按语义轴下钻与商用判定；
 `verified` 不超过 `collectible`、`published`、`consumed` 中的任一项；各语义轴 `defined` 之和等于总数。
- 禁止结果：不得出现 schema 枚举之外的 `collectionChannel` / `consumedBy` 取值；不得存在悬空 `tagRef`。

<a id="dom-003"></a>
### DOM-003 采集通道接线断点可枚举且只减不增

- 条件：taxonomy 与 App 生产代码均可读。
- 可观察结果：`verify_tag_collection_wiring.py` 列出每条在用通道的覆盖标签数与接线状态，
 并对未登记通道、基线外未接通、基线内已接通三类偏离全部阻断。
- 禁止结果：不得以文档注释提及生产符号冒充接通；不得在未接通的前提下扩大基线。

<a id="dom-004"></a>
### DOM-004 孤儿棘轮对增减双向阻断

- 条件：taxonomy 可读且 `closure-scorecard --gate` 可执行。
- 可观察结果：无采集通道的标签数高于上限时报「新增了没有采集通道的标签定义」并非零退出；
 低于上限时报「请把 `ORPHAN_NO_CHANNEL_CEILING` 同步下调」并非零退出；等于上限时通过。
- 禁止结果：不得因商用判定仍为 `BLOCK` 而放行孤儿增长；不得把上限调高来容纳新增定义。

## 7. 工程归属

- App：`quwoquan_app/lib/service/content_service`
- Contracts：`quwoquan_service/services/content-service/contracts`
- Contracts（协作引用，不用于代码归属）：`quwoquan_service/services/integration-service/contracts`
- Service：`quwoquan_data`、`quwoquan_service/services/content-service`
- Service（协作引用，不用于代码归属）：`quwoquan_service/services/integration-service`
- 测试：
  - `local_contract`：`quwoquan_service/services/content-service/tests`、`quwoquan_app/test/local_contract/journeys/viewer_profile_state_sync`
  - `api_integration`：`quwoquan_service/services/content-service/tests`
  - `user_acceptance`：`quwoquan_ops/tests/acceptance/user_acceptance`、`quwoquan_app/test/user_acceptance/journeys/home_recommendation`、`quwoquan_app/test/user_acceptance/journeys/home_video_playback`

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 discovery content 领域边界验收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：领域边界、上下游依赖、工程映射和服务治理清晰。
- 完成判定：`DOM-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 标签闭环 verified 为 0，标签体系尚不支撑商用

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前 `closure-scorecard` 实测 `defined=5891 / collectible=4159 / published=5 / consumed=4159 / verified=0`，
 判定 `BLOCK`。尚无任何标签同时具备采集通道、真实内容供给与消费方。
 其中 `consumed` 的 4159 项全部落在「有消费声明但零内容供给」——`Topic/地理` 4122 个节点声明了 `poi` 采集与
 `recall`/`intersection` 消费，但 `Post.geoTagRef` 在端侧没有生产写入点，供给恒为空（断点证据见 `OPEN-003`）。
 canonical 发布物只有 3 篇、合计使用 5 个 `tagRef`，因此扩充标签定义不会转化为可用信号，只会放大空转。
- 完成判定：`DOM-002` 可复跑，且 `verified > 0`（至少一条语义轴打通采集、供给、消费三级）

<a id="open-003"></a>
### OPEN-003 三条在用采集通道全部没有生产写入点

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前 taxonomy 只使用三条采集通道，三条都未接通，合计 4159 个标签永远不会被打上：
 `poi` 覆盖 4059 个 `Topic/地理` 节点，`GeoTagRefResolver` 已实现却只在测试树被调用，
 发布确认页选中 POI 时仅写 `locationPoi`，`Post.geoTagRef` 恒空，
 导致 `decodeDeclaredVisit` 的区域级同地交集分支从未被触发；
 `exif` 覆盖 40 个摄影节点，`extractMediaCaptureMetadata` 无任何生产调用点，
 `PublishSettings.captureMetadata` 恒为 `empty`，`captureDerivedTagRefs` 恒为空列表；
 `creator_chip` 覆盖 60 个节点，创作页尚无打标 chip，`tagRefs` 只能由正文内联 mention 填充。
 断点已由 `UNWIRED_BASELINE` 固化，接通一条即须删除一条。
- 完成判定：`DOM-003` 通过且 `UNWIRED_BASELINE` 为空
