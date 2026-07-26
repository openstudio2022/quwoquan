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

## 6. 领域验收

<a id="dom-001"></a>
### DOM-001 discovery content 领域边界验收

- 条件：本领域收到有效输入且前置领域事实成立。
- 可观察结果：领域边界、上下游依赖、工程映射和服务治理清晰。
- 禁止结果：不得绕过本领域公开 command/query/event 写入其拥有事实。

## 7. 工程归属

- App：`quwoquan_app/lib/ui/discovery`、`quwoquan_app/lib/ui/content`、`quwoquan_app/lib/cloud/services/content`
- Contracts：`quwoquan_service/services/content-service/contracts`
- Contracts（协作引用，不用于代码归属）：`quwoquan_service/services/integration-service/contracts`
- Service：`quwoquan_data`、`quwoquan_service/services/content-service`
- Service（协作引用，不用于代码归属）：`quwoquan_service/services/integration-service`
- 测试：
  - `local_contract`：`quwoquan_service/services/content-service/tests`
  - `api_integration`：`quwoquan_service/services/content-service/tests`
  - `user_acceptance`：`quwoquan_ops/tests/acceptance/user_acceptance`

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 discovery content 领域边界验收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：领域边界、上下游依赖、工程映射和服务治理清晰。
- 完成判定：`DOM-001` 对应行为满足且真实测试 `spec_ref` 有效
