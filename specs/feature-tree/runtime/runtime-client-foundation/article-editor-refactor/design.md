# 文章编辑器完全重构 — 设计基线

> **L2**：`runtime-client-foundation`  
> **L3**：`article-editor-refactor`  
> **上游规格**：`spec.md`  
> **验收**：`acceptance.yaml`

---

## 1. 设计动因

- 现有沉浸文章路径为**纯文本 + 分页近似**，**图文环绕**在数据层存在但编辑态为上下堆叠，**非 WYSIWYG** 与阅读态不一致。
- 工具栏能力分散（结构 / 模版 / 字体三分），缺少**样式、序号、排版**的清晰 IA，且无 **undo/redo**。
- 类型与开关名含 **`V2` / `create_editor_v2`**，与「前后兼容、无版本后缀」的维护目标冲突；需**统一命名**并**全库迁移**。

---

## 2. 上游输入评审

| 输入 | 结论 |
|------|------|
| `spec.md` | 已冻结顶栏、底栏、面板、WYSIWYG、卡片侵入式、横切门禁；作为本设计范围边界。 |
| `creation-mode-and-surface-ia-unification` | 已引入统一状态；本设计在其上**收敛命名**并**扩展文章能力**，不保留双轨状态命名。 |
| `contracts/metadata` | 文章载荷与块结构扩展须先 metadata 再 codegen；与 `metadata_driven_ui_gap_inventory` 对齐。 |
| `specs/02_IOS_NATIVE_FRONTEND_UX_SPEC.md` | 材质、贴底高度、断点、语义 token 为强制约束。 |

---

## 3. 对标输入分析

| 参考 | 借鉴 | 不借鉴 |
|------|------|--------|
| iOS 备忘录 / Pages | 键盘与附件条高度一致、撤销重做独立 | 系统私有 API |
| 常见富文本编辑器 | 块级结构 + span 样式、undo 栈 | 直接引入 WebView 编辑 |
| 现有 `ArticleWrappedParagraph` / 分页引擎 | 阅读侧环绕与测量思路 | 编辑侧继续用「仅预览组件」替代 |

---

## 4. 方案对比

### 方案 A：自研块模型 + `CustomEditable`（或等价）+ 自管 undo

- **优点**：依赖少、与现有 `ArticleDocumentData` / 分页引擎可逐步对齐；包体积可控。
- **缺点**：开发与无障碍成本高；需完整测试选区、输入法、列表嵌套。

### 方案 B：成熟富文本库（如 `super_editor` 等）

- **优点**：选区、撤销、块结构可能较完整。
- **缺点**：与现有 Cupertino 壳、分页、`ArticlePaginationEngine` 集成成本高；需评估 license 与体积。

### 选型决策（初稿）

- **默认采用方案 A**：以 **块 + span 文档模型** 为核心，编辑区采用 **Flutter 层可组合方案**（`TextSpan` + 控制器或社区库中**仅采编排层**），在 `design` 评审中可对方案 B 做 **spike 后**再最终确认。
- **undo/redo**：使用 **Command 模式** 或 **文档快照差分**（浅层优先），与面板状态 **解耦**。

---

## 5. 关键设计决策

### 5.1 命名：去掉 `V2` 与 `v` 版本后缀

| 当前 | 目标 |
|------|------|
| `CreateEditorStateV2` | **`CreateEditorState`** |
| `class CreateEditorNotifier extends Notifier<CreateEditorStateV2>` | **`Notifier<CreateEditorState>`** |
| `ContentPublishDraftComposite` typedef | 指向 **`CreateEditorState`** |
| 特性键 `create_editor_v2` | **删除**；统一使用 metadata 已存在键 **`enable_unified_create_editor`**（见 §5.2） |

**约束**：**禁止**在新代码中使用 `V2`、`v2`、`*V*` 作为类/typedef/文件名版本后缀；记录符号在迁移 PR 中一次性替换。

### 5.2 特性开关

- **客户端**：仅依赖 **`enable_unified_create_editor`**（`contracts/metadata/content/post/ui_config.yaml` + codegen）；**已移除** `create_editor_v2` 与 `CreateEditorStateV2` 等版本后缀命名。
- **回滚**：通过 `enable_unified_create_editor` 灰度；若需更细粒度，在 **metadata 新增独立键**（命名仍**禁止**含 `v2`）。

