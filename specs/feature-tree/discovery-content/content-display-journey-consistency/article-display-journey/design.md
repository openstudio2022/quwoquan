# article-display-journey 设计

## 设计动因

`article-display-journey/spec.md` 已把文章从“post 详情页”升级为“书本化沉浸阅读旅程”，但当前实现与契约仍有四个核心缺口：

1. metadata / projection 尚未承载 `articleDocument`、`articleTemplate`、`articleFontPreset` 等 presentation 真相源，当前 app 只能依赖 raw map 和本地约定字段。
2. 发现页文章卡、圈子双列卡、沉浸式文章阅读器和编辑预览各自演进，没有统一的 distribution profile / reader profile / editor profile。
3. mock 数据仅覆盖少量 article 模板，无法稳定评测“5 套模板 x 有/无封面 x 3 种展示方式”的实际效果。
4. 用例主要覆盖当前分页与投影，不足以看护真实书页壳层、模板推荐、封面参与规则和沉浸式翻页降级。

本设计的目标是在不牺牲 metadata-first 与单一真相源的前提下，选定一套可商用落地的文章展示系统：轻量分发快照、按需水合全文、统一书本模板、真实翻页与可降级阅读器，并把 mock / 测试一起纳入正式切片。

## 上游输入评审

### 已冻结输入

- L2：`specs/feature-tree/discovery-content/content-display-journey-consistency/spec.md`
- L2 acceptance：`specs/feature-tree/discovery-content/content-display-journey-consistency/acceptance.yaml`
- L3：`specs/feature-tree/discovery-content/content-display-journey-consistency/article-display-journey/spec.md`
- L3 acceptance：`specs/feature-tree/discovery-content/content-display-journey-consistency/article-display-journey/acceptance.yaml`
- UX 基线：`specs/02_IOS_NATIVE_FRONTEND_UX_SPEC.md`
- CR：`specs/changelog/CR-20260322-002-article-book-display-prd.yaml`

### 当前代码基线评审

- App 端已具备：
  - 连续文档模型 `ArticleDocumentData`
  - 动态分页引擎
  - 模板与字体基础能力
  - 编辑 / 预览 / 详情 / 沉浸式文章的统一分页基础
- 当前缺口集中在：
  - `ArticlePostDto` 仅含 `title/body/coverUrl`
  - `content/post/projections/article_post.yaml` 未声明 `articleDocument` / `articleTemplate` / `articleFontPreset`
  - `content/post/ui_config.yaml` 只定义 article tab 为 `list_with_cover`，未定义关注流卡、圈子双列卡和书本阅读器 profile
  - mock article 数据只有少量模板，且未系统覆盖“有封面 / 无封面 / current fallback / 三种 surface”

### G1 基线结果

已执行：

```bash
make -C quwoquan_service verify-metadata
make codegen
make codegen-app
```

结果：

- metadata 校验通过
- codegen / codegen-app 基线通过
- 当前仓库具备进入 `/design` 的 metadata/codegen 基础

## 对标输入分析

| 对标 | 借鉴点 | 风险 | 本次吸收 |
|------|--------|------|----------|
| 微信读书 | 顶部 `返回 + 页码`、阅读 chrome 自动淡出、正文区域绝对优先 | 过于偏纯文本，不适合图文模板 | 吸收导航与沉浸节奏，不吸收纯文本壳 |
| Apple Books | 书页舞台、实体翻页、模板和阅读气质统一 | 动效与物理感实现复杂，低端设备成本高 | 吸收书页实体感与页角翻页，必须设计降级 |
| 小红书长图文 | 分发封面连续感、点击转场自然 | 仍偏“详情页”，阅读器沉浸不足 | 吸收封面用于分发与扉页，不吸收详情页逻辑 |
| Notion / Medium | 编辑态与阅读态共享排版心智 | 缺少“真实书本风格” | 吸收单一内容模型，不吸收网页感 |

结论：

- 文章展示必须是 `reader-first`，不是 `detail-first`。
- 顶部导航与页码要统一，但阅读器仍需保留书页舞台。
- 封面应进入阅读，但不能浪费成纯封面独占页。
- 真实翻页必须有正式降级边界，不能把高端动效写成唯一方案。

