# WP6 · 长文编辑与发布增强（端侧为主）

> 树归属：`discovery-content/publish-comment-reaction` + `content-type-framework`
> 影响 Journey：`content-discovery-to-consumption`（创作回流环）
> 验收意图：GWT + contract；测试证据：T1 / T2 / T3

## 1. 背景与现状

- 三段式已达标：块式编辑器（`entry/widgets/article_editor.dart`，图文混排 + 三种图片环绕）→ 排版页（`article_typography_page.dart`，书页预览 + 纸张/字体）→ 发布确认组件（`entry/widgets/create_publish_confirm_sheet.dart`）。
- 富语义发布闭环已接通：`PublishSettings` 承载并恢复 `summary/tagRefs/entityRefs/assistantUsePolicy`；`ArticleMarkdownCodec` 将这些字段写入 QWQ Rich Markdown front matter；`buildCreatePostPayloadMap()` 写入 `CreatePost` payload。
- `CreatePostRequestWire.tagRefs/entityRefs` 已经从 `String?` 风险修正为 `List<String>?`，修正来自 app metadata codegen 规则与重新生成的 wire，未手改 generated。
- 发布确认组件已具备摘要编辑、小趣摘要生成、标签搜索/添加/删除、关联主页选择/删除、`assistantUsePolicy` 选择；用户文案使用「标签 / 关联主页 / 关联地点和事物」，不暴露「实体」内部词。
- 行内对象提及已使用 `ArticleInlineSpan(kind: 'entity')` 接入编辑器工具栏「提及对象」入口，复用 `HomepagePicker`；样式切换、切段、插图、草稿/Markdown 往返均由 provider/codec/payload 测试守护。
- 读侧 `ArticlePageReadOnlyView` 已按 `ArticleInlineSpan.isEntity` 渲染可点击 rich text，并通过 `onEntityTap` 交给宿主跳转对象主页。
- 小趣推荐标签/对象依赖 WP8 `creation-suggest` metadata，本包不硬编码 assistant path/operation；WP8 未上线时仅保留摘要生成与手动选择能力。
- 技债：`create_page.dart` 已从发布确认 sheet 与行内提及 picker 中抽离部分逻辑，但当前仍约 2646 行，未降到 <1000；已登记到 `CR-20260611-033` convergence item，后续按 article-editor-refactor 继续拆分。

## 2. 功能规格

### 2.0 统一概念基线（本包必须遵守）

- 长文与其他内容一样只有 `赞 / 评 / 转` 三个互动动作，无任何长期动作入口；读者「以后再看」由 `我的足迹` 自动承载。
- 创作链路必须围绕连接结果组织：内容被 `赞`、被 `讨论`、被 `转发`，并把读者引向内容背后的对象——关注作者、关注绑定实体、加入绑定圈子。
- 因此摘要、标签、对象绑定、小趣辅助生成的目标，应优先服务“关注作者 / 进入圈子 / 关注对象 / 形成讨论”，而不是“提高收藏率”或任何内容沉淀指标。

### 2.1 发布确认页增强

- **标签选择**：发布确认组件使用 tag repository 搜索结果生成路径制 `tagRef`，不接受未解析成路径的裸标签；payload 写入 `tagRefs`。
- **多对象绑定**：在 `primaryHomepage`（主挂载，保留）之外支持附加关联主页/地点和事物，payload 写入 `entityRefs`；前台文案不出现「实体」。
- **摘要可编辑 + AI 摘要**：摘要字段开放编辑；「小趣生成摘要」调用 content `GenerateArticleSummary`，成功填入摘要框且用户可继续修改，失败不覆盖当前摘要。
- **小趣推荐标签和对象**：入口消费 WP8 的创作辅助契约（见 §3）；WP8 未合入时入口隐藏/不出现，不阻塞发布。
- `assistantUsePolicy` 开放用户选择并写入 payload 与 Markdown front matter，缺省 `inherit`。

### 2.2 编辑器行内对象提及