### 5.3 WYSIWYG、低心智层次与卡片侵入式

- **编辑块渲染**与 **发布预览** 共用 **同一套块布局组件**（或共享 layout delegate）；卡片圆角/边距使用 **DesignSemanticConstants / AppSpacing**。
- **环绕**：编辑态使用与阅读态一致的 **横向分栏结构**（图固定宽 + 文本 `Expanded` 或与 `ArticleWrappedParagraph` 测量一致）。
- **低心智文本层级**：对用户仅暴露 **正文 / 小标题 / 大标题** 三档；内部才映射到具体 block type / 字号层级，避免用户理解 H1/H2。
- **节奏 token**：冻结三档垂直节奏  
  - `T1`：行内换行  
  - `T2`：正文段落、图片与上下文、图与图之间  
  - `T3`：章节级停顿（大标题前后）  
  图片与上下文间距 = `T2`，作为默认长文美感基线。

### 5.4 顶栏与主视口：编辑 / 预览（冻结，可开发）

> **替代**原「卡片 ↔ 瀑布流」占位 IA；与 `spec.md` §4、§7.3–§7.5 同源。

#### 5.4.1 设计目标

| 模式 | 用户心智 | 主视口 | 顶栏控件 |
|------|----------|--------|----------|
| **编辑** | 像高品质 iOS 长文创作器 | 纵向滚动、多「纸页」堆叠；每页可编辑 | 紧凑 **编辑** 选中态；底栏工具栏 **可见** |
| **预览** | 像作品沉浸浏览器里读长文 | 横向翻页、全页只读 | 紧凑 **预览** 选中态；底栏 **隐藏或极简**（避免与沉浸冲突） |

- **单一文档真相**：两种模式共用同一 `CreateEditorState.articleDocument`。  
  - **统一 page slice 真相**：先由 `ArticleFlowLayoutEngine` 产出 **有序 flow runs** 与测量高度，再按统一 page metrics 切出 **page slices**。  
  - **编辑（纵向）**：以这些 page slices 组成纵向纸页列表，每页**同尺寸可编辑**。  
  - **预览（横向）**：使用相同 page slices 只读展示；**横向页数不随文内图张数 1:1 增长**。  
  - **状态回跳**：切回编辑时可回到当前 slice 对应页；若需要兼容旧逻辑，允许将 `activeArticlePageId` 映射回 page slice id，而不是退回“结构页专用 id”。
- **iOS 高品质**：控件使用 **Cupertino** 语义（`CupertinoTheme`、`CupertinoColors.separator`、毛玻璃顶栏与现 `_buildImmersiveArticlePage` 一致）；**禁止** Material `TabBar` 作为顶栏主切换终态。

#### 5.4.2 顶栏布局（`create_page` 沉浸文章，对齐图片编辑器）

- **删除**独立第二行 `CupertinoSlidingSegmentedControl`（现「卡片 / 瀑布流」整块 `Padding`）。
- **新增** `编辑 | 预览`：**宽度紧凑** 的分段控件（`CupertinoSlidingSegmentedControl` **小号**或 **两个 `CupertinoButton` 图标+`Semantics`**），放在 **导航栏 `middle`/`trailing` 与「草稿」「下一步」同一 `Stack` 行内** 或 **标题右侧**，保证 **不增加** `toolbarHeight` 之外的 **第二行专高**。
- **文案**：走 `UITextConstants` / arb；无障碍：`Semantics(label: …, toggled: …)`。
- **质感参考**：按钮层级、主 CTA「下一步」、毛玻璃/阴影/底分隔需与图片编辑器页面同档；避免“顶部只是功能按钮排一排”的低保真实现。

#### 5.4.3 编辑态：Word 式纵向分页（与预览同页尺寸）

- **结构**：`CustomScrollView` + `SliverPadding` + 多个 **「纸页」`SliverToBoxAdapter`**（或 `ListView.builder` 按页 item），页与页之间 **竖向间隙**（`AppSpacing.interGroupSm` 量级）表达分页。
- **单页 chrome**：
  - **页眉**：顶边距内一条或多行（可占位标题缩写、章节名或模版字段，**产品可先做轻量占位**）。
  - **内容区**：现有 `ArticleEditor` 单页画布逻辑 **嵌入** 纸内（WYSIWYG、环绕、块卡片）。
  - **页脚 + 页码**：底区 hairline 上显示 **当前页 / 总页数**（与 `articlePages.length` 一致）。