## 方案对比

### 方案 A：保留 post 详情页，只给文章套模板皮肤

描述：

- 继续沿用当前 `PageView` / card shell
- 关注流和圈子流仅微调卡片
- 模板主要作为纸纹和字体皮肤
- 不新增 metadata presentation state

优点：

- 实现成本最低
- 后端契约改动最少

缺点：

- 无法满足“真实书本体验”
- 编辑态与阅读态仍会出现第二套真相源
- 无法稳定支持封面扉页、圈子模板推荐和真实翻页

### 方案 B：统一 presentation state + 轻量分发快照 + 阅读器详情水合 + 书本阅读器

描述：

- metadata 增加文章 presentation fields
- feed projection 保持轻量，只带分发快照
- 阅读器打开后用 `GetPost` / detail payload 水合完整 `articleDocument`
- 书本模板、封面扉页、真实翻页与编辑预览共享同一 presentation state

优点：

- payload 规模可控
- presentation 真相源清晰
- 与当前连续文档模型兼容最好
- 可同时覆盖分发卡、阅读器、编辑器

缺点：

- 需要 metadata / projection / repository / renderer 一起演进
- 需要 reader hydration 与 skeleton 过渡设计

### 方案 C：服务端预切页并输出整本“文章卡组”

描述：

- 服务端负责分页与扉页排版
- feed / reader 直接消费服务端 page deck
- 客户端只负责展示与翻页

优点：

- 客户端逻辑最简单
- 页码和分页绝对一致

缺点：

- 不适配当前客户端真实测量分页模型
- 屏幕尺寸差异大，服务端分页难以保证 iPhone / 华为旗舰 / 平板一致体验
- 编辑态无法真正所见即所得

### 选型

选择 **方案 B**。

原因：

1. 与当前“连续文档模型 + 客户端真实测量分页”完全同向。
2. 可以同时满足 metadata-first、模板单一真相源、阅读器书本体验与编辑态预览一致。
3. 允许按需降级和渐进灰度，不会把高端翻页动效绑死在唯一路径上。

## 选型决策

### D1：文章 presentation state 正式进入 metadata

新增文章展示真相源，最小字段为：

- `articleDocument`：完整连续文档（canonical）
- `articleTemplate`：书本模板
- `articleFontPreset`：字体预设
- `articlePresentationVersion`：展示版本，用于后续演进和灰度
- `coverUrl`：显式封面，继续作为分发和扉页素材
- `summary`：分发摘要；无显式摘要时由 `articleDocument` 派生

不新增单独 `articleCoverMode`：

- 本期封面参与规则已冻结为“有封面即扉页式第一页”
- 不把尚未开放给作者的策略做成 metadata 可写字段，避免过早复杂化

### D2：分发快照与阅读详情分层

正式采用“双层内容载荷”：

- **分发快照**（feed / circle card）
  - `title`
  - `summary` / excerpt
  - `coverUrl`
  - `articleTemplate`
  - `articleFontPreset`
  - `articlePresentationVersion`
  - 互动计数与作者快照
- **阅读详情**（GetPost / hydrated detail）
  - `articleDocument`
  - `coverUrl`
  - `articleTemplate`
  - `articleFontPreset`
  - 互动计数与作者快照

结论：

- feed projection 不携带整本长文，避免 discovery / circle feed 被长文拖重
- reader 打开时可先用分发快照渲染首帧，再异步水合完整文档
- 若来源已持有完整 `articleDocument`（如 mock、本地草稿、缓存命中），则跳过 hydration

### D3：关注流 / 圈子 / 阅读器 / 编辑器共享同一模板系统

模板系统分 4 层：

1. `distribution profile`
2. `reader profile`
3. `editor profile`
4. `template visual token`

其中：

- `distribution profile` 决定关注流与圈子卡的布局密度
- `reader profile` 决定阅读器的舞台、边缘、书脊、翻页阻尼
- `editor profile` 决定编辑态纸张、预览与工具层如何附着
- `template visual token` 决定纸色、边缘、装订、胶带、网格等视觉风格

