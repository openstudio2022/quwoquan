# L3 Story：comment-thread（Comment / ContentReaction 商用对象闭环） (`comment-thread`)

> 所属能力：[`publish-comment-reaction`](../spec.md)
>
> Journey / Scenario：[`JNY-003 / SCN-008`](../../../spec.md#scn-008)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，我希望Comment 与 ContentReaction 经对象专属 Facade、generated client、Mongo/outbox、治理投影和统一 Runtime execution path 完成可排序、可治理、可追溯的二层评论闭环，从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- typed Comment command/query、reply Slice、ContentReaction 与服务端能力投影。
- production Remote-only、alpha fixture 隔离、严格 decoder 与 RuntimeFailure。
- hot/latest 两档服务端 keyset、pinned-first、hotScore、CAS、幂等、outbox、计数和投影收敛。
- hidden/restore/tombstoned 治理、创建频控、Post 删除级联与审计事实。
- authorIpLocation、authorLiked、viewerRelation、拉黑过滤与批量读投影。
- Feed、沉浸式、文章、个人互动、通知深链、举报与登录续接。
- ListComments 返回一级评论、replyPreview、replyNextCursor。
- ListCommentReplies 按 cursor 和 limit 独立展开二级回复。
- reply_preview_count 默认 1、reply_expand_page_size 默认 10，支持 App Config 覆盖。
- CreateComment 支持 replyToCommentId 并规范化 parentCommentId。

### Out of Scope

- recommended/latest/most_liked 三档排序及任何兼容参数。
- 评论搜索、翻译、语音评论、视频附件、AI 摘要与 ML rerank。
- same_circle 关系标签、个性化热评和 hotScore 时间衰减。
- generic Repository、动态 Map DTO、失败回退 Mock 与 PostService 评论第二通路。
- 三级及以上嵌套回复。
- 回复全文搜索。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 平铺内容入口复用 typed Comment surface

- 平铺内容必须复用同一 typed Comment surface；评论加载失败不得阻断正文浏览，刷新或追加失败不得清空已确认内容。

<a id="req-002"></a>
### REQ-002 沉浸式内容打开和关闭后上下文可恢复

- 图片、视频和文章在关闭评论 surface 后必须恢复原图片索引、播放进度或阅读位置。

<a id="req-003"></a>
### REQ-003 登录续接完整保留 typed 评论草稿

- 登录续接必须保留正文、附件、mentions、宿主内容和回复目标；目标不一致时拒绝误提交。

<a id="req-004"></a>
### REQ-004 回复摘要与分页是服务端 typed 投影

- 一级评论查询必须返回 typed 回复摘要和游标，展开操作只能读取独立的二级回复分页。

<a id="req-005"></a>
### REQ-005 一级评论按 hot/latest 服务端稳定排序

- 一级评论只支持 `hot` 与 `latest` 两档服务端稳定排序；App 不得本地重排。

<a id="req-006"></a>
### REQ-006 ContentReaction 三态互斥并由列表投影恢复

- `like`、`dislike` 与 `none` 必须互斥，计数和当前用户状态由服务端投影返回并可在重入后恢复。

<a id="req-007"></a>
### REQ-007 图片附件和 mentions 端云全程强类型

- 图片附件只能引用真实 `MediaAsset`，mentions 必须使用强类型对象并在创建后按原语义回读。

<a id="req-008"></a>
### REQ-008 四环境数据源和三层证据无 Mock 污染

- alpha fixture 必须与 beta/gamma/prod Remote 物理隔离；发布证据必须绑定同一 commit 与 ContractGraph 摘要。

<a id="req-009"></a>
### REQ-009 个人评论与互动深链使用 typed Facet

- 个人评论与互动列表必须使用 typed Facet，并以 `postId/commentId/parentCommentId` 返回原评论位置。

<a id="req-010"></a>
### REQ-010 Comment contract 严格解码且无旧 DTO

- 未知枚举、错误字段类型或缺失必填字段必须 fail-closed；旧 Comment DTO 与动态附件 Map 不可达。

<a id="req-011"></a>
### REQ-011 权限与可观测字段来自同一商用投影

- 评论动作权限和遥测维度必须来自同一服务端能力投影，端侧不得自行推断可执行动作。

<a id="req-012"></a>
### REQ-012 置顶与删除以服务端内部 CAS 执行命名意图

- 置顶、取消置顶和删除必须以命名命令执行服务端 CAS；冲突时返回结构化失败且不得覆盖新版本。

## 4. 契约引用

- operation：`CreateComment`、`ListComments`、`ListCommentReplies`、`ListCommentsByAuthor`、`ListCommentsForPostAuthor`、`PinComment`、`UnpinComment`、`DeleteComment`
- reaction operation：`ReactToComment`
- comment contract：`quwoquan_service/services/content-service/contracts/content/comment/operations.yaml`
- reaction contract：`quwoquan_service/services/content-service/contracts/content/content_reaction/operations.yaml`
- media contract：`quwoquan_service/services/content-service/contracts/media/media_asset/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 平铺内容入口复用 typed Comment surface

- GIVEN 用户打开可评论的平铺内容详情
- WHEN 用户从评论 CTA 进入评论 section
- THEN 页面只消费 ContentCommentFacet 与 ContentCommentListItem。
- THEN 空态、加载失败和重试不影响正文浏览。
- THEN 首屏无数据失败使用无卡片外框的区块错误空态
- AND 已有评论刷新失败保留旧数据
- AND 追加失败只出现在列表尾部。
- THEN 首屏阻塞失败时标题不展示未经确认的“共 0 条评论”。

<a id="gwt-002"></a>
### GWT-002 沉浸式内容打开和关闭后上下文可恢复

- GIVEN 用户正在浏览图片、视频或文章沉浸式内容
- WHEN 用户打开评论、执行互动并关闭评论
- THEN 评论 surface 不复制 Repository 或 Comment 状态机。
- THEN 图片索引、视频进度或文章页码保持。

<a id="gwt-003"></a>
### GWT-003 登录续接完整保留 typed 评论草稿

- GIVEN 游客已输入正文、附件、mentions 和可选回复目标
- WHEN 完成登录并回到原 Comment surface
- THEN postId、replyToCommentId、正文、附件和 ContentCommentMention 原样恢复。
- THEN 宿主或回复目标不一致时拒绝误提交。

<a id="gwt-004"></a>
### GWT-004 回复摘要与分页是服务端 typed 投影

- GIVEN 一级评论存在一个或多个二级回复
- WHEN 读取一级列表并展开回复
- THEN 一级项返回 replyCount、replyPreview、replyNextCursor。
- THEN 展开只调用 ListCommentReplies 并消费 ReplyPageSlice。

<a id="gwt-005"></a>
### GWT-005 一级评论按 hot/latest 服务端稳定排序

- GIVEN 帖子含置顶评论及不同互动量、创建时间的未置顶一级评论
- WHEN 用户按默认 hot 或切换 latest 分页读取评论
- THEN 默认 hot 顺序固定为 isPinned、pinnedAt、hotScore、createdAt、id。
- THEN latest 顺序固定为 isPinned、pinnedAt、createdAt、id。
- THEN App 只传 hot/latest 并重新请求服务端，不做本地重排。
- THEN recommended/most_liked 与旧三档类型、参数、测试扫描为零。

<a id="gwt-006"></a>
### GWT-006 ContentReaction 三态互斥并由列表投影恢复

- GIVEN 用户读取含 viewerReaction 的 Comment
- WHEN 用户执行 like、dislike 或 none
- THEN 三态互斥且服务端返回精确 likeCount/dislikeCount。
- THEN 重入时 ViewerReaction 来自 ContentReaction reader。

<a id="gwt-007"></a>
### GWT-007 图片附件和 mentions 端云全程强类型

- GIVEN 用户在输入面板选择图片并添加 @ 对象
- WHEN 创建 Comment 并重新读取
- THEN command 使用 attachmentMediaIds 和 ContentCommentMention。
- THEN 查询返回 ContentCommentAttachment，不暴露 Map。

<a id="gwt-008"></a>
### GWT-008 四环境数据源和三层证据无 Mock 污染

- GIVEN alpha、beta、gamma、prod 使用各自正式 composition
- WHEN 执行 package purity、环境 verify 与 Comment Journey
- THEN alpha 只经独立 runner 使用 fixture Facet。
- THEN beta/gamma/prod 只使用 Remote，prod kernel 不可达 mock/fixture。

<a id="gwt-009"></a>
### GWT-009 个人评论与互动深链使用 typed Facet

- GIVEN 用户查看我的评论、收到的评论或评论互动项
- WHEN 用户点击项目返回原内容
- THEN ListCommentsByAuthor 与 ListCommentsForPostAuthor 返回 typed Slice。
- THEN 深链携带 postId、commentId 与 parentCommentId 并定位目标。

<a id="gwt-010"></a>
### GWT-010 Comment contract 严格解码且无旧 DTO

- GIVEN generated client 返回 Comment 商用投影
- WHEN pure contracts 解码 command result、page、reply 和能力投影
- THEN 未知 enum、错误字段类型和缺失必填字段 fail closed。
- THEN CommentDto、CommentPage、动态附件 Map 不可达。

<a id="gwt-011"></a>
### GWT-011 权限与可观测字段来自同一商用投影

- GIVEN 作者、访客和 Post owner 分别读取同一 Comment
- WHEN 页面渲染动作并执行 query/command
- THEN isAuthor、canDelete、canReply、canReport、canPin 只由 Service 派生。
- THEN list/append/command、failure、replay 与 projection 指标携带 operation/trace identity。

<a id="gwt-012"></a>
### GWT-012 置顶与删除以服务端内部 CAS 执行命名意图

- GIVEN Post owner 和 Comment author 分别发起置顶或删除意图
- WHEN 执行 pin/unpin 或 delete
- THEN 置顶仅允许 Post owner 操作一级 Comment。
- THEN 服务端加载当前 aggregate version，以有界内部 CAS 重放纯技术冲突；调用方不携带 expectedVersion/If-Match。
- THEN 相同 Idempotency-Key 重放原 receipt，不覆盖后续状态。

<a id="gwt-013"></a>
### GWT-013 Comment 与 ContentReaction 独立对象提交并可靠投影

- GIVEN Command 经对象专属 Facade 到达 aggregate
- WHEN 创建、删除 Comment 或变更 ContentReaction
- THEN aggregate 与 outbox 在同一存储事务提交。
- THEN dispatcher 使用 checkpoint、重试和幂等 event identity。
- THEN PostService 评论方法、Memory store 和旧 Repository 不可达。

<a id="gwt-014"></a>
### GWT-014 production Remote-only 与 alpha fixture 物理隔离

- GIVEN App 以 alpha 或 production composition 启动
- WHEN 构建、分析并扫描 kernel/AOT/SBOM 可达性
- THEN production provider 只返回 RemoteContentCommentFacet 与 RemoteContentPostReactionFacet，依赖缺失启动失败。
- THEN AlphaContentCommentFacet 与 AlphaContentPostReactionFacet 只由 quwoquan_cloud_mock 和 alpha runner 引用。

<a id="gwt-015"></a>
### GWT-015 Comment 四态生命周期与举报治理单轨

- GIVEN active 或 hidden Comment、具备权限的作者/operator 及 Report target=comment
- WHEN 作者删除、operator 隐藏/恢复，或宿主 Post 删除
- THEN 状态只允许 active→deleted、active→hidden→active、active|hidden→tombstoned。
- THEN deleted/tombstoned 为终态，非法迁移返回稳定 conflict；调用方不传 expectedVersion，服务端仅对内部技术 CAS 冲突有界重放。
- THEN 前台列表、回复和计数只包含 active；作者私有投影可见 hidden 状态。
- THEN 举报只写既有 Report 聚合，ResolveReport 通过治理命令处置并保留 CommentModerated 审计事实。

<a id="gwt-016"></a>
### GWT-016 CreateComment 滑动窗口频控可配置且失败可恢复

- GIVEN authenticated persona 在短窗或日窗内连续创建评论
- WHEN 创建量达到配置阈值后再次提交
- THEN 服务端在 Comment 创建事务内按 authorId 串行化，再查询权威短窗/日窗并返回 comment_rate_limited。
- THEN 默认阈值为 30 秒不超过 5 条且 24 小时不超过 200 条，配置变更不改协议。
- THEN 幂等重放在频控前返回原 receipt；并发请求不会超卖额度，删除评论不能绕过计数。
- THEN App 保留草稿并消费 RuntimeFailure/RuntimeRecoveryPolicy，不伪造成功或切换 Mock。

<a id="gwt-017"></a>
### GWT-017 属地、作者赞过、关系与拉黑事实由服务端批量投影

- GIVEN Comment 作者、Post 作者、viewer 之间存在不同 reaction/relationship/block 事实
- WHEN viewer 读取一级评论、回复或个人互动 Slice
- THEN authorIpLocation 为创建时快照，境内只到省级、境外只到国家级，解析失败为空且不臆造。
- THEN authorLiked 只来自 Post 作者的 ContentReaction 事实。
- THEN viewerRelation 只允许 none/following/friend，匿名恒 none。
- THEN 任一方向拉黑或 viewer 拉黑 Post owner 时服务端过滤评论、回复摘要与计数；投影不可用时 fail closed。
- THEN reaction、relationship、block 与附件读取均批量执行，禁止 N+1 和端侧拼装。

<a id="gwt-018"></a>
### GWT-018 评论、回复、提及与置顶通知回到原评论

- GIVEN CommentCreated 或 CommentPinChanged 事实含 post/comment/parent/mentioned user identity
- WHEN notification-service 投影消息且接收者点击通知
- THEN 一级评论通知 Post 作者，回复通知 reply target，mentions 通知被提及用户，置顶通知评论作者。
- THEN 自评、自回与自提及去重，单一事实不会向同一接收者重复投递。
- THEN AppMessage source/target 携带稳定 comment identity，App 经 MediaViewerCommentContext 定位并高亮原评论。
- THEN 目标删除、隐藏或无权访问时进入结构化失效态，不跳到错误对象。

<a id="gwt-019"></a>
### GWT-019 非 alpha 环境只使用真实双栈离线 IP 属地库

- GIVEN content-service 分别以 alpha、beta、gamma、prod composition 启动
- WHEN 装配 Comment IP location resolver 并创建评论
- THEN alpha 只允许 deterministic fixture resolver。
- THEN beta/gamma/prod 只允许 ip2region IPv4+IPv6 离线库，缺库、损坏、错误 provider 或数据超过 45 天均启动失败。
- THEN 镜像固定数据版本与双库 SHA256，保留 Apache-2.0 许可证；原始 IP 不落 Comment、不写日志。
- THEN lookup outcome 与 data age 有 Prometheus 指标和告警，解析失败只落空串。

<a id="gwt-020"></a>
### GWT-020 评论动作、输入与无障碍体验达到统一商用 surface

- GIVEN 用户在 compact/regular/expanded、light/dark、键盘和弱网场景打开评论
- WHEN 切换排序、输入 @/emoji/图片、回复、复制、举报或删除
- THEN @ 按钮打开 typed 关注候选选择器，不默认写入固定账号；已选 mention 可见、可移除并随草稿恢复。
- THEN 删除先二次确认，复制/举报/删除按服务端 capability 显示，游客登录成功续接原动作且关闭登录回安全态。
- THEN 排序与动作触控区域不小于 44pt，具有 button/selected 语义和清晰焦点顺序。
- THEN 窄屏、动态字体下正文、属地和 badge 不裁切；失败保留已有内容或草稿并提供显式恢复动作。

<a id="gwt-021"></a>
### GWT-021 回复预览和展开分页端云契约一致

- GIVEN 某帖子存在一个一级评论和超过 reply_preview_count 的二级回复。
- WHEN 客户端调用 ListComments 后继续调用 ListCommentReplies。
- THEN ListComments 只返回配置数量的 replyPreview，并返回 replyNextCursor。
- THEN ListCommentReplies 每次返回 reply_expand_page_size 条以内的回复和下一页 cursor。
- THEN CreateComment 回复请求写入 replyToCommentId、replyToUserId 和 parentCommentId，列表回显归属一级评论。

## 6. 依赖

- 前置要求：[`publish-comment-reaction`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 平铺内容入口复用 typed Comment surface

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：Gamma 真机完成打开、评论、返回和二次进入
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 沉浸式内容打开和关闭后上下文可恢复

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：三类真实页面均在 Gamma 设备通过恢复 Journey
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 登录续接完整保留 typed 评论草稿

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：评论和回复均完成本地契约、真实 API 与设备续接
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-004"></a>
### OPEN-004 一级评论按 hot/latest 服务端稳定排序

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：两档 keyset、Mongo explain、App 切换与重入恢复全部通过
- 完成判定：`GWT-005` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-005"></a>
### OPEN-005 图片附件和 mentions 端云全程强类型

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：真实 MediaAsset、Mongo、Gamma 页面完成上传到回显
- 完成判定：`GWT-007` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-006"></a>
### OPEN-006 四环境数据源和三层证据无 Mock 污染

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：四环境、SBOM/AOT、Gamma UAT 和 prod rollout 证据绑定同一 commit/Graph hash
- 完成判定：`GWT-008` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-007"></a>
### OPEN-007 个人评论与互动深链使用 typed Facet

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：本地契约、真实 API 与 Gamma 页面 Journey 全部通过
- 完成判定：`GWT-009` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-008"></a>
### OPEN-008 production Remote-only 与 alpha fixture 物理隔离

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺少 package boundary、production purity、AOT/SBOM 与 gamma Remote Journey 的同版本完整证据。
- 完成判定：`GWT-014` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-009"></a>
### OPEN-009 Comment 四态生命周期与举报治理单轨

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：状态机、HTTP、真实 Mongo/outbox、Report 协作和 operator 权限负例全部通过
- 完成判定：`GWT-015` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-010"></a>
### OPEN-010 CreateComment 滑动窗口频控可配置且失败可恢复

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：边界时刻、跨窗、并发、错误映射与 Widget 恢复均通过
- 完成判定：`GWT-016` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-011"></a>
### OPEN-011 属地、作者赞过、关系与拉黑事实由服务端批量投影

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：local contract、真实 Mongo projection、严格 codec 与页面渲染负例一致
- 完成判定：`GWT-017` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-012"></a>
### OPEN-012 评论、回复、提及与置顶通知回到原评论

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：projection local contract、真实 stream API、App 深链与 Gamma 点击 Journey 全部通过
- 完成判定：`GWT-018` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-013"></a>
### OPEN-013 非 alpha 环境只使用真实双栈离线 IP 属地库

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：composition contract、镜像 checksum、gamma 双栈样本、Prometheus readback 与 prod preflight 全部通过
- 完成判定：`GWT-019` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-014"></a>
### OPEN-014 评论动作、输入与无障碍体验达到统一商用 surface

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：Widget contract、语义树、golden/像素、Gamma iOS/Android/Web capability profile Journey 全部通过
- 完成判定：`GWT-020` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-015"></a>
### OPEN-015 回复预览和展开分页端云契约一致

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：Mock、Remote、Go contract test 使用同一组 seed 断言通过。
- 完成判定：`GWT-021` 对应行为满足且真实测试 `spec_ref` 有效