- **页尺寸**：**页宽 = 屏宽 − 水平安全区 − 编辑区左右 inset**；**页高**与预览态使用同一 page metrics，禁止编辑态自定义另一套“无限高轻量页”。
- **外框**：**去掉**当前包裹整列编辑区的 **粗容器边框**；仅 **每张纸** 保留 **细边框 + 轻阴影**（token：`AppColors` 分隔/表面、`AppSpacing.hairline`），其视觉强度略弱于预览态纸面。

#### 5.4.4 预览态：侵入式媒体浏览器一致 + 翻书动效

- **对标代码**：`quwoquan_app/lib/ui/discovery/widgets/works_immersive_viewer.dart`（宿主 `UnifiedMediaViewerPage`：`quwoquan_app/lib/ui/content/pages/unified_media_viewer_page.dart`）。  
- **背景**：预览主区域背景与作品沉浸 **同级深色或纸感二选一**（建议：**深底 + 纸页浮起** 与现网文章在 works 中阅读一致 —— 以 **产品截图对齐** 为准；design 默认 **与 `AppColors.worksBackground` / 沉浸条渐变可类比**）。
- **手势**：横向 **整页** 切换；**跟手滚动** + **速度阈值翻页**；边缘可保留 **轻微弹性或页码点**（与 `PageView` + 自定义 `physics` 或 `ScrollPhysics` 对齐现网沉浸条）。
- **翻书动效（终态要求）**：
  - **禁止**仅使用默认 `PageView` **无动画**切换作为唯一表现。
  - **推荐实现路径**（按工程成本选其一，PR 中注明）：
    1. **`PageView` + 自定义 `transform`**：按 `ScrollPosition` 的 `page` 小数部分对 **当前页/相邻页** 施加 **绕垂直轴旋转**（透视 `Matrix4`）+ 轻微 **阴影梯度**，模拟 **铰链翻页**（注意性能：每帧仅 2～3 页）。
    2. **`Transform` + `AnimationController`**：在 `onPageChanged` 间插 **自定义 240–320ms** `easeOutCubic` 翻页曲线（简化版「卷曲」）。
  - **前翻 / 回翻**：两方向都必须成立；不得只实现“向前翻”而回退时退化为普通滑动。
  - **回退**：若低端机帧率不达标，**feature 或动态降级**为短 **`CupertinoPageTransition`** 风格滑动（仍优于硬切），并在 observability 记录降级原因（可选）。

#### 5.4.5 与「图片编辑 — 下一步」全页一致

- **导航条**：与沉浸创作顶栏 **同一 `BackdropFilter` + 底部分隔线** 配方；`下一步` **强调色**、字重与 `create_page` 现 `_buildImmersiveArticlePage` 右对齐 **一致**。
- **预览态** 若展示顶栏，**返回/关闭** 与 **模式切换** 的触控热区 ≥ 44pt。
- **底栏**：编辑态保持 **文章 accessory 工具栏**；预览态 **收起** 或与沉浸浏览器 **底部互动条高度不冲突**（预览以 **阅读** 为主，**不**展示完整五项编辑工具）。

#### 5.4.6 状态与实现锚点

| 状态键（建议） | 类型 | 说明 |
|----------------|------|------|
| `articleEditorSurfaceMode` | `enum { edit, preview }` | 可挂在 `CreateEditorState` 或 `create_page` 局部 `State`，持久化策略：仅内存或随草稿 JSON（product 定）。 |
| 分页 | `articlePages` | 两种模式 **同一列表**；预览 `PageController` 初始 `jumpToPage(activeIndex)`。 |

- **移除**：`_immersiveArticleCardLayout` 布尔及 UI；迁移测试 `TestKeys` 若依赖旧切换需更新。

#### 5.4.7 测试与验收映射

