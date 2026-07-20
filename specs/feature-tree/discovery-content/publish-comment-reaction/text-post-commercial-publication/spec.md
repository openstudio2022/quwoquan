# L3 Story：text-post-commercial-publication

## 节点定位

- `L1_domain_service`: `discovery-content`
- `L2_business_capability`: `publish-comment-reaction`
- `L3_story`: `text-post-commercial-publication`
- AppRoot Journey: `content-creation-to-publication`
- Scenario: `text-post-create-publish-return`

## 用户目标

用户从全局创作入口选择「写文字」后，可以先写再决定发布为短文字或文章；草稿不会丢失，
发布失败有明确恢复动作，发布成功立即看到结果和分发去向。任何没有获得机器 allow 或人工
approve 的内容都不会进入公开读模型。

## 业务对象与边界

| 对象 | 责任 | 边界 |
|---|---|---|
| `LocalPostDraft` | 端侧自动保存、恢复、放弃 | 仅当前设备和当前 Persona，不是远端 Post |
| `PostPublicationIntent` | 冻结一次提交的 payload、媒体顺序与幂等键 | 同一草稿只有一个不可变 intent |
| `Post` | 已提交的不可变内容 revision；只有 approved+published 可公开消费 | 远端允许 `pending_review → published|rejected → deleted`，机器 allow 可直接 published |
| `PostPublicationReceipt` | 提交已被接受的稳定回执 | `state` 只允许 `pending_review` 或 `published`；仅 `published` 允许端侧清理草稿 |
| `MediaAsset` | 文章插图和封面的已验证远端素材 | 发布命令不得携带本地路径 |
| `CirclePostPlacement` | Post 与 Circle 的分发关系 | 独立聚合；Post 不保存 circleIds |
| `PostModerationCase` | 对 pending_review revision 的发布前人工审核，以及已发布 revision 的举报复核 | 绑定 `postId + version + contentDigest`，不承载草稿正文 |

## 领域裁决

### 1. 单轨 Post 生命周期

`SubmitPostPublication --allow--> published --DeletePost--> deleted`

- `draft` 只属于 `LocalPostDraft`。
- `review` 或安全依赖 `unavailable` 只能创建不可公开的 `pending_review` Post，并通过
  `PostSubmittedForReview` 打开人工 Case。
- Case approved 后进入 published；rejected 后进入 rejected。pending/rejected 只允许作者读取。
- `archived` 没有业务命令和页面，不进入 `PostStatus`。
- `PostModerationCase` 状态闭集为
  `pending → reviewed → approved|rejected`，任意非 superseded 状态可在 revision 失效后进入
  `superseded`。

### 2. 强制发布前安全准入

`SubmitPostPublication` 在媒体绑定和 payload 规范化后、事务提交前依次执行：

1. 长度与结构校验。
2. Persona 级发布频控。
3. `PublicationSafetyGate` 内容安全判定。

安全门返回：

- `allow`：继续原子创建 Post + receipt + outbox。
- `review`：创建 pending_review Post + receipt + review outbox；公开读模型不得消费。
- `reject`：返回 metadata 定义的结构化拒绝错误，保留本地草稿，不创建 Post。
- `unavailable`：按 fail-closed 策略进入 pending_review 与人工 Case，不得 fallback 为 published。

生产 composition 缺安全门或频控端口必须 fail-fast；alpha/test 使用确定性 typed adapter，
不得在生产失败后 fallback 为 allow。

### 3. 文本形态由用户确认

编辑器可依据标题、段落、字数和插图建议 `micro` 或 `article`，但发布确认页必须显示：

- `短文字`：正文为主，进入 feed 文字卡。
- `文章`：Markdown + 资源清单 +渲染画像，进入作品浏览器。

建议只设置默认选中项；用户可修改。最终 `contentType` 必须来自确认结果，而不是提交时再次
静默推导。

## 功能规格

### F1 入口与登录续接

- 游客可先看到创作动作面板。
- 点击「写文字」才触发 `createPost` 登录门。
- 关闭登录回安全首页且不循环；登录成功进入原文字编辑器。

