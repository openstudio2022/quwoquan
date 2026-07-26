# L3 Story：图片编辑 (`image-editing`)

> 所属能力：[`publish-comment-reaction`](../spec.md)
>
> Journey / Scenario：[`JNY-003 / SCN-008`](../../../spec.md#scn-008)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，我希望图片编辑器商用化：工具全真实现（占位清零）、曲线/白平衡/马赛克/文字补齐、全局撤销与放弃保护、像素引擎同源与页面观测，从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- 一级工具（滤镜/裁剪/旋转/专业工具/文字/马赛克）与专业工具箱（整体/局部/HSL/黑白色阶/曲线/白平衡）全部真实像素级实现。
- 确认即烘焙 + 文件快照全局撤销/重做/历史回退；back 放弃确认与顶栏完成提交。
- ImageEditorExportEngine 预览导出同源、解码降采样上限。
- page.media.image_editor 四事件埋点与 image_editor_tool_used 工具分布。

### Out of Scope

- 消除笔/透视校正/涂鸦/贴纸/美颜（M3 规划）。
- FilterCatalogRelease 云目录与 MediaAsset 图片 variants（独立 M2 Story）。
- EditRecipe/FilterUsageFact/FilterUsageStatsView 上云与圈子交集（独立 M3 Story）。
- 媒体上传/发布链路（归属 post-create-update）。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 工具入口零占位，所见工具即真实效果

- 全仓无占位符号；工具确认路径全部经 ImageEditorExportEngine 烘焙

<a id="req-002"></a>
### REQ-002 曲线为真实多通道 LUT 编辑器

- 曲线引擎必须保持控制点有序并支持恒等、单调、S 曲线与提亮，确认后效果写入导出像素。

<a id="req-003"></a>
### REQ-003 马赛克与文字为图上实绘图层

- 模型 wire roundtrip 必须保留笔刷、路径与颜色；命中路径后像素合成结果必须与预览一致。

<a id="req-004"></a>
### REQ-004 全局撤销/重做与放弃保护

- 步骤栈必须支持撤销、重做、放弃与完成；不可用工具必须禁用且不得创建空步骤。

<a id="req-005"></a>
### REQ-005 所有可见编辑工具必须产生真实像素结果

- 所有对用户可见的编辑工具必须产生真实像素结果，禁止占位面板或确认后无效果的空壳工具。
- 唯一像素真相源 `ImageEditorExportEngine`：解码（`decodeConstrained`，长边上限 4096 防 OOM；预览降采样 1440）、裁剪、旋转/翻转、矩阵应用、局部径向锚点、曲线 LUT、马赛克化与笔画合成、文字合成、PNG/JPEG 编码。预览与导出共用同一几何/参数，禁止第二坐标链或把局部调整退化为全图平均矩阵。

## 4. 契约引用

- canonical：`quwoquan_app/lib/components/media/image/editor/image_editor_page.dart`
- canonical：`quwoquan_app/lib/components/media/image/editor/shared/image_editor_export_engine.dart`
- canonical：`quwoquan_app/lib/components/media/image/editor/panels/curves/image_editor_curve_models.dart`
- canonical：`quwoquan_app/lib/components/media/image/editor/panels/curves/image_editor_curve_panel.dart`
- canonical：`quwoquan_app/lib/components/media/image/editor/panels/mosaic/image_editor_mosaic_models.dart`
- canonical：`quwoquan_app/lib/components/media/image/editor/panels/text/image_editor_text_models.dart`
- canonical：`quwoquan_app/lib/components/media/image/editor/shared/image_editor_step_stack.dart`
- canonical：`quwoquan_app/lib/components/media/image/editor/top_bar/image_editor_top_bar.dart`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 工具入口零占位，所见工具即真实效果

- GIVEN 用户从图片选择器/相机/创作页进入图片编辑器
- WHEN 用户遍历底部工具栏与专业工具箱的全部入口并逐一确认
- THEN 底部工具栏为滤镜/裁剪/旋转/专业工具/文字/马赛克 6 项；不存在相框入口。
- THEN 专业工具箱为调整图片/局部/HSL/黑白色阶/曲线/白平衡 6 项；不存在透视/修复/色调对比度/魅力光晕占位项。
- THEN 任何面板不出现「操作模版或内容」「即将支持」类占位文案。
- THEN 每个工具确认后当前图片文件被真实烘焙（文件路径变更且像素变化）。

<a id="gwt-002"></a>
### GWT-002 曲线为真实多通道 LUT 编辑器

- GIVEN 用户进入专业工具箱曲线面板
- WHEN 用户切换 RGB/R/G/B 通道、添加/拖动控制点并确认
- THEN 面板展示直方图背景、对角基线与通道曲线；控制点可增删拖动（每通道最多 8 点，端点仅纵向）。
- THEN LUT 由 Fritsch–Carlson 单调插值生成，无过冲；预览与导出使用同一 LUT。
- THEN 确认后图片按曲线烘焙并入撤销栈；取消不产生任何变更。

<a id="gwt-003"></a>
### GWT-003 马赛克与文字为图上实绘图层

- GIVEN 用户进入马赛克或文字工具
- WHEN 马赛克涂抹并确认；文字添加/拖缩旋/样式颜色切换并确认
- THEN 马赛克涂抹路径实时显示对应马赛克效果
- AND 笔画可单步撤销
- AND 确认后全尺寸合成。
- THEN 文字项以图层渲染，选中态可编辑样式（纯色/描边/底纹）与 8 色板颜色，双击重新编辑内容。
- THEN 预览与导出共用同一归一化几何（buildMosaicStrokePath / buildTextPainter）。

<a id="gwt-004"></a>
### GWT-004 全局撤销/重做与放弃保护

- GIVEN 用户完成了至少一步工具确认
- WHEN 用户点击顶栏撤销/重做/记录，或点击 back
- THEN 撤销恢复上一步文件快照
- AND 重做恢复
- AND 新步骤清空重做栈
- AND 历史面板可回退到任一步之前。
- THEN back 弹出破坏性放弃确认
- AND 确认后宿主收到 null 不更新
- AND 无修改时直接退出。
- THEN 顶栏「完成」提交编辑结果并上报 submit 埋点。

## 6. 依赖

- 前置要求：[`publish-comment-reaction`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
