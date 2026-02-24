# app-global 布局与一级 Tab 设计

## Context

app-global 规格已有产品定位、五大频道、主页 3-Tab、小趣入口、头像设计、语义 token 等。当前实现中已有 `CenteredScrollableTabBar`、`AppSpacing.responsiveValue`、`videoForceDarkProvider` / `bottomNavHiddenProvider` 等，但规格层面未统一定义布局与整体交互基线、一级 Tab 行为。本次将上述约定写入 app-global 规格，使设计与实现一致。

## Goals / Non-Goals

**Goals:**
- 在 app-global 中定义布局与整体交互体验基线（断点、热区、间距、沉浸式全屏）
- 在 app-global 中定义一级 Tab 转场与交互（可见数自适应、渐变、居中、anchorTabId、滑动吸附）
- 发现/圈子/主页一级 Tab 同语义（选中态、字号、热区、动画）
- 视频全屏沉浸时底部导航隐藏，左右滑动切换 Tab 或退出沉浸时恢复

**Non-Goals:**
- 小趣私人助手能力（由 assistant-baseline-spec 独立维护）
- 二级 Tab 或子频道内部实现细节
- 具体数值硬编码（由 AppSpacing、AppTypography 等常量承载）

## Decisions

| 决策 | 选择 | 理由 |
|------|------|------|
| 一级 Tab 组件语义 | CenteredScrollableTabBar 作为统一语义组件 | 发现、圈子已使用，主页 3-Tab 可复用；规格中描述行为而非实现类名 |
| 断点语义 | compact < 360、regular 360–599、expanded ≥ 600 | 与 06-semantic-consistency-audit 一致，通过 AppSpacing.responsiveValue / AppTypography.responsive 控制 |
| 可交互热区 | 下限 44×44，主操作建议 48×48 | 满足无障碍与触控精度；使用 AppSpacing.minInteractiveSize / iconButtonMinSizeSm |
| 沉浸式底部导航 | 由 bottomNavHiddenProvider 控制 | 视频全屏时隐藏，左右滑动切换 Tab 或退出沉浸时恢复 |
| 一级 Tab 可见数 | 3/5/7/9/11 等奇数自适应 | 居中对称；具体由实现根据宽度计算，规格中约定「可见数奇数、左右渐变」 |

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 规格与实现偏差 | 归档时将 delta 合并进 app-global，并执行 flutter analyze 与语义审计脚本 |
| 不同频道 Tab 形态不一 | 规格明确「同语义」；设计审计检查发现/圈子/主页 Tab 一致性 |
