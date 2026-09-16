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
- 四环境 Remote-only、test-only typed double 隔离、严格 decoder 与 RuntimeFailure。
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
### REQ-003 评论只在提交时登录并完整续接 typed 草稿

- 游客必须能进入评论或回复输入态并完成正文、emoji、mentions 与本地图片选择，只有点击提交时才触发登录。
- 游客选择图片时只保留受控本地路径与预览，不得在登录前调用需要账号身份的媒体上传 operation；登录成功续接提交时才上传图片并转换为真实 `MediaAsset` identity。
- 登录续接必须保留正文、已上传附件、待上传本地图片、mentions、宿主内容和回复目标；登录成功后在原 Comment surface 自动完成原提交，目标不一致时拒绝误提交。
- 关闭登录必须 pop 回原评论输入态，保留全部输入并且不得再次自动弹出登录；用户可继续编辑或主动关闭输入态。

<a id="req-004"></a>
### REQ-004 回复摘要与分页是服务端 typed 投影

- 一级评论查询必须返回 typed 回复摘要和游标，展开操作只能读取独立的二级回复分页。

<a id="req-005"></a>
### REQ-005 一级评论按 hot/latest 服务端稳定排序

- 一级评论只支持 `hot` 与 `latest` 两档服务端稳定排序；App 不得本地重排。

<a id="req-006"></a>
### REQ-006 ContentReaction 三态互斥并由列表投影恢复

