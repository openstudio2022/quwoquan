# L3 Story：TEXT 内容商用发布 (`text-post-commercial-publication`)

> 所属能力：[`publish-comment-reaction`](../spec.md)
>
> Journey / Scenario：[`JNY-003 / SCN-008`](../../../spec.md#scn-008)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，我希望写文字从编辑、显式形态确认、发布前安全准入、可靠提交到结果回流与运营观测的商用闭环，从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- micro/article 统一文字编辑器与显式发布形态确认。
- LocalPostDraft、PostPublicationIntent、Post receipt 和 CirclePostPlacement 的可靠协作。
- 发布前长度、频控和内容安全 fail-closed 准入。
- 发布结果回流、发布任务恢复、tag 事实、审核运营和发布漏斗。

### Out of Scope

- 发布后正文编辑。
- 跨设备云草稿。
- AI 代写与模板市场。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 写文字入口正文优先且短文字与文章由用户显式确认

- micro 与 article 两种确认结果均有 widget 与 payload 合同证据。

<a id="req-002"></a>
### REQ-002 文字长度合同和发布频控端云同源

- App 与真实 content API 必须对相同输入边界返回同一 canonical 错误语义。

<a id="req-003"></a>
### REQ-003 发布前安全门 fail-closed 且未获批准时不公开 Post

- 准入的四种结论、人工批准/拒绝与并发重放必须收敛到唯一发布状态。

<a id="req-004"></a>
### REQ-004 发布意图可恢复可管理且鉴权失败不空转

- 重启后必须恢复待发布状态；错误分类决定可重试或放弃，二者不得同时可用。

<a id="req-005"></a>
### REQ-005 发布成功立即回流真实 Post 并刷新消费投影

- 写短文字和写文章两条完整 UAT 均从底栏加号走到回读页。

<a id="req-006"></a>
### REQ-006 标签和实体只以可证实 semantic mention 进入交集投影

- picker、payload、服务端投影和回读均有合同证据。

<a id="req-007"></a>
### REQ-007 创作发布漏斗进入产品遥测单轨并可运营

- App reporter、product-ops ingestion、dashboard 和 alert 必须由同一版本的直接契约证据串联。

<a id="req-008"></a>
### REQ-008 举报审核可运营且决定与 Post revision 一致

- Portal、content API、通知消费与公开读路径有端到端证据。

<a id="req-009"></a>
### REQ-009 安全检查未放行时只能创建不可公开的 `pending_review` Post

- 安全检查返回 `review` 或依赖 `unavailable` 时，只能创建不可公开的 `pending_review` Post。
- `review`：创建 pending_review Post + receipt + review outbox；公开读模型不得消费。
- `unavailable`：按 fail-closed 策略进入 pending_review 与人工 Case，不得 fallback 为 published。
- 标签选择使用 tag 域 typed `TagCatalogQuery`，不得使用本地常量或自由字符串。
- 无标签也可发布；不得把推荐相似度伪装为共同标签事实。
- `unauthorized` 不进入无限网络重试，必须走登录续接。
- `rate_limited` 使用服务端 recovery-after 调度；不可恢复校验错误进入 blocked。
- 发布结果页/目标页必须显示「已发布」与实际 circle/entity/tag/location 去向摘要。
- 同时 invalidate feed 与当前 Persona 作品列表；不能要求用户手动下拉才看到新内容。
- 已发布正文不可编辑；删除走 `DeletePost` 和墓碑。

## 4. 契约引用

- canonical：`quwoquan_service/services/content-service/contracts/content/post/operations.yaml`
- canonical：`quwoquan_app/packages/quwoquan_cloud_contracts/lib/src/content/post_publication_contracts.dart`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/errors.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/object.yaml`
- canonical：`quwoquan_app/lib/ui/content/entry/providers/post_publication_intent_queue_provider.dart`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/projections/work_browser_item.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/fields.yaml`
- canonical：`quwoquan_service/services/tag-service/contracts/tag/tag_node_view/operations.yaml`
- canonical：`quwoquan_service/services/product-ops-service/contracts/product_ops/event_record/event_catalog.yaml`
- canonical：`quwoquan_ops/observability/monitoring/alerts/content_contract/post.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/trust_safety/post_moderation_case/operations.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/trust_safety/post_moderation_case/fields.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 写文字入口正文优先且短文字与文章由用户显式确认

- GIVEN 用户已登录并从全局创作面板点击写文字。
- WHEN 用户分别输入轻量正文和包含标题、多段落或插图的重内容并进入发布确认。
- THEN 顶栏显示写文字而非长文编辑，默认焦点进入正文。
- THEN 标题以添加标题可选入口渐进展开。
- THEN 系统可建议短文字或文章，但确认页显示并允许用户修改最终形态。
- THEN 最终 typed command 的 contentType 与用户确认一致，提交阶段不得再次静默推导。

<a id="gwt-002"></a>
### GWT-002 文字长度合同和发布频控端云同源

- GIVEN 标题、micro 正文、article Markdown、摘要与 mention 已声明唯一长度上限。
- WHEN 用户在边界值和超边界值提交，或同一 Persona 在频控窗口内连续发布。
- THEN 边界值可发布，超界请求返回 CONTENT.USER.content_too_long。
- THEN 频控命中返回 CONTENT.USER.rate_limited 和 recovery-after。
- THEN App 展示剩余量并按恢复时间调度，不无限立即重试。

<a id="gwt-003"></a>
### GWT-003 发布前安全门 fail-closed 且未获批准时不公开 Post

- GIVEN content-service 已装配 PublicationSafetyGate。
- WHEN 安全门分别返回 allow、review、reject 和 unavailable。
- THEN allow 原子创建一个 published Post、receipt 和 outbox。
- THEN review 创建不可公开 pending_review Post、receipt 和 review outbox。
- THEN reject 返回结构化拒绝，草稿保留且 Post/receipt/outbox 数均为零。
- THEN unavailable 按 fail-closed 策略创建 pending_review 并进入人工 Case，公开 Post 数为零。
- THEN production composition 缺端口时启动失败。

<a id="gwt-004"></a>
### GWT-004 发布意图可恢复可管理且鉴权失败不空转

- GIVEN 用户已产生 submitting、retry_wait 或 blocked 发布意图。
- WHEN 网络恢复、登录失效、服务限流、永久校验失败或用户主动放弃。
- THEN 发布任务页展示状态、错误与重试或放弃动作。
- THEN unauthorized 进入登录续接而非网络重试。
- THEN rate_limited 尊重 recovery-after。
- THEN 仅 published receipt 清理草稿；放弃后后台不得复活 intent。

<a id="gwt-005"></a>
### GWT-005 发布成功立即回流真实 Post 并刷新消费投影

- GIVEN micro 或 article 发布返回 published receipt。
- WHEN App 处理成功结果。
- THEN micro 打开内容详情，article 打开作品浏览器文章。
- THEN 目标页展示已发布和真实圈子、实体、标签、位置去向。
- THEN feed 与当前 Persona 作品列表失效并回读同一 Post。
- THEN 不出现仅 Toast 后关闭或要求手动下拉的断点。

<a id="gwt-006"></a>
### GWT-006 标签和实体只以可证实 semantic mention 进入交集投影

- GIVEN 用户可从 typed tag/entity picker 选择目标，也可不选择。
- WHEN 用户发布包含标签、实体或两者都无的文字内容。
- THEN 选择项写入 semanticMentions，服务端只投影合法 published mention。
- THEN 非法、pending 或 rejected mention 不进入 tagRefs/entityRefs。
- THEN 推荐相似度和自由字符串不得伪装成事实标签。

<a id="gwt-007"></a>
### GWT-007 创作发布漏斗进入产品遥测单轨并可运营

- GIVEN 写文字页面已进入、保存草稿并提交发布。
- WHEN 发布成功、排队、阻断或失败。
- THEN App 只提交强类型 content_publication 事件，不调用推荐行为 ReportBehaviors。
- THEN 事件包含 contentType、stage、result、objectState、surfaceId，且不含正文或原始 intentId。
- THEN Dashboard 可计算三项黄金指标，发布可用性和 P95 告警均有规则。

<a id="gwt-008"></a>
### GWT-008 举报审核可运营且决定与 Post revision 一致

- GIVEN 已发布 Post 被举报并打开当前 revision 的 PostModerationCase。
- WHEN operator 在 Portal 领取、复核并批准或拒绝。
- THEN pending、reviewed、approved、rejected、superseded 状态迁移符合闭集。
- THEN 旧 revision 决定不能覆盖新 revision。
- THEN rejected Post 从公开读模型下架，作者收到站内信并可查看原因。
- THEN Portal 不使用 mock/seed 数据。

## 6. 依赖

- 前置要求：[`publish-comment-reaction`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 写文字入口正文优先且短文字与文章由用户显式确认

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：micro 与 article 两种确认结果均有 widget 与 payload 合同证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 文字长度合同和发布频控端云同源

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：App local_contract 与真实 content API 对同一边界和错误码给出一致结果。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 发布前安全门 fail-closed 且未获批准时不公开 Post

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：四种结论、人工批准/拒绝与并发重放均有 local_contract 和 api_integration 证据。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-004"></a>
### OPEN-004 发布意图可恢复可管理且鉴权失败不空转

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：重启恢复、错误分类、重试与放弃状态机均有 local_contract。
- 完成判定：`GWT-004` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-005"></a>
### OPEN-005 发布成功立即回流真实 Post 并刷新消费投影

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：写短文字和写文章两条完整 UAT 均从底栏加号走到回读页。
- 完成判定：`GWT-005` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-006"></a>
### OPEN-006 标签和实体只以可证实 semantic mention 进入交集投影

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：picker、payload、服务端投影和回读均有合同证据。
- 完成判定：`GWT-006` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-007"></a>
### OPEN-007 创作发布漏斗进入产品遥测单轨并可运营

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺少 App reporter、product-ops ingestion、dashboard 和 alert 的同源端到端证据。
- 完成判定：`GWT-007` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-008"></a>
### OPEN-008 举报审核可运营且决定与 Post revision 一致

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：Portal、content API、通知消费与公开读路径有端到端证据。
- 完成判定：`GWT-008` 对应行为满足且真实测试 `spec_ref` 有效
