# WP2 · 发现页交集呈现与内容卡统一（端侧）

> 树归属：`discovery-content/dual-rail-discovery-redesign` + `object-homepage-network/intersection-unified-experience`
> 影响 Journey：`content-discovery-to-consumption`、`content-feed-open-detail`
> 验收意图：GWT + SIT；测试证据：T1 / T2

## 1. 背景与现状

- 首页结构（`lib/ui/discovery/pages/home_page.dart` + `widgets/home_multi_form_feed.dart`）：搜索 chrome → 频道导航 → 交集 spotlight（headerSliver + 段间插入）→ 瀑布流，与规格一致。
- 双列内容卡（`widgets/dual_column_discovery_post_card.dart`）：图 → 交集理由 chip → 标题 → 作者+点赞，**已符合规格**（理由在图下，非覆盖图上）。
- spotlight（`widgets/intersection_spotlight_module.dart`）：单屏 3.35 卡、名称黑粗 / 主交集蓝 / 副交集灰 三行，**已符合规格**。
- 缺口：
  - 上述符合项**无契约测试固化**，存在回归风险；
  - `weightTier`（light/heavy，70/20/10 频率契约）字段已定义但端侧未消费，内容卡无轻重分化；
  - 双列卡只取 `reasons.first` 一条 primaryText（保持，规格要求展示结论不堆砌）；
  - 主交集蓝/副交集灰的颜色未全部 token 化核验。

## 2. 功能规格

### 2.0 统一概念基线（已落地基线，引用词典；本包防回归）

> 以下基线已由「持续连接基线修正」会话在全仓落地（含 `discovery_page.dart` 收藏入口/收藏动画/AuthGateReason.favorite 全部删除），本包按**防回归**口径执行，不再作为待办：

- 内容卡主互动**只有** `点赞 / 评论 / 转发` 三件套；内容不提供任何长期动作入口（无收藏、无关注内容、无稍后看），发现页所有内容消费面同此约束。
- 持续连接只针对对象：关注人 / 关注实体 / 加入圈子；「以后再看」由 `我的足迹`（自动记录，私有）承载，本包不为其新增入口。
- 本包消费云侧交集理由时，只显示六个母表达口径：`共同关注的人 / 共同圈子 / 共同兴趣 / 共同地点 / 共同校友 / 共同讨论`；kind 以词典唯一注册表（`specs/product/intersection-definition-and-application.md` §5.4）为准，无兼容别名。
- 交集叙事重点是连接关系而非行为计数：优先「来自AI产品圈」「2位校友正在讨论」「与你关注的对象相关」类表达。

### 2.1 卡结构契约固化（防回归）

- Widget 测试断言双列卡渲染顺序：封面 → 交集理由（若有）→ 标题 → 作者行；断言交集理由 **不在** 封面 Stack 内部（禁止 overlay）。
- 单列关系卡断言：作者头部 → 交集 chip → 正文 → 媒体 → 互动栏。
- spotlight 断言：`visibleCardsPerViewport` ∈ [3, 3.5]；卡内文字 ≤3 行；主交集使用品牌蓝 token、副交集使用次级灰 token。

### 2.2 weightTier 轻重分化

- `heavy`：完整理由行（图标 + 蓝色 primaryText）。
- `light`：弱化形态（小图标 + 次级灰短文案），满足「内容优先」原则（§20.6）。
- `weightTier` 为空时按 `heavy` 兜底（向后兼容现状）。
- 本轮实现口径修正：`intersection_reason_chip.dart` 作为 chip 形态的同源消费点，覆盖双列卡与首页多形态 feed 的结构测试；沉浸式浏览器 / 详情页继续从云侧 reasons 直出解释层，不强行改造成 chip，从而避免把详情解释文案压缩为卡片理由位。

### 2.3 颜色与语言统一

- 交集相关颜色全部走 `AppColors` 语义 token（连接蓝 / 副文案灰）；移除任何硬编码 Color。
- chip / spotlight 文案直出云侧 `primaryText/secondaryText`，不做端侧改写（G2）。