- **T1**：`article_pagination_engine_test.dart`（`contentHeightOverride`、长文后通栏图页序）。  
- **T2**：`article_edit_preview_chrome_widget_test.dart`（预览 `PageView` + `TestKeys.articlePreviewBookPager`；纵向编辑 `ListView`）；顶栏单行与预览无 accessory 由 `create_page` 分支保证。  
- **T3**：沿用既有 provider / `article_editor_wysiwyg` 测；编辑↔预览文档一致可专测增量。  
- **T4**：Patrol 留待专 CR（见 §9）。  
- **门禁**：`create_page` 变更同步 **page-horizontal-quality** 矩阵与 P2 清单。

---

### 5.5 Undo / Redo

- **范围**：当前草稿文档内的文本与结构变更（插入块、改样式、改环绕等）。
- **与面板**：undo/redo **不强制**关闭 accessory 面板；若实现导致焦点丢失，在实现中 **最小化** 副作用并记录在 PR。

### 5.6 文内图：内容区宽度、半宽、caption 与工具栏（落实 spec §8）

- **内容区宽度**：在 `article_editor` / `article_paged_canvas` / 卡片内容容器内，用 **父级传入的 `maxWidth` 或 `LayoutBuilder`** 得到 `contentWidth`；**半宽** `imageColumnWidth = contentWidth * 0.5`（或与 `AppSpacing` 断点组合的离散档位，但须等价于「内容区 50%」语义）。  
- **禁止**：在未减去水平 padding 的 **屏幕全宽** 上乘系数作为环绕图宽（除非文档区全宽即内容区，且已文档化）。  
- **高度**：`displayHeight = imageColumnWidth / intrinsicAspectRatio`，`BoxFit.contain` 或等价；若环绕列与图块竖直 **视觉不齐**，允许在 **±少量逻辑像素** 内调整 **列高/内边距** 或 **图框高度**（不改变存储中的像素比），以满足 spec §8.2 / §8.4。  
- **配图说明**：说明区计入 **图块总高度**；下方正文 `padding`/`margin` 的 **顶边** 从 **说明区底** 起算。空说明 **不占高**；编辑态、预览态、测高函数共享这一规则。  
- **对齐**：caption 统一 **居中对齐**。  
- **编辑入口**：caption 优先通过 **图片工具栏** 编辑；画布不保留长期空输入框。  
- **图片工具栏**：以 `selectedAssetId` 为唯一锚点，选中图片必显，支持 `fullWidth / wrapLeft / wrapRight / caption / remove`。  
- **阅读/编辑共享**：与 `ArticleWrappedParagraph` 抽 **同一宽度/高度计算函数**（或 `ArticleWrapLayoutDelegate`），避免编辑与详情页漂移。

---

## 6. metadata / codegen 方案

- **新增或扩展**（按载荷需要逐项落地，顺序：`fields` / `service` / `post` 相关 schema）：
  - 块类型（段落、标题、列表项、图片+段落等）。
  - 行内样式与对齐的序列化（如受限 JSON 或 markdown 子集，**唯一真相在 metadata**）。
  - 列表层级上限（3）与校验规则。
  - 图片布局枚举（与现有 `wrapLeft` / `wrapRight` / `fullWidth` 对齐并**契约化**）。
- **命令**：`make -C quwoquan_service verify-metadata` → `make codegen` → `make codegen-app`。

### 6.1 端云发布与媒体链路（Remote）

- **createPost**：`RemoteContentRepository.createPost` → `POST` `ContentApiMetadata.createPostPath`；请求头 `CloudRequestHeaders.forPage(ContentRequestPageIds.createPost)`；body 为 `create_page.dart` 中 `_buildCreatePayload` 经 `_attachActivePersonaContext` 合并后的 Map。
- **publishPost**：`POST` `ContentApiMetadata.publishPostPath(postId:)`；请求头 `CloudRequestHeaders.forPage(ContentRequestPageIds.publishPost)`；body 为 `PublishSettings.toPayloadFields()`（与确认弹窗一致）。
- **文章载荷**：`contentType=article` 时包含 `articleDocument`（`ArticleDocumentData.toMap()`）、`articleTemplate`、`articleFontPreset`、`articlePages`、`articleBlocks`、`cards`、`mediaUrls`、`coverUrl` 等，**仅**发送与 `contracts/metadata/content/post/service.yaml` 中 `writable_fields` 及 `article_document_schema.yaml` 一致的形状；禁止在 UI 维护第二套 path/字段表。
- **错误语义**：HTTP 响应经 `CloudResponseDecoder`；用户可见文案使用 metadata/codegen 错误枚举（见仓库 error-permission 与 `cloud/runtime/error_codes.dart`），禁止硬编码业务错误码字符串。
- **媒体路径**：文内图与封面经 `MediaPicker` / `replaceArticlePageImage` 等写入 **本地文件路径** 至 `mediaUrls` 与 `articleDocument.assets[].imageUrl`；公网 URL 回填由 **服务端或后续统一上传管线** 完成（与既有图文帖一致）；本 L3 不在客户端新增平行的第二套上传 API 约定。

