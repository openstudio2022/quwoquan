# L1 Design：内容发现与发布 (`discovery-content`)

> 对应规格：[L1 spec](./spec.md)

## 1. 背景与设计目标

- 设计目标：发现流、推荐排序、内容发布、评论互动、媒体处理与帮读能力。

## 2. 领域模型与所有权

- authoritative ownership：拥有内容作品、发布状态、评论、互动、内容行为、内容投影和内容媒体处理结果的生命周期与写入决定权。
- write boundary：只能通过本领域公开 command 修改其拥有事实。
- 非本域对象：不拥有其他 L1 的事实；跨域协作必须使用对方公开 command、query、projection 或 event。
- 非本域对象：不复制 metadata 中的字段、path、错误码和 wire 语义。

## 3. 上下文边界与协作

- [`JNY-003 / SCN-007`](../spec.md#scn-007) — 在“从内容流打开详情”中，维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态。
- [`JNY-003 / SCN-009`](../spec.md#scn-009) — 在“内容详情跳转作者主页”中，维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态。
- [`JNY-003 / SCN-008`](../spec.md#scn-008) — 在“评论互动与回流”中，维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态。
- [`JNY-004 / SCN-001`](../spec.md#scn-001) — 在“写文字创建、可靠发布与结果回流”中，维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态。
- [`JNY-004 / SCN-002`](../spec.md#scn-002) — 在“照片创建、像素编辑、原图可靠上传与发布回流”中，维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态。
- [`JNY-004 / SCN-003`](../spec.md#scn-003) — 在“视频创建、转码处理、发布与结果回流”中，维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态。
- [`JNY-005 / SCN-011`](../spec.md#scn-011) — 在“全局搜索查询与筛选”中，维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态。
- [`JNY-006 / SCN-021`](../spec.md#scn-021) — 在“沉浸式媒体浏览器边缘滑动返回”中，维护内容、媒体、评论、互动和发现读模型，并交付可阅读、可发布或可恢复的内容终态。

## 4. 架构与数据流

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
- 工程边界由 spec 的“工程归属”声明；设计不复制具体实现文件。

## 5. 关键决策

<a id="dec-001"></a>
### DEC-001 内容对象由 content-service owner 写入，App 只消费生成契约与读模型
- 决策：内容对象由 content-service owner 写入，App 只消费生成契约与读模型。
- 理由：发现流、推荐排序、内容发布、评论互动、媒体处理与帮读能力。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 关联能力：[`content-display-consistency`](./content-display-consistency/spec.md)、[`content-service-cloud-production`](./content-service-cloud-production/spec.md)、[`content-service-contract-foundation`](./content-service-contract-foundation/spec.md)、[`content-type-framework`](./content-type-framework/spec.md)、[`dual-rail-discovery-redesign`](./dual-rail-discovery-redesign/spec.md)、[`exposure-governance`](./exposure-governance/spec.md)、[`feed-orchestration-recommendation`](./feed-orchestration-recommendation/spec.md)、[`media-processing-helper-read`](./media-processing-helper-read/spec.md)、[`object-homepage-coverage-scaling`](./object-homepage-coverage-scaling/spec.md)、[`publish-comment-reaction`](./publish-comment-reaction/spec.md)

## 6. 质量与运行约束

- 沿用 AppRoot 全局质量约束并保持 metadata/code/test 单轨。

## 7. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：按 canonical recovery action 重试、刷新或回滚到上一份已验证配置。
- 禁止 fallback：不得使用 Mock、旧 wire、双读双写或跨域直写伪造成功。
