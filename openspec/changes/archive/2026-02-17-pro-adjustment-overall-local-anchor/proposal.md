## Why

当前专业修图已经有“基础/HSL/曲线”的框架，但核心能力仍不完整：HSL 尚未落地，且缺少行业常见的“局部锚点调节”（按点+半径渐弱作用）。用户已明确要求对齐 Snapseed/醒图的专业工作流，因此需要一次性补齐“整体 + 局部 + HSL 会话操作”能力并统一面板语义。

## What Changes

- 将专业修图入口升级为“工具箱弹窗 + 工具独立编辑态”，避免直接切页；保留底栏工具栏并在其上方弹出专业工具列表。
- 将“调整图片”参数从 7 项扩展到 15 项，顺序固定为：光感、亮度、曝光、对比度、饱和度、自然饱和度、纹理、锐化、结构、高光、阴影、色温、色调、颗粒、褪色。
- 调整图片支持“整体 + 局部”共享参数列表与同一调节线；局部模式下调节仅作用于当前锚点，整体模式下作用于全图。
- 新增局部锚点的专业交互约束：一次添加模式（点击一次只添加一个锚点）、最多 10 个锚点、添加态提示可缩放范围、双指缩放调半径、当前/非当前锚点亮度分层。
- 新增锚点拖拽性能策略：拖拽中以视觉跟随为主，松手后再一次性应用新位置效果并恢复旧位置影响，保证流畅度与可预测性。
- 新增锚点可视化语义：锚点中心显示当前参数首字，外圈 360 度圆环根据参数值映射；负值区间按逆时针方向增长、正值区间按顺时针方向增长。
- 补齐 HSL 专业调色面板与交互：颜色通道、H/S/L 三轴调节、会话内撤回/重做、对比原图。
- 新增系统级会话操作条（底部内容区）：统一 `undo/redo + compare`，可复用到 HSL 与局部。
- 统一底部 `X / ✓` 样式与热区，并保持黑底中性高可读视觉（不使用蓝色主选中语义）。

## Capabilities

### New Capabilities
- `pro-local-adjustment-panel`: 局部锚点调节能力，覆盖锚点创建/编辑/复制/删除、渐弱半径作用、15项共享参数调节、添加上限与锚点可视化反馈。
- `pro-hsl-adjustment-panel`: HSL 专业调色能力，覆盖通道选择、三轴调节、会话操作与实时预览。
- `editor-session-ops-strip`: 图片编辑器会话操作条能力，统一提供工具会话内 `undo/redo` 与 `compare`。

### Modified Capabilities
- `image-editor`: 专业修图分组结构、面板顺序、工具会话交互与预览导出语义发生规格级变更（整体/局部/HSL/曲线）。

## Impact

- 受影响代码：
  - `lib/components/media/image/editor/image_editor_page.dart`
  - `lib/components/media/image/editor/panels/image_editor_operation_panel.dart`
  - `lib/components/media/image/editor/tool_list/*`
  - 计划新增 `lib/components/media/image/editor/panels/local/*`（锚点与局部面板）
  - 计划新增 `lib/components/media/image/editor/shared/session_ops/*`（会话操作条）
  - 计划新增 `lib/components/media/image/editor/panels/hsl/*`（HSL 面板）
- 受影响状态：
  - 专业修图状态扩展为“整体 + 局部 + HSL + 曲线”并行会话模型
  - 新增局部锚点集合、选中锚点、参数快照、会话内历史栈
- 受影响文档：
  - 变更 `openspec/specs/image-editor/spec.md`
  - 新增 `pro-local-adjustment-panel` / `pro-hsl-adjustment-panel` / `editor-session-ops-strip` 三个能力规格