这 4 层都由同一 `articleTemplate` 驱动，不允许各 surface 各自维护第二张映射表。

### D4：真实翻页采用“主路径 page curl + 降级 pager”

正式实现采用两级策略：

- 主路径：页角拖拽 `page curl`
  - 四角热区
  - 可停留中间态
  - 阈值后自动完成或回弹
- 降级路径：`book-style pager`
  - 仍保留书页舞台与页边阴影
  - 取消连续 curl 形变，只保留预掀页 + 平滑翻页

触发降级的条件：

- 系统减少动态效果
- 低性能设备 / 大文档场景
- 内存或帧率监测不达标

不允许回退为普通卡片 `PageView`。

### D5：封面采用扉页式第一页，而不是纯封面屏

第一页规则固定：

- 有封面：
  - 上半区为封面
  - 下半区为标题 + 正文开头
- 无封面：
  - 直接标题 + 正文

这样兼顾：

- 分发连续性
- 阅读节奏
- 扉页仪式感

并废弃旧探索节点中的“纯封面第一页 + 正文从第二页开始”的默认前提。

### D6：圈子频道推荐模板，但作者最终选择优先

频道推荐只承担“默认建议”，不承担最终真相。

落实方式：

- `ui_config.yaml` 提供 `circleCategory -> recommendedArticleTemplates`
- 新建文章时若作者未手动选择模板，按频道推荐回填默认值
- 已有文章的 `articleTemplate` 永远优先于频道推荐

### D7：mock 数据必须做成评测矩阵，而不是少量样例

正式 mock 范围冻结为：

- 5 套模板：`journal` / `ritual` / `diffuse` / `tech` / `gentle`
- 2 种封面状态：有封面 / 无封面
- 3 种展示方式：
  - 关注流文章卡
  - 圈子双列文章卡
  - 沉浸式阅读器 / 编辑预览

最小评测矩阵：

- `5 templates x 2 cover states = 10` 篇 canonical article seeds
- 每篇同时具备：
  - discovery/follow 分发快照
  - circle feed 分发快照
  - hydrated reader payload
- 额外补 4 类兼容样例：
  - `articleDocument` 完整新模型
  - `articleBlocks` current 回退
  - `cards` current 回退
  - `body only` 极简旧数据

总计不少于 `14` 条 article mock fixtures。

## 关键设计决策

### 1. metadata / codegen 方案

#### 1.1 metadata 变更

目标文件：

- `quwoquan_service/contracts/metadata/content/post/fields.yaml`
- `quwoquan_service/contracts/metadata/content/post/service.yaml`
- `quwoquan_service/contracts/metadata/content/post/projections/article_post.yaml`
- `quwoquan_service/contracts/metadata/content/post/ui_config.yaml`
- `quwoquan_service/contracts/metadata/_shared/types.yaml`

字段方案：

1. `fields.yaml`
   - 新增 `articleDocument`：`object`，`api_exposure: read_write`
   - 新增 `articleTemplate`：`enum`，`api_exposure: read_write`
   - 新增 `articleFontPreset`：`enum`，`api_exposure: read_write`
   - 新增 `articlePresentationVersion`：`int`，`DEFAULT_1`
   - `coverUrl` 从“普通封面”升级为“作者显式文章封面”，语义备注更新，并将 exposure 对齐到 `read_write`
2. `_shared/types.yaml`
   - 新增 `ArticleTemplatePreset`
   - 新增 `ArticleFontPreset`
3. `service.yaml`
   - `CreatePost` / `UpdatePost` / `PromotePostToWork` writable_fields 增加：
     - `articleDocument`
     - `articleTemplate`
     - `articleFontPreset`
     - `articlePresentationVersion`
   - `UpdatePostSettings` 扩展为允许发布后更新 presentation fields：
     - `coverUrl`
     - `articleTemplate`
     - `articleFontPreset`
     - `articlePresentationVersion`
4. `article_post.yaml`
   - feed projection 补齐：
     - `summary`
     - `articleTemplate`
     - `articleFontPreset`
     - `articlePresentationVersion`
   - `body` 在 article feed 中明确降级为 excerpt / distribution summary
