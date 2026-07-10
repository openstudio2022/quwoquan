# WP7 · 精品页统一（端侧，小包）

> 树归属：`discovery-content/content-display-journey-consistency`
> 影响 Journey：`content-discovery-to-consumption`、`immersive-media-edge-swipe-back`
> 验收意图：GWT；测试证据：T2

## 1. 背景与现状

- 移动端精品已收口统一沉浸 viewer（`lib/ui/discovery/widgets/works_immersive_viewer.dart`，3622 行（基线修正收藏退场后从 3659 降至 3622））：四类画布（图片/视频/文章 Dark Paper/纯文本）、默认深色沉浸、格式筛选（`ContentUIConfig.workFormatFilters`：all/image/video/article）、交集理由 sheet、统一互动栏。
- Web 宽屏精品已完成商用收口：`web_main_app_shell.dart` 中 `_WebFeaturedWorkspace` 明确采用「发现内容流多列墙 + 点击进入统一沉浸 viewer」的宽屏降级规格，filter 映射固定为 `all -> work / image -> photo / video -> video / article -> article`；不再维护「精品队列」hero/rail。该口径已有 `web_featured_no_queue_test.dart`、`main_app_shell_widget_test.dart` 与页面矩阵 2026-06-06 记录守护。
- `workFormatFilters` 基础闭集已完成 metadata → codegen → Web/Mobile 消费闭环：真相源为 `contracts/metadata/content/post/ui_config.yaml#work_format_filters`，生成 `ContentUIConfig.workFormatFilters`，当前闭集为 `all/image/video/article`，由 `post_ui_config_contract_test.dart` 守护。
- 旧详情页已删除（photo/video/article_detail_page），统一入口 `work_browser_entry_page.dart` + `single_post_media_viewer.dart` 已就绪。
- 真实缺口：
  - 「实体专题 / 圈子精选」卡位尚未落地 metadata、UI 与测试闭环，本轮默认后置为 convergence item；如明确启用 WP7 Plus，再按 §2.3 执行。
  - Work Browser 输入边界仍是 `rawPostsById + PostBaseDto -> WorkBrowserItemDto` 兼容态，尚未纯化为 `WorkBrowserItemDto` 单一输入真相源；该项后置到持续收口，不阻断 WP7 Core。

## 2. 功能规格

### 2.0 统一概念基线（已达成现状 + 防回归）

> 「无收藏入口」已由基线修正会话在全产品达成（精品 viewer 内收藏按钮/计数/动画已删），本节按防回归口径执行：

- 精品页「无收藏入口」为全产品主线现状：内容消费互动只有 `点赞 / 评论 / 转发`，内容不提供任何长期动作入口。
- 本包后续扩展操作面板也不得引入 `收藏 / 关注内容 / 稍后看`；长期连接动作只出现在对象上（关注作者、关注实体、加入圈子）。
- 精品页展示的交集与影响说明只用六个母表达与连接型口径：`共同讨论`、`建立新连接`、`来自XX圈`。

### 2.1 Web 精品同源

- Web 宽屏精品规格冻结为**宽屏发现内容墙 + 统一沉浸浏览落点**，不是独立精品队列：
  - `featured/all` 渲染 `work` 频道；
  - `featured/image` 渲染 `photo` 频道；
  - `featured/video` 渲染 `video` 频道；
  - `featured/article` 渲染 `article` 频道；
  - 内容列表复用 `HomeMultiFormFeed`，post 点击统一走 `openHomeFeedPost(...) -> workBrowser -> WorksImmersiveViewer`。
- 禁止回退到「精品队列」hero/rail；如未来要重启独立精品容器，必须另起 CR 更新页面矩阵、测试基线与本规格。

### 2.2 筛选 metadata 化扩展

- `workFormatFilters` 当前闭集冻结为 `all/image/video/article`；本轮不默认扩展 `长文`（article 细分）或垂类（`contentVertical`）。
- 如未来需要新增 `longform` 或垂类筛选，必须单独冻结产品口径，经 `contracts/metadata/content/post/ui_config.yaml` → `make codegen-app` → Web/Mobile 同源消费 → 契约测试更新；禁止端侧硬编码筛选项。
- 筛选入口保持「更多操作」弹层统一，不在阅读视野常驻工具（§20.6 内容优先）。

### 2.3 实体专题 / 圈子精选入口

- WP7 Core 不落地专题/精选卡位，仅在 CR 与集成清单显式登记为 convergence item。
- 若明确启用 WP7 Plus，再按以下规格实施：精品流内插入「专题 / 圈子精选」卡位（运营配置驱动，经 `ui_config.yaml` 的模块策略，对齐首页 `intersection_module_policy` 的配置模式）；点击进入已有对象主页或圈子主页 route；配置开→显示，配置关→不显示；前台文案不出现「实体」（用对象名/「专题」）。

### 2.4 体验核验

- 深色沉浸核验（状态栏、文章画布强制 dark）与边缘滑动返回回归（`immersive-media-edge-swipe-back` journey 测试保持绿）。
- R03 警戒：`works_immersive_viewer.dart` 现 3622 行（行数 ratchet 基线已登记 `specs/gates/file_line_budget_allowlist.yaml`，只减不增），本包新增能力必须拆出子文件，总行数只减不增。

## 3. 周边契约

- 筛选闭集唯一真相源：`contracts/metadata/content/post/ui_config.yaml#work_format_filters`；当前闭集不扩。
- WP7 Core 不新增 metadata 字段；如启用 WP7 Plus，模块卡位配置唯一真相源同样放在 `contracts/metadata/content/post/ui_config.yaml`，不新造平行配置文件。
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
3. WP7 Core 不要求专题/精选卡位测试；若启用 WP7 Plus，必须补配置驱动测试（配置开→显示，关→不显示，点击→既有对象页 route）。
4. `works_immersive_viewer.dart` 行数不增加；`bash quwoquan_ops/gate/gate_repo.sh --scope app` 全绿。
5. `content-display-journey-consistency` spec、`works-immersive-viewer/acceptance.yaml`、`90-integration-acceptance.md` 与 CR dev_log 同步修订。

## 6. 验收标准（GWT 样例）

- Given 移动端与 Web 同一账号打开精品，Then Web 符合冻结的宽屏多列墙降级规格，移动端符合 Work Browser V1 规格，二者筛选项同源来自 `ContentUIConfig.workFormatFilters`，post 点击均进入 `workBrowser`。
- Given 打开 Web 精品页，Then 不出现「精品队列」hero/rail/队列文案，默认 `all` 渲染 `web-content-feed-work`。
- Given WP7 Plus 未启用，Then 「专题 / 圈子精选」卡位作为 convergence item 登记，不计入 WP7 Core done_when；若启用，Then 运营配置开启时卡位出现且点击进入对象页/圈子页，关闭时不出现。
- Given 深色环境阅读文章画布，Then 全程沉浸无白闪，工具入口不遮挡正文。