- `like`、`dislike` 与 `none` 必须互斥，保持 authenticated Persona 要求；一级评论、回复与个人互动 Tab 共享同一 actor/comment 的版本化 Reaction，不进入 Post bool 队列。
- 本人反应、命令结果和统计新鲜度独立：按钮允许当前意图乐观，赞/踩数字只读最近有效服务端统计，不做本地加减；未知状态不当作 none 盲切换。
- 确认 receipt 即结束该命令，统计落后或提交后统计读取失败不改报未提交。确定拒绝仅撤当前 intent 的 overlay，不恢复整树快照，不抹掉其他评论、回复或成功互动。
- 权限同时满足评论可互动和父 Post published/审核/actor 可访问；内部生命周期补偿与用户命令分别授权。Reaction 的前置版本、签名依据、幂等恢复与有限窗口引用 [reaction-state-counter](../reaction-state-counter/spec.md#req-004)，不改变 Comment 创建、置顶、删除的独立命令协议。

<a id="req-007"></a>
### REQ-007 图片附件和 mentions 端云全程强类型

- 图片附件只能引用真实 `MediaAsset`，mentions 必须使用强类型对象并在创建后按原语义回读。

<a id="req-008"></a>
### REQ-008 四环境数据源和三层证据无 Mock 污染

- alpha 由隔离组合根注入对象级本地 adapter；beta/gamma/prod App 使用 Remote Facet。测试树 typed double 与环境 artifact 物理隔离，发布证据必须绑定同一 commit 与 ContractGraph 摘要。

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
### GWT-003 评论只在提交时登录并完整续接 typed 草稿

- GIVEN 游客已打开评论或回复输入态，并输入正文、emoji、mentions、选择本地图片和可选回复目标。
- WHEN 游客尚未点击提交，或在提交触发登录后关闭登录。
- THEN 输入、选择本地图片与预览均不调用媒体上传 operation；关闭登录 pop 回原 Comment surface，postId、replyToCommentId、正文、本地图片、已上传附件和 ContentCommentMention 原样保留且不再次弹登录。
- WHEN 游客点击提交并完成登录回到原 Comment surface。
- THEN 待上传本地图片先转换为真实 MediaAsset identity，再与正文、已上传附件和 ContentCommentMention 自动完成一次原提交，用户无需重复点击。
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
- THEN 三态互斥，按钮只乐观覆盖本 intent；服务端统计按声明来源水位返回赞/踩数，不承诺与该 receipt 同时可见或由 App 本地加减。
- THEN receipt 确认独立结束命令 pending，重入时本人态来自同 actor 的版本化 ContentReaction reader，统计落后/不可用不得重发已成功命令。

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
- THEN alpha 使用隔离本地演练 Facet，beta/gamma/prod 使用 Remote Facet；四环境 kernel/UAT support 均不可达 mock/fixture。
- THEN typed double 只存在测试树，不作为环境 Journey 证据。

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
### GWT-014 四环境 Remote-only 与 test-only double 物理隔离

- GIVEN App 以 alpha、beta、gamma 或 prod composition 启动
- WHEN 构建、分析并扫描 kernel/AOT/SBOM 可达性
- THEN 四环境 provider 只返回 RemoteContentCommentFacet 与 RemoteContentPostReactionFacet，依赖缺失启动失败。
- THEN typed double 只由测试树引用，不进入 runner、UAT support、kernel/AOT 或 SBOM。

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
- THEN alpha/beta/gamma/prod 只允许受环境配置约束的 ip2region IPv4+IPv6 离线库；deterministic resolver 仅存在测试树。
- THEN 环境缺库、损坏、错误 provider 或数据超过 45 天均启动失败。
- THEN 镜像固定数据版本与双库 SHA256，保留 Apache-2.0 许可证；原始 IP 不落 Comment、不写日志。
- THEN lookup outcome 与 data age 有 Prometheus 指标和告警，解析失败只落空串。

<a id="gwt-020"></a>
### GWT-020 评论动作、输入与无障碍体验达到统一商用 surface

- GIVEN 用户在 compact/regular/expanded、light/dark、键盘和弱网场景打开评论
- WHEN 切换排序、输入 @/emoji/图片、回复、复制、举报或删除
- THEN @ 按钮打开 typed 关注候选选择器，不默认写入固定账号；已选 mention 可见、可移除并随草稿恢复。
- THEN 删除先二次确认，复制/举报/删除按服务端 capability 显示，游客登录成功续接原动作；评论提交登录关闭时回到原 Comment 输入态并保留草稿，其他动作关闭登录回所属安全态。
- THEN 排序与动作触控区域不小于 44pt，具有 button/selected 语义和清晰焦点顺序。
- THEN 窄屏、动态字体下正文、属地和 badge 不裁切；失败保留已有内容或草稿并提供显式恢复动作。

<a id="gwt-021"></a>
### GWT-021 回复预览和展开分页端云契约一致

- GIVEN 某帖子存在一个一级评论和超过 reply_preview_count 的二级回复。
- WHEN 客户端调用 ListComments 后继续调用 ListCommentReplies。
- THEN ListComments 只返回配置数量的 replyPreview，并返回 replyNextCursor。
- THEN ListCommentReplies 每次返回 reply_expand_page_size 条以内的回复和下一页 cursor。
- THEN CreateComment 回复请求写入 replyToCommentId、replyToUserId 和 parentCommentId，列表回显归属一级评论。

<a id="gwt-022"></a>
### GWT-022 评论三态共享意图与局部失败恢复

- GIVEN 同 actor 在一级评论、回复或个人互动 Tab 看到同一 comment，另一个评论/回复已有成功变更。
- WHEN 当前 comment 连续赞→踩→none，出现版本冲突、响应丢失或统计读取失败。
- THEN 同 comment 共享互斥三态、稳定命令身份和版本；未知不当 none，不能进入 Post bool 队列；已发送前驱未决时后继不绕过。
- AND 确定拒绝只撤本动作 overlay，不回滚整树或其他成功变更；receipt 已确认就结束 pending，数字继续显示有效服务端基线，不本地加减、不因统计失败再写。
- AND 未登录、评论不可互动、父 Post 非 published 或 actor 无权限时不接纳；真实 owner 资格读取失败不伪成功，内部删除补偿不成为公开绕鉴权入口。

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
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：评论和回复均完成提交时登录、本地附件延迟上传、取消登录回原输入态、本地契约、真实 API 与设备续接
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
### OPEN-008 四环境 Remote-only 与 test-only double 物理隔离

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺少四环境 package boundary、Remote composition attestation、AOT/SBOM 与 release-bound Remote Journey 的同版本完整证据。
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

<a id="open-016"></a>
### OPEN-016 评论三态、独立统计与局部恢复尚缺当前证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：`REQ-006`、`GWT-006` 与新增 `GWT-022` 尚待 typed 统计/回执合同、共享三态、局部 overlay 恢复和真实父 Post/Comment 资格验证；旧“命令响应必带即时精确数”用例不证明当前结果分型。
- 完成判定：`GWT-006`、`GWT-022` 的单评论反转/unknown、另一评论已成功、提交后统计失败、失权与登录反例在 local_contract/真实 API/双真机直接绑定当前 `spec_ref`，不得由 Post bool 或整树回滚实现替代。

## 8. 三态增量的待实现测试绑定

以下是需要扩展的实际 runner 与未来 `spec_ref` 落点，不表示新 required 证据已实现或通过；现有其他 GWT/OPEN 保持各自责任。

- `quwoquan_app/test/local_contract/service/content_service/content/comment/comment_facet_widget__local_contract_test.dart`、同目录 `content_comment_facet__local_contract_test.dart` 和 `comment_item_actions__local_contract_test.dart`：扩展绑定 `GWT-006`、`GWT-022` 的三态互斥、未知、局部撤销与数字基线。
- `quwoquan_app/test/api_integration/service/content_service/content/comment/content_comment_remote__api_integration_test.dart` 与 `quwoquan_app/test/api_integration/service/content_service/content/content_reaction/content_reaction_remote__api_integration_test.dart`：扩展绑定上述两锚的真实 receipt、统计失败隔离和同 actor 重入。
- `quwoquan_service/services/content-service/tests/api_integration/content/content_reaction/http_mongo_transaction__api_integration_test.go` 只承担事务专项；真实 Comment/父 Post 资格组合需在同对象 API 目录新增直接场景并绑定 `GWT-022`，不能用恒 active reader 替身代证。
- `quwoquan_app/test/user_acceptance/service/content_service/content/comment/comment_post__user_acceptance_test.dart`：扩展绑定 `GWT-006`、`GWT-022`，一级/回复/个人互动入口分别有真机动作和服务读回，不以 UI selected 状态证明提交。