5. `ui_config.yaml`
   - 新增 article 分发 profile：
     - `follow_list_with_optional_cover`
     - `circle_dual_column_with_optional_cover`
   - 新增 article reader profiles：
     - `full_screen_book_stage`
     - `top_nav_with_page_fraction`
   - 新增 article template config：
     - 模板视觉 token
     - 频道默认推荐
   - 新增 feature flags：
     - `enable_article_book_reader`
     - `enable_article_page_curl`

#### 1.2 codegen 产物

预期影响：

- `quwoquan_app/lib/cloud/runtime/generated/content/article_post_dto.g.dart`
- `quwoquan_app/lib/cloud/runtime/generated/content/content_metadata.g.dart`
- `quwoquan_app/lib/cloud/content/generated/content_ui_config.g.dart`

如果 codegen 暂不支持 `object` 到 typed DTO：

- 第一阶段允许 `articleDocument` 仍由 raw map 进入 `projectArticleDetailView`
- 但 metadata 必须先定义字段，确保不再由 app 侧发明第二套字段约定
- 第二阶段再扩 `codegen_app_metadata` 支持 `Map<String, dynamic>` / typed detail dto

### 2. 字段演进、迁移 / 回填与双读双写

#### 2.1 写路径

新写入：

- `articleDocument` 为 canonical
- `summary` 为分发摘要
- `coverUrl` 为显式封面
- `articleTemplate` / `articleFontPreset` / `articlePresentationVersion` 为展示真相源

兼容派生：

- `body` 继续写入摘要或正文开头，用于旧 projection / 搜索 / current UI
- 不再新写 `cards` / `articlePages` 作为 canonical；仅允许在 app payload 中作为兼容过渡字段保留一轮

#### 2.2 读路径

读取优先级：

1. `articleDocument`
2. `articleBlocks`
3. `cards`
4. `body`

presentation 读取优先级：

1. `articleTemplate` / `articleFontPreset`
2. 频道推荐默认
3. app 默认值 `gentle + clean`

#### 2.3 回填

旧文章回填规则：

- 有 `articleBlocks`：转为 `articleDocument`
- 有 `cards`：合成 `articleDocument`
- 仅有 `body`：生成单段 document
- `coverUrl` 为空时不自动用正文首图顶替；旧数据保持无封面
- 未设置模板：回填 `gentle`
- 未设置字体：回填 `clean`
- `articlePresentationVersion` 回填 `1`

#### 2.4 双读双写退出条件

退出 current fallback 的前提：

- T3 / T4 验证完成
- 线上 `articleDocument coverage >= 95%`
- `cards/articleBlocks/body-only` reader fallback 触发率低于 guardrail

### 3. 客户端结构方案

#### 3.1 分发卡

- 关注流：复用 `post_preview_list_tile.dart` 系列骨架，新增 article-specific profile
- 圈子双列：复用 `PostPreviewCard` 骨架，新增无封面文字卡变体
- 卡片是否有封面只由 `coverUrl` 判定，不看正文图片

#### 3.2 阅读器

- 沿用 `works_immersive_viewer.dart` 作为壳层归属
- 新增 article-specific reader shell：
  - 顶部统一阅读导航
  - 书页舞台
  - reader hydration
  - page curl / fallback pager

#### 3.3 编辑态

- 编辑入口继续归 `ui/content/entry/`
- 编辑器增加封面、模板、字体正式设置区
- 预览页与阅读器共用同一 `ArticleCanvasMetrics` / `ArticleTemplatePreset`

### 4. mock 数据方案

mock 文件：

- `quwoquan_app/lib/cloud/services/content/mock/content_mock_data.dart`
- 必要时新增 `quwoquan_app/lib/ui/content/mock/article_book_mock_matrix.dart`

mock 规则：

- discovery article data 中必须至少覆盖 10 篇模板样本
- circle feed items 中必须把这 10 篇文章按频道分散映射，保证频道推荐可见
- editor preview fixtures 中必须覆盖：
  - 有封面/无封面
  - 长文/短文
  - 图文混排/纯文字
  - current fallback