---

## 7. 字段演进、迁移与兼容

- **本地草稿**：`SharedPreferences` / 现有 JSON 若含旧字段名，在 **反序列化** 时做 **单点迁移**（读完即写回新格式），**不**长期保留 `V2` 命名。
- **双读双写**：仅在迁移窗口需要；目标为 **单格式**，窗口结束删除旧路径。

---

## 8. feature flag、观测、SLO 与回滚

- **Flag**：`enable_unified_create_editor` 为主开关；文章编辑器子能力可再拆键（metadata 登记）。
- **观测**：保留/补充 `create_editor_ready`、发布成功/失败等事件；大文档滚动帧率可设预算（在实现阶段定具体指标）。
- **回滚**：关 `enable_unified_create_editor` 回退到统一编辑器关闭路径（需与产品确认「关闭」时的 UX：降级为旧 UI 或拦截入口）。

---

## 9. TDD / ATDD 策略

- **T1**：模型与序列化单测（块、span、列表深度、undo 栈）；**分页**：`quwoquan_app/test/ui/content/article_pagination_engine_test.dart`（`contentHeightOverride` 传递、长文后通栏图落到后续页）。
- **T2**：Widget：底栏布局、面板切换、undo/redo 禁用态；**编辑/预览**：`quwoquan_app/test/ui/content/entry/article_edit_preview_chrome_widget_test.dart`（`ArticlePreviewBookPager` 的 `PageView` + `TestKeys.articlePreviewBookPager`；`ArticleEditor` `articlePageLayoutAxis: vertical` 时 `ListView`、无 `PageView`）。
- **T3**：集成：沉浸文章创建 → 改环绕 → 预览 → 发布载荷契约（沿用既有 `article_editor_wysiwyg_widget_test` / provider 测；模式切换与文档一致性可在后续补 `create_page` 泵测）。
- **T4**：E2E（Patrol）：**本切片不登记 uat**；创作 → 顶栏切预览 → 横向翻页 → 回编辑 留待专 CR 与 `test/patrol` 路径补齐。

---

## 10. plan slice 与 T1~T4 映射

| Slice（见 `plan.yaml`） | T1 | T2 | T3 | T4 |
|-------------------------|----|----|----|----|
| metadata-codegen | ✓ | | | |
| rename-state-and-flag | ✓ | ✓ | | |
| document-model-undo | ✓ | ✓ | ✓ | |
| accessory-toolbar-panels | | ✓ | ✓ | |
| wysiwyg-canvas-wrap | | ✓ | ✓ | ✓ |
| edit-preview-chrome | ✓ | ✓ | ✓ | （Patrol 可选，后续 CR） |
| gates-cross-cutting | | ✓ | ✓ | ✓ |

---

## 11. 未来演进

- 协同编辑、评论锚点、版本记录 **不在**本 L3 范围。
- 若引入方案 B 富文本库，应作为 **独立 CR** 评估与迁移。

---

## 12. 助手链路

- **本次变更**：不涉及 Personal Assistant；无需引用 PA 三类核心文档。

---

## 13. 真相源映射

| 主题 | 真相源 |
|------|--------|
| 字段与 API | `contracts/metadata` |
| UI 文案 | `UITextConstants` / `lib/l10n` |
| 特性键 | `content/post/ui_config.yaml` + codegen |
| 页面横切 | `page-horizontal-quality-matrix.md`、`metadata_driven_ui_gap_inventory.yaml` |
| 文内图环绕与尺寸 | `spec.md` §8；本设计 §5.6 |
