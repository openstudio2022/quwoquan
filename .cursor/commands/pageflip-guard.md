---
name: /pageflip-guard
id: pageflip-guard
category: Quality
description: 前后翻组件几何/视觉变更前的强制审视入口，防止死分支和诊断分叉
---

`/pageflip-guard` 用于任何触及以下路径的任务：

- `quwoquan_app/lib/ui/content/pageflip/**`
- `quwoquan_app/lib/ui/content/article_reader/pageflip/**`
- `quwoquan_app/test/**/pageflip/**`

## 执行姿态

先只读审视，再制定或刷新计划；不得直接实现。若审视发现真实 paint 路径与既有计划不一致，必须先更新计划。

## 必须输出

### 1. 真实绘制链路

- 判断任务触及 forward、BACK，还是两者。
- 写清 `scene/calculation -> render frame -> deck layers -> Widget paint`。
- 明确真实 paint 使用的函数、Widget、clip、transform。

### 2. 分支地图

- 列出 geometry/helper/projection/slices/diagnostics 分支。
- 标记每个分支属于 `paint`、`diagnostics-only`、`test-only` 或 `dead branch`。
- 禁止优先修改未证明进入 runtime paint 的分支。

### 3. 业界语义对照

- 对照 StPageFlip 的 `flippingPage`、`bottomPage`、`static current`、`position + angle + area`。
- 写明本地 Flutter 不能直接照搬的 layout、clip、transform 差异。

### 4. 本次不变量

- 前/后翻分别要守住的 page face、层级、spine、seam、clip、texture 方向。
- BACK 必须明确 previous leaf、current static page、front/back face 的 page index 语义。

### 5. 红测和证据

- 必须列出至少一个会在旧实现失败的测试、日志指标或诊断指标。
- 层级、前一页背面可见、书脊固定必须有 framebuffer 像素或 viewport overlap 证据。
- `zOrder=`、`currentLayer=`、`backwardReplaySlices` 只能作为辅助证据。

### 6. 删除/封死分叉

- 列出本次要删除、薄包装或禁止继续扩展的分支。
- 若暂不删除，必须写明风险、原因和后续收口点。

## 验证清单

- visual/widget/contract 目标测试必须覆盖本次不变量。
- visual test 不得为了稳定性关闭关键像素断言；若 `toImage()` 慢，只能缩小画布、减少采样点或拆单帧测试。
- 完成后必须说明真实 paint、diagnostics、测试是否仍共用同一 geometry 输出。