- 行内对象提及的端侧真相源为 `ArticleInlineSpan(kind: 'entity', targetType, targetId, displayText)`；Markdown 语法为 `@[对象名](entity:homepage/id)`。
- `article_markdown_codec.dart` 编解码往返无损；`CreateEditorProvider.attachArticleEntityMention()` 写入 span；`toggleArticleInlineStyle` 与切段/插图相关路径保留对象提及 span 元数据。
- 编辑器工具栏新增「提及对象」入口，复用 `HomepagePicker` 选择目标对象后将当前选区标注为对象提及。
- 发布后读侧 rich text 已通过 `onEntityTap` 支持点击跳对象主页；gamma 端到端仍作为集成验收旅程留证。

### 2.3 结构拆分（R03）

- 本轮新增能力不得继续堆入 `create_page.dart`：发布确认页已拆到 `create_publish_confirm_sheet.dart`，行内提及 picker 已拆到 `article_entity_mention_picker.dart`。
- `create_page.dart` 仍未降到 ≤1000 行，作为本 CR convergence item 继续拆分，后续目标是保留协调层，媒体处理、草稿调度、发布 orchestration、编辑器 adapter 分离。

## 3. 周边契约

- 云侧无需改动：`CreatePost` writable（`entityRefs/tagRefs/summary`）、`GenerateArticleSummary` 均已就绪。
- mention 语法/派生规则若需登记 → `contracts/metadata/content/post/`（fields.yaml entityMentions 描述层），不改字段形状。
- **小趣创作辅助契约（与 WP8 共同冻结）**：`POST /v1/assistant/skills/creation-suggest`（语义名，最终 path 由 WP8 经 assistant metadata 定稿）——请求 `{draftTitle, draftSummary, bodyDigest, boundCircleIds[], primaryHomepageId}`，响应 `{suggestedTagRefs[], suggestedHomepages[{id,type,displayName}], suggestedTitle?, suggestedSummary?}`。本包按此形状写适配层与降级逻辑；形状变更需双包确认。
- 新增文案 key 追加 `UITextConstants`，登记于此：（细化会话填写）。

## 4. 改动范围

- `quwoquan_app/lib/ui/content/entry/`（create_page 协调层、发布确认组件、publish_settings_models、create_page_remote_helpers、行内提及 picker）
- `quwoquan_app/lib/ui/content/article_render/markdown/`（front matter 与 entity inline span codec）
- `quwoquan_app/lib/cloud/services/content/`（summary API 与 CreatePost wire 出口）
- 对应测试（codec 往返、payload 契约、provider/editor/widget）
- **禁止**改 `lib/ui/discovery/**`、`works_immersive_viewer.dart`、`lib/components/object_page/**`

## 5. 准出要求

1. T1：发布 payload 契约测试——选择了标签/关联对象/摘要后 `CreatePost` 请求体含 `tagRefs/entityRefs/summary/assistantUsePolicy` 且与 service.yaml writable 对齐。
2. T1：entity inline span markdown 编解码往返测试（含 front matter 与 inline mention）。
3. T2：发布确认页 widget 测试（标签选择、多实体、摘要编辑、AI 摘要按钮三态：加载/成功/失败结构化错误）。
4. T3：gamma 发布一篇带 实体提及+多实体+圈子+标签+AI 摘要 的长文，读侧 entityMentions 可点。
5. 新增发布 UI 与提及 picker 均为独立文件；`create_page.dart` 未降至 <1000 的剩余拆分登记到 CR convergence item。
6. `bash agent_ops/gate/gate_repo.sh --scope app` 全绿；若本地只跑子集，必须在 CR dev_log 记录未跑项/阻断。

## 6. 验收标准（GWT 样例）

- Given 我在编辑器输入正文并点「提及对象」选择「九寨沟景区」，Then 行内插入蓝色提及，草稿保存/恢复后提及无损。
- Given 我在发布确认页点「小趣生成摘要」，Then 摘要框填入 AI 草案且可继续编辑；服务失败时显示结构化错误并保留手写摘要。
- Given 我选择 2 个标签、1 个主挂载主页、1 个附加对象、2 个圈子后发布，Then CreatePost payload 完整携带且发布成功；TA 在阅读侧可点提及跳转对象主页。
- Given WP8 未上线，Then 「小趣推荐标签和实体」入口不出现，其余发布能力不受影响。