评测视图要求：

- 关注流能直接看到全部模板的有/无封面样本
- 圈子频道至少在人文、科技、旅行、生活四类频道中看到对应推荐模板
- 沉浸式阅读器与编辑预览能直接切换全部模板，无需现写现编

### 5. 用例看护方案

#### T1

- metadata schema test：
  - `articleTemplate` / `articleFontPreset` / `articleDocument` 字段存在
- codegen contract test：
  - `ArticlePostDto` 和 `content_ui_config.g.dart` 产物含新增字段
- projection fallback contract：
  - `articleDocument`、`articleBlocks`、`cards`、`body` 四路回退顺序正确

#### T2

- `article_feed_list_tile_widget_test.dart`
  - 有封面 / 无封面
  - 标题 / 摘要行数限制
- `article_circle_card_widget_test.dart`
  - 双列有封面卡 / 无封面文字卡
  - 频道推荐模板样式映射
- `article_reader_shell_widget_test.dart`
  - 顶部 `返回 + 页码`
  - 封面扉页
  - 书页舞台不侵入工具栏
- `article_editor_template_preview_widget_test.dart`
  - 模板切换
  - 封面开关
  - 编辑预览和阅读页一致

#### T3

- repository / projection integration
- `GetPost` hydration integration
- Mock / Remote 一致性

#### T4

- 关注流 article -> reader -> profile -> back
- 圈子双列 article -> reader -> profile -> back
- 有封面与无封面两条旅程各至少 1 条

### 6. feature flag、观测、SLO 验证与回滚

#### feature flags

- `enable_article_book_reader`
  - 控制阅读器壳层切换
- `enable_article_page_curl`
  - 控制真实翻页
- `enable_article_distribution_profiles`
  - 控制关注流与圈子文章新卡片

#### observability

- `article_reader_open_ms`
- `article_reader_hydration_ms`
- `article_page_flip_commit_ms`
- `article_page_curl_abort_rate`
- `article_reader_fallback_rate`（非主文档来源时 `reason` 形如 `document_structure:<source>:hydrated=<bool>`）
- `article_template_render_error_rate`

#### SLO 验证

- reader 首帧
- hydration 延迟
- 翻页帧率
- 模板切换刷新

#### rollback

1. 关闭 `enable_article_page_curl`，保留书页壳层
2. 关闭 `enable_article_book_reader`，回退当前稳定分页壳
3. 关闭 `enable_article_distribution_profiles`，回退旧 article card

## TDD / ATDD 策略

- 先补 metadata / projection / ui_config contract tests，再进入代码实现
- 先做 mock matrix，再做 reader shell，保证评测与验收并行推进
- page curl 采用 `Red -> Green -> degrade -> optimize` 策略：
  - 先让 fallback pager 过验收
  - 再叠加 curl 主路径
  - 最后做性能降级与减少动态效果

## Plan Slice 与 T1~T4 证据矩阵映射

| Slice | 核心内容 | acceptance | 证据 |
|------|----------|------------|------|
| P1 | metadata / UI config 冻结 | A3 A4 A6 A7 | T1 |
| P2 | codegen 基线与 DTO/UIConfig 产物 | A6 A7 A8 | T1 |
| P3 | mock matrix 与 projection fallback | A1 A2 A7 A8 | T1 T2 |
| P4 | 关注流 / 圈子双列文章卡 | A1 A2 A8 | T2 T4 |
| P5 | reader shell / hydration / 顶部导航 | A3 A4 A5 A8 | T2 T3 T4 |
| P6 | page curl / template edge / degrade | A3 A5 A7 | T2 T4 |
| P7 | 编辑态 presentation settings 对齐 | A4 A6 A7 | T2 T3 |
| P8 | 全链路验证、观测、灰度与回滚 | A1-A8 | T1 T2 T3 T4 |

## 未来演进

- 平板横屏双页展开与对开书脊模式
- 作者自定义模板资产包
- 模板级音效 / 触感策略
- 文章阅读进度同步与书签能力