### F2 编辑与标题渐进披露

- 首屏标题为「写文字」，不提前暴露「长文编辑」。
- 默认焦点进入正文。
- 标题默认是「添加标题（可选）」入口，点击或恢复有标题草稿时才展开输入框。
- 正文、标题、插图、标签、实体 mention 使用同一 `CreateEditorState`，不新建第二编辑器。

### F3 单一长度合同

长度按 Unicode rune 计数，端云使用同一常量：

- 标题：`80`
- micro 正文：`5000`
- article Markdown：`20000`
- 摘要：`240`
- semantic mentions：`30`

端侧在输入时显示剩余量并阻止继续输入；云侧对绕过端侧的请求返回
`CONTENT.USER.content_too_long`。

### F4 标签与交集事实

- 标签选择使用 tag 域 typed `TagCatalogQuery`，不得使用本地常量或自由字符串。
- 选择结果写入 `semanticMentions(kind=tag,status=published)`，`tagRefs` 只由服务端投影。
- 无标签也可发布；不得把推荐相似度伪装为共同标签事实。

### F5 发布任务与恢复

- 队列公开 typed 状态：`submitting / retry_wait / blocked / accepted`。
- 用户可查看 retry_wait/blocked 的错误原因、重试或放弃。
- `unauthorized` 不进入无限网络重试，必须走登录续接。
- `rate_limited` 使用服务端 recovery-after 调度；不可恢复校验错误进入 blocked。
- receipt.state=`pending_review` 时保留草稿快照和任务；只有状态查询变为 published 才清理草稿。

### F6 发布结果回流

- micro 发布成功打开内容详情。
- article 发布成功打开作品浏览器对应文章。
- 发布结果页/目标页必须显示「已发布」与实际 circle/entity/tag/location 去向摘要。
- 同时 invalidate feed 与当前 Persona 作品列表；不能要求用户手动下拉才看到新内容。

### F7 可观测

创作漏斗使用 ops telemetry catalog 的强类型 `content_publication` 事件，不再写入推荐行为
`/content/behaviors`：

`editor_ready → draft_saved|draft_restored → submit_started → queued|blocked|published`

必带 `contentType / stage / result / objectState / surfaceId`；可选
`durationMs / failReasonCode / correlationHash`。正文、标题、原始 intent id 和用户标识不得上报。

黄金指标：

1. 有效发布率：published / submit_started。
2. 开始创作到内容可见 P95。
3. retry_wait 后恢复成功率。

### F8 发布后治理

- 已发布正文不可编辑；删除走 `DeletePost` 和墓碑。
- 举报打开当前 revision 的 `PostModerationCase`。
- Portal 必须能读取 pending/reviewed case 并执行 review/approve/reject。
- rejected 后 feed/detail 不再公开，作者在站内通知和自己的内容状态中看到原因与申诉入口。

## 非功能

| 指标 | 商用门槛 |
|---|---|
| 编辑器 warm 可交互 | P95 ≤ 1.2s |
| 草稿自动保存成功率 | ≥ 99.9% |
| `SubmitPostPublication` | P95 ≤ 800ms，可用性 ≥ 99.9% |
| 发布开始到内容可见 | P95 ≤ 2s（无媒体转码） |
| 重复 intent 创建 Post 数 | 恒为 1 |
| 未获 allow/approve 的公开 Post 数 | 恒为 0 |
| 发布事件采集完整率 | ≥ 99.9% |

## 灰度与回滚

- 不保留旧 CreatePost/Bind/Publish 三段流程或静默分型双轨。
- 阈值和安全策略来自受控配置；关闭外部安全 provider 时必须 fail-closed 到本地确定性规则，
  不能绕过安全门。
- 发布回流 UI 可回滚到详情直达，但不得回滚为只 Toast 后关闭。
- 任何回滚不得破坏已持久化 LocalPostDraft、intent 或 receipt 的可读性。

## Out of Scope

- 发布后正文在线编辑。
- 跨设备云草稿。
- AI 代写、AI 封面生成或模板市场。
- 把推荐相似度当作标签、关系或交集事实。

