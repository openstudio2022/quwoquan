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

### 2.1 卡结构契约固化（防回归）

- Widget 测试断言双列卡渲染顺序：封面 → 交集理由（若有）→ 标题 → 作者行；断言交集理由 **不在** 封面 Stack 内部（禁止 overlay）。
- 单列关系卡断言：作者头部 → 交集 chip → 正文 → 媒体 → 互动栏。
- spotlight 断言：`visibleCardsPerViewport` ∈ [3, 3.5]；卡内文字 ≤3 行；主交集使用品牌蓝 token、副交集使用次级灰 token。

### 2.2 weightTier 轻重分化

- `heavy`：完整理由行（图标 + 蓝色 primaryText）。
- `light`：弱化形态（仅小图标 + 灰色短文案，或并入作者行尾），具体形态在细化会话内定稿，但必须满足「内容优先」原则（§20.6）。
- `weightTier` 为空时按 `heavy` 兜底（向后兼容现状）。
- 四口径理由位（单列/双列/沉浸/详情，`lib/ui/content/widgets/intersection_reason_chip.dart`）同源消费，禁止只改其一。

### 2.3 颜色与语言统一

- 交集相关颜色全部走 `AppColors` 语义 token（连接蓝 / 副文案灰）；移除任何硬编码 Color。
- chip / spotlight 文案直出云侧 `primaryText/secondaryText`，不做端侧改写（G2）。

### 2.4 曝光与归因保持

- spotlight 曝光（前 4 条 reportExposure + trackImpression）、「换一批」轮转、点击 `_primeIntersectionHighlight` 透传高亮锚，全部保持并补回归测试。

## 3. 周边契约

- 只消费 `cloud/runtime/generated/recommendation/intersection_reason.g.dart` 现有字段（含 `weightTier`），**不新增字段、不改 metadata**。
- 开发期数据用 alpha mock seed（WP1 会补七类样本，但本包不依赖：现有 seed 已含蓝色主交集样本）；beta 阶段与 WP1 联调。
- 新增文案 key（如 light 形态占位）只追加 `UITextConstants`，登记于本节：（细化会话填写）。

## 4. 改动范围（独占权见总纲 §4）

- `quwoquan_app/lib/ui/discovery/widgets/dual_column_discovery_post_card.dart`
- `quwoquan_app/lib/ui/discovery/widgets/intersection_spotlight_module.dart`
- `quwoquan_app/lib/ui/discovery/widgets/home_multi_form_feed.dart`（如需）
- `quwoquan_app/lib/ui/content/widgets/intersection_reason_chip.dart`
- `quwoquan_app/test/**` 对应 widget/golden 测试
- **禁止**改 `works_immersive_viewer.dart`（归 WP7）、`lib/components/object_page/**`（归 WP3）

## 5. 准出要求

1. T2：四口径理由位 widget 测试 + 双列卡/单列卡/spotlight 结构断言测试全绿（含「理由不在封面 Stack 内」反断言）。
2. T2：weightTier heavy/light/空 三态渲染测试。
3. 曝光/点击埋点回归测试绿（reportExposure / trackImpression / 归因透传）。
4. `dart analyze` 0 error；`bash agent_ops/gate/gate_repo.sh --scope app` 全绿（含 `verify_dart_semantic.py` 颜色语义化）。
5. 页面矩阵无漂移（本包不新增页面，若改动触发矩阵行为列则同步更新）。

## 6. 验收标准（GWT 样例）

- Given 推荐频道含带交集理由的内容卡，When 渲染双列瀑布流，Then 理由显示在图片下方、标题上方，蓝色单行，且图片上无任何交集覆盖物。
- Given spotlight 候选 ≥6 条，When 渲染交集发现区，Then 单屏可见 3~3.5 张卡，每卡 名称/主交集(蓝)/副交集(灰) 三行以内。
- Given reason.weightTier=light，Then 内容卡展示弱化形态；=heavy 或空，Then 展示完整理由行。
- Given reason 无 primaryText 且无 displayText，Then 理由位整体不渲染（无空壳）。