### 2.4 曝光与归因保持

- spotlight 曝光（前 4 条 reportExposure + trackImpression）、「换一批」轮转、点击 `_primeIntersectionHighlight` 透传高亮锚，全部保持并补回归测试。

## 3. 周边契约

- 只消费 `cloud/runtime/generated/recommendation/intersection_reason.g.dart` 现有字段（含 `weightTier`，端侧 DTO 已含该字段——基线修正已落地），**不新增字段、不改 metadata**。
- 开发期数据用 alpha mock seed。**前置说明**：端侧 mock `intersection_repository.dart` 仍残留 3 处旧 kind（`friendInCircle/friendVisited/mutualFriend`），WP1·T4（端侧 mock/fixtures kind 标准化）须先行；否则本包开发期展示将出现旧 kind 样本。beta 联调依赖 WP1·T2（六类真实数据源）与 T3（空窗治理）。
- 新增文案 key（如 light 形态占位）只追加 `UITextConstants`，登记于本节：（细化会话填写）。

## 4. 改动范围（独占权见总纲 §4）

- `quwoquan_app/lib/ui/discovery/widgets/dual_column_discovery_post_card.dart`
- `quwoquan_app/lib/ui/discovery/widgets/intersection_spotlight_module.dart`
- `quwoquan_app/lib/ui/discovery/widgets/home_multi_form_feed.dart`（如需）
- `quwoquan_app/lib/ui/content/widgets/intersection_reason_chip.dart`
- `quwoquan_app/test/**` 对应 widget/golden 测试
- **禁止**改 `works_immersive_viewer.dart`（归 WP7）、`lib/components/object_page/**`（归 WP3）

## 5. 准出要求

1. T2：chip 双口径 widget 测试 + 双列卡/首页多形态 feed/spotlight 结构断言测试全绿（含「理由不在封面 Stack 内」反断言）。
2. T2：weightTier heavy/light/空 三态渲染测试。
3. 曝光/点击埋点回归测试绿（reportExposure / trackImpression / 归因透传）。
4. `dart analyze` 0 error；`bash agent_ops/gate/gate_repo.sh --scope app` 全绿（含 `verify_dart_semantic.py` 颜色语义化）。
5. 页面矩阵无漂移（本包不新增页面，若改动触发矩阵行为列则同步更新）。

## 6. 验收标准（GWT 样例）

- Given 推荐频道含带交集理由的内容卡，When 渲染双列瀑布流，Then 理由显示在图片下方、标题上方，蓝色单行，且图片上无任何交集覆盖物。
- Given spotlight 候选 ≥6 条，When 渲染交集发现区，Then 单屏可见 3~3.5 张卡，每卡 名称/主交集(蓝)/副交集(灰) 三行以内。
- Given reason.weightTier=light，Then 内容卡展示弱化形态；=heavy 或空，Then 展示完整理由行。
- Given reason 无 primaryText 且无 displayText，Then 理由位整体不渲染（无空壳）。

## 7. C0 收口证据（2026-06-12）

- 已落地：`IntersectionReasonChip` 消费 `weightTier`，双列卡与首页多形态 feed 通过同一 chip 管线展示 heavy/light/空三态；spotlight 保持主交集品牌蓝、副交集次级灰，并保留曝光/点击归因路径。
- 边界登记：原规格「四口径同源」修正为「卡片 chip 双口径同源 + 沉浸/详情 reasons 直出」，避免把详情解释层降格为卡片理由位。
- 本地证据：`cd quwoquan_app && flutter test test/ui/content/widgets/intersection_reason_chip_widget_test.dart test/ui/discovery/home_intersection_multiform_feed_widget_test.dart`。
- 仍需集成证据：gamma T3 spotlight 非空窗与真实推荐流曝光/点击归因留证，纳入 `90-integration-acceptance.md` C5。
