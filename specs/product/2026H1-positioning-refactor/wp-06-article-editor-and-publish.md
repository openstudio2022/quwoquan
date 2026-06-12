# WP6 · 长文编辑与发布增强（端侧为主）

> 树归属：`discovery-content/publish-comment-reaction` + `content-type-framework`
> 影响 Journey：`content-discovery-to-consumption`（创作回流环）
> 验收意图：GWT + contract；测试证据：T1 / T2 / T3

## 1. 背景与现状

- 三段式已达标：块式编辑器（`entry/widgets/article_editor.dart`，图文混排 + 三种图片环绕）→ 排版页（`article_typography_page.dart`，书页预览 + 纸张/字体）→ 发布确认 sheet（`_CreatePublishConfirmSheet`）。
- 发布确认页已有：可见范围、单实体挂载（`primaryHomepage*`）、多圈子选择、身份模式（作品/点滴）。
- 缺口（云侧契约已就绪、端侧未接）：
  - `tagRefs`：CreatePost writable 已含，端侧 payload 不写、无选择 UI；
  - `entityRefs`（多实体）：同上；
  - `GenerateArticleSummary`（`/v1/content/articles/summary:generate`）：API + repository 已实现，UI 零调用；摘要现为自动截断 120 字、不可编辑；
  - 行内实体提及：`entityMentions` 仅读侧消费（`ArticleEntityMentionDto`），编辑器 AST（`qwq_markdown_ast.dart`）无 mention 节点；
  - 小趣创作辅助：零入口（`assistantUsePolicy: 'inherit'` 硬写）。
- 技债：`create_page.dart` 3155 行，超 R03 红线（>1000 行 GATE_BLOCK 口径），本包内拆分。

## 2. 功能规格

### 2.1 发布确认页增强

- **标签选择**：新增标签选择入口（路径制 `tagRef`，来源数据工程 taxonomy；选择器复用/对齐既有 tag 域端侧能力），payload 写入 `tagRefs`。
- **多实体绑定**：在 `primaryHomepage`（主挂载，保留）之外支持附加实体引用，payload 写入 `entityRefs`；前台文案用「关联主页 / 关联地点和事物」，不出现「实体」。
- **摘要可编辑 + AI 摘要**：摘要字段开放编辑；新增「小趣生成摘要」按钮调用 `GenerateArticleSummary`，结果填入可再编辑；保留 120 字自动截断为缺省兜底。
- **小趣推荐标签和实体**：入口消费 WP8 的创作辅助契约（见 §3）；WP8 未合入时入口隐藏（feature 探测），不阻塞本包准出。
- `assistantUsePolicy` 开放用户选择（front matter 写入），缺省 `inherit`。

### 2.2 编辑器行内实体提及

- `qwq_markdown_ast.dart` 新增 mention 节点（`subjectType/subjectId/displayName`），`article_markdown_codec.dart` 编解码往返无损；语法形态经 metadata 登记（与读侧 `entityMentions` 派生规则同源）。
- 编辑器工具栏新增「提及对象」入口（搜索 picker 复用 `HomepagePicker` 能力），插入行内 mention；就近浮层原则不变。
- 发布后读侧 `entityMentions` 可点跳对象主页（读侧已具备，补端到端测试）。

### 2.3 结构拆分（R03）

- `create_page.dart` 拆分为 ≤1000 行的协调层 + 子组件/子控制器文件；行为不变，以既有测试守护。

## 3. 周边契约

- 云侧无需改动：`CreatePost` writable（`entityRefs/tagRefs/summary`）、`GenerateArticleSummary` 均已就绪。
- mention 语法/派生规则若需登记 → `contracts/metadata/content/post/`（fields.yaml entityMentions 描述层），不改字段形状。
- **小趣创作辅助契约（与 WP8 共同冻结）**：`POST /v1/assistant/skills/creation-suggest`（语义名，最终 path 由 WP8 经 assistant metadata 定稿）——请求 `{draftTitle, draftSummary, bodyDigest, boundCircleIds[], primaryHomepageId}`，响应 `{suggestedTagRefs[], suggestedHomepages[{id,type,displayName}], suggestedTitle?, suggestedSummary?}`。本包按此形状写适配层与降级逻辑；形状变更需双包确认。
- 新增文案 key 追加 `UITextConstants`，登记于此：（细化会话填写）。

## 4. 改动范围

- `quwoquan_app/lib/ui/content/entry/`（create_page 拆分、发布确认 sheet、publish_settings_models、create_page_remote_helpers、新标签/实体选择组件）
- `quwoquan_app/lib/ui/content/markdown/`（AST mention 节点 + codec）
- `quwoquan_app/lib/cloud/services/content/`（payload 组装、summary API 调用接线）
- 对应测试（codec 往返、payload 契约、widget）
- **禁止**改 `lib/ui/discovery/**`、`works_immersive_viewer.dart`、`lib/components/object_page/**`

## 5. 准出要求

1. T1：发布 payload 契约测试——选择了标签/实体/摘要后 `CreatePost` 请求体含 `tagRefs/entityRefs/summary` 且与 service.yaml writable 对齐。
2. T1：mention 节点 markdown 编解码往返测试（含嵌套/边界）。
3. T2：发布确认页 widget 测试（标签选择、多实体、摘要编辑、AI 摘要按钮三态：加载/成功/失败结构化错误）。
4. T3：gamma 发布一篇带 实体提及+多实体+圈子+标签+AI 摘要 的长文，读侧 entityMentions 可点。
5. `create_page.dart` 拆分后所有创作相关文件 ≤1000 行；既有创作/草稿测试全绿。
6. `bash agent_ops/gate/gate_repo.sh --scope app` 全绿。

## 6. 验收标准（GWT 样例）

- Given 我在编辑器输入正文并点「提及对象」选择「九寨沟景区」，Then 行内插入蓝色提及，草稿保存/恢复后提及无损。
- Given 我在发布确认页点「小趣生成摘要」，Then 摘要框填入 AI 草案且可继续编辑；服务失败时显示结构化错误并保留手写摘要。
- Given 我选择 2 个标签、1 个主挂载主页、1 个附加对象、2 个圈子后发布，Then CreatePost payload 完整携带且发布成功；TA 在阅读侧可点提及跳转对象主页。
- Given WP8 未上线，Then 「小趣推荐标签和实体」入口不出现，其余发布能力不受影响。
