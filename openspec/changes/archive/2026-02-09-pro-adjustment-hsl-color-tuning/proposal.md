## Why

当前专业修图中的 HSL 仍是占位状态，无法满足用户对商业级色彩精修的核心需求（按颜色通道精细调色、取色联动、步骤回退与前后对比）。在已完成基础调节分组后，HSL 是下一阶段最关键的专业能力闭环，必须先落地可用的高保真交互与参数体系。

## What Changes

- 为专业修图新增完整 HSL 调色面板：颜色通道选择（红/橙/黄/绿/青/蓝/紫）、色相/饱和度/明度三维调节、默认中位值、实时预览。
- 新增图像取色器交互：用户可在画面中点选目标颜色并自动映射到最接近的颜色通道，选中态在通道项中有明确视觉反馈。
- 新增 HSL 会话操作：支持撤回/重做与「对比原图」瞬时预览。
- 将「撤回/重做 + 对比原图」抽象为系统级可复用会话操作条（位于图片底部内容区），可被 HSL 及后续其它工具复用；对比基线统一为“进入当前工具会话时的初始图像状态”。
- 统一 HSL 面板底部操作栏与基础分组的 `X / ✓` 样式语义与点击热区，修复尺寸不一致问题。
- 定义并固化专业工具常用参数范围（参考 Lightroom/Camera Raw 常用实践）：
  - 色相（Hue）：`-100 ~ 100`（默认 `0`）
  - 饱和度（Saturation）：`-100 ~ 100`（默认 `0`）
  - 明度（Luminance）：`-100 ~ 100`（默认 `0`）

## Capabilities

### New Capabilities
- `pro-hsl-adjustment-panel`: 专业修图 HSL 面板能力，覆盖通道选择、取色器、三维参数调节、会话级撤回/重做与原图对比。
- `editor-session-ops-strip`: 图片编辑器系统级会话操作条能力，统一提供会话内 undo/redo 与原图对比交互，并可复用到多个工具面板。

### Modified Capabilities
- `image-editor`: 专业修图中的 HSL 分组由占位升级为可用能力，面板交互、底部操作栏一致性与预览行为发生规格级变更。

## Impact

- 受影响代码：
  - `lib/components/media/image/editor/image_editor_page.dart`
  - `lib/components/media/image/editor/panels/image_editor_operation_panel.dart`
  - `lib/components/media/image/editor/tool_list/*`
  - 可能新增 `components/media/image/editor/shared/session_ops/*` 组件
  - 可能新增 `panels/hsl/*` 相关组件与绘制逻辑
- 受影响状态：
  - 专业修图会话状态从基础分组扩展为 `基础 + HSL` 双分组并行管理
  - 需要新增 HSL 参数快照、记录栈、取色状态
- 受影响文档：`openspec/specs/image-editor/spec.md` 与新增 HSL 能力规格
