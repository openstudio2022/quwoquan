# app-global (delta)

## ADDED Requirements

### Requirement: 布局与整体交互体验要求

应用须遵循以下布局与整体交互基线（来源：06-semantic-consistency-audit 与设计规范）：

- **断点语义**：compact < 360、regular 360–599、expanded ≥ 600；通过 AppSpacing.responsiveValue / AppTypography.responsive 控制差异。
- **可交互热区**：下限 44×44，主操作建议 48×48；使用 AppSpacing.minInteractiveSize / iconButtonMinSizeSm。
- **组内与组间间距**：组内 intraGroup*，组间 interGroup*；分类分段优先 filterCategoryGroupGap。
- **工具面板与创作页可读性**：核心可交互文案不低于 AppTypography.sm，优先 base。
- **深色背景下文本/图标**：须满足高对比；优先 AppColorsFunctional.getColor(...)。
- **沉浸式全屏**：视频等全屏沉浸时底部导航须隐藏；左右滑动切换 Tab 或退出沉浸时须恢复显示。

#### Scenario: 断点影响布局

- **WHEN** 屏幕宽度在 compact（< 360）、regular（360–599）、expanded（≥ 600）区间
- **THEN** 使用 AppSpacing.responsiveValue 或 AppTypography.responsive 获取对应布局与字号值

#### Scenario: 可交互热区满足下限

- **WHEN** 构建可点击的图标或按钮
- **THEN** 触控热区不小于 44×44，主操作建议 48×48

#### Scenario: 沉浸式全屏隐藏底部导航

- **WHEN** 用户进入视频全屏沉浸模式
- **THEN** 底部导航隐藏；左右滑动切换 Tab 或退出沉浸时底部导航恢复显示

---

### Requirement: 一级 Tab 转场与交互

发现、圈子、主页等频道内的一级 Tab 须采用统一的 Tab 转场与交互语义（由 CenteredScrollableTabBar 或等价组件实现）：

- **可见数**：根据屏幕宽度自适应 3/5/7/9/11（小屏优先 5），奇数对称。
- **左右渐变**：两侧渐隐，提示可滚动。
- **点击居中**：点击某 Tab 时，该 Tab 滚动至居中并完成转场。
- **锚定 Tab（可选）**：若指定 anchorTabId（如圈子「推荐」），左滑到一定程度后该 Tab 固定左侧。
- **滑动吸附**：滑动结束且未完成切换时，当前选中 Tab 居中吸附。

发现、圈子、主页一级 Tab 须同语义：选中态、字号、热区与动画一致。

#### Scenario: 可见数自适应

- **WHEN** 屏幕宽度变化
- **THEN** 可见 Tab 数量根据断点取 3/5/7/9/11 之一（小屏优先 5），奇数

#### Scenario: 点击 Tab 居中转场

- **WHEN** 用户点击某 Tab
- **THEN** 该 Tab 滚动至居中，且选中态切换；动画平滑

#### Scenario: 滑动结束居中吸附

- **WHEN** 用户横向滑动 Tab 栏后松手且未完成 Tab 切换
- **THEN** 当前选中 Tab 居中吸附

#### Scenario: 发现与圈子一级 Tab 同语义

- **WHEN** 用户比较发现页与圈子页的一级 Tab
- **THEN** 选中态、字号、热区与动画一致，无视觉与交互差异
