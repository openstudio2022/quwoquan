# WP7 · 精品页统一（端侧，小包）

> 树归属：`discovery-content/content-display-journey-consistency`
> 影响 Journey：`content-discovery-to-consumption`、`immersive-media-edge-swipe-back`
> 验收意图：GWT；测试证据：T2

## 1. 背景与现状

- 移动端精品已收口统一沉浸 viewer（`lib/ui/discovery/widgets/works_immersive_viewer.dart`，3622 行（基线修正收藏退场后从 3659 降至 3622））：四类画布（图片/视频/文章 Dark Paper/纯文本）、默认深色沉浸、格式筛选（`ContentUIConfig.workFormatFilters`：all/image/video/article）、交集理由 sheet、统一互动栏。
- 缺口：
  - **Web 宽屏「精品」退化**为普通发现流（`web_main_app_shell.dart` `_WebFeaturedWorkspace`），与移动端不同源；
  - 筛选维度只有格式（image/video/article），无长文细分、无垂类（contentVertical）维度；
  - 无「实体专题 / 圈子精选」入口位（规格 §8 内容类型）；
  - 旧详情页已删除（photo/video/article_detail_page），统一入口 `work_browser_entry_page.dart` + `single_post_media_viewer.dart` 已就绪。

## 2. 功能规格

### 2.0 统一概念基线（已达成现状 + 防回归）

> 「无收藏入口」已由基线修正会话在全产品达成（精品 viewer 内收藏按钮/计数/动画已删），本节按防回归口径执行：

- 精品页「无收藏入口」为全产品主线现状：内容消费互动只有 `点赞 / 评论 / 转发`，内容不提供任何长期动作入口。
- 本包后续扩展操作面板也不得引入 `收藏 / 关注内容 / 稍后看`；长期连接动作只出现在对象上（关注作者、关注实体、加入圈子）。
- 精品页展示的交集与影响说明只用六个母表达与连接型口径：`共同讨论`、`建立新连接`、`来自XX圈`。

### 2.1 Web 精品同源

- Web 宽屏精品与移动端同源消费精品队列（沉浸 hero + 队列），或在细化会话内冻结一份明确的宽屏降级规格（栅格 + 点击进沉浸）；二选一定稿后写入 `content-display-journey-consistency` spec，禁止维持「无规格的退化」现状。

### 2.2 筛选 metadata 化扩展

- `workFormatFilters` 闭集评估扩展：保持 all/image/video/article，评估新增 `长文`（article 细分）与垂类（`contentVertical`）维度；结论无论增减都经 `contracts/metadata/content/post/ui_config.yaml` → `make codegen-app`，端侧禁止硬编码筛选项。
- 筛选入口保持「更多操作」弹层统一，不在阅读视野常驻工具（§20.6 内容优先）。

### 2.3 实体专题 / 圈子精选入口

- 精品流内插入「实体专题 / 圈子精选」卡位（运营配置驱动，经 ui_config 的模块策略，对齐首页 `intersection_module_policy` 的配置模式）；点击进入对应对象主页或聚合页。
- 前台文案不出现「实体」（用对象名/「专题」）。

### 2.4 体验核验

- 深色沉浸核验（状态栏、文章画布强制 dark）与边缘滑动返回回归（`immersive-media-edge-swipe-back` journey 测试保持绿）。
- R03 警戒：`works_immersive_viewer.dart` 现 3622 行（行数 ratchet 基线已登记 `specs/gates/file_line_budget_allowlist.yaml`，只减不增），本包新增能力必须拆出子文件，总行数只减不增。

## 3. 周边契约

- 筛选闭集与模块卡位配置唯一真相源：`contracts/metadata/content/post/ui_config.yaml`。
- 不改 feed API；专题卡位数据消费既有 feed/对象读模型。
- 与 WP2 边界：`works_immersive_viewer.dart` 与 Web 壳精品区归本包；发现页瀑布流与 spotlight 归 WP2。

## 4. 改动范围

- `quwoquan_app/lib/ui/discovery/widgets/works_immersive_viewer.dart`（+拆分出的子文件）
- `quwoquan_app/lib/app/shell/web_main_app_shell.dart`（精品 workspace 部分）
- `contracts/metadata/content/post/ui_config.yaml` + codegen
- 对应 widget 测试

## 5. 准出要求

1. T2：筛选项渲染与 metadata 一致性测试（codegen 常量驱动）。
2. T2：Web 精品按定稿规格渲染测试；移动端四画布回归。
3. 专题/精选卡位配置驱动测试（配置开→显示，关→不显示）。
4. `works_immersive_viewer.dart` 行数不增加；`bash agent_ops/gate/gate_repo.sh --scope app` 全绿。
5. `content-display-journey-consistency` spec 同步修订。

## 6. 验收标准（GWT 样例）

- Given 移动端与 Web 同一账号打开精品，Then 两端体验同源（或符合冻结的宽屏降级规格），筛选项一致且来自 metadata。
- Given 运营配置开启「圈子精选」卡位，Then 精品流出现该卡位且点击进入圈子主页；关闭后不出现。
- Given 深色环境阅读文章画布，Then 全程沉浸无白闪，工具入口不遮挡正文。
