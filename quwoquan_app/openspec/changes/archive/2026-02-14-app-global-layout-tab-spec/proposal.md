# app-global 布局与一级 Tab 规格整合

## Why

app-global 规格已有产品定位、五大频道、主页 3-Tab、小趣入口等，但缺少**布局与整体交互体验**的基线约定，以及**一级 Tab**（发现/圈子等频道内横向切换）的转场与交互规范。这些分散在实现中，导致不同频道 Tab 形态不一、语义不一致。将布局、整体交互、一级 Tab 统一纳入 app-global，可形成清晰基线，后续小趣私人助手等特性在此基础上扩展。

小趣私人助手已作为独立基线特性（assistant-baseline-spec），本次不改动；仅增强 app-global。

## What Changes

- **新增**：app-global 中增加「布局与整体交互体验要求」章节（断点语义、可交互热区、组内/组间间距、沉浸式全屏底部导航显隐等）
- **新增**：app-global 中增加「一级 Tab 转场与交互」需求（CenteredScrollableTabBar 语义：可见数自适应、左右渐变、点击居中、anchorTabId、滑动吸附等）
- **明确**：发现/圈子/主页一级 Tab 同语义（选中态、字号、热区与动画统一）
- **明确**：视频全屏沉浸时底部导航隐藏；左右滑动切换 Tab 或退出沉浸时恢复

## Capabilities

### New Capabilities

（无新增能力；仅修改现有 app-global）

### Modified Capabilities

- `app-global`: 增加「布局与整体交互体验要求」「一级 Tab 转场与交互」两大需求；明确断点、热区、间距、沉浸式全屏、一级 Tab 行为

## Impact

- **规格**：`openspec/specs/app-global/spec.md` 新增章节
- **代码**：`CenteredScrollableTabBar`、`discovery_page`、`circles_page`、`main_app_shell`（底部导航显隐）等与规格对齐
- **依赖**：无新依赖；与 assistant-baseline-spec 并列，不冲突
