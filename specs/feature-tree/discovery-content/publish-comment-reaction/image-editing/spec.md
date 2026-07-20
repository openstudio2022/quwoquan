# L3 特性：image-editing

## 功能说明

- 图片编辑器是图片作品创作链路（选择器/相机 → 编辑 → 创作页发布）中的编辑环节，目标是让创作者在发布前把照片快速修到可发布品质。
- 对标 Snapseed 3.0 / 醒图的基础盘：所有对用户可见的工具入口必须是真实像素级实现，禁止占位面板或「确认后无效果」的空壳工具。
- 编辑为纯端侧本地能力：编辑动作不触发云调用；编辑结果以本地文件路径回填宿主，发布时经 `MediaUploadSession → MediaAsset` 通用链路上传（归属 post-create-update）。

## 工具矩阵（2026-07-20 商用化收敛冻结）

一级工具（底部栏，6 项，全部真实实现）：

| 工具 | 实现语义 |
|---|---|
| 滤镜 | 预设分类/强度/推荐/最近使用；`ColorFilter.matrix` 预览与导出同源 |
| 裁剪 | 比例（original/free/1:1/2:3/3:2/3:4/4:3/9:16/16:9）+ 拖拽框 + 重置 |
| 旋转 | 90° 步进 + 精细角度 + 水平/垂直翻转，范围框内导出 |
| 专业工具 | 二级工具箱（见下） |
| 文字 | 图上文字图层：输入、纯色/描边/底纹样式、8 色板、拖动/双指缩放旋转、双击重编、删除；导出经 `applyTextItems` 合成 |
| 马赛克 | 涂抹实绘：像素化/模糊两种效果、笔刷大小、笔画撤销；预览 painter 与导出 `applyMosaicStrokes` 共用 `buildMosaicStrokePath` 几何 |

专业工具箱（6 项，全部真实实现）：

| 工具 | 实现语义 |
|---|---|
| 调整图片 | 15 项整体调节（光感/亮度/曝光/对比度/饱和度/自然饱和度/纹理/锐化/结构/高光/阴影/色温/色调/颗粒/褪色） |
| 局部 | 最多 10 锚点局部调节（拖拽/半径/放大镜/复制/删除/会话撤销） |
| HSL | 8 通道 × 色相/饱和度/明度 + 取色器 + 会话撤销/对比 |
| 黑白色阶 | 白场/黑场 + 会话撤销/对比 |
| 曲线 | RGB/R/G/B 四通道控制点曲线（每通道最多 8 点）、亮度直方图背景、Fritsch–Carlson 单调三次插值生成 256 LUT；预览 CPU LUT 降采样实时、导出全尺寸同一 LUT |
| 白平衡 | 色温/色调矩阵 + 灰世界自动白平衡（AWB） |

已按商用诚信原则移除的入口（无实现不上架）：相框、透视、修复（消除笔）、色调对比度、魅力光晕、工具箱重复锐化、美颜残留标签。消除笔/透视/涂鸦/贴纸列入 M3 规划（见 acceptance out_of_scope）。

## 编辑会话与撤销语义

- **确认即烘焙**：每个工具确认时立即把效果烘焙为新的本地临时文件（与醒图/Snapseed 的按工具提交模型一致），一步一文件快照。
- **全局撤销/重做**：`ImageEditorStepStack` 文件快照栈；每步记录 `imageIndex/beforePath/afterPath`，undo 恢复 before、redo 恢复 after、新步骤清空重做栈；历史面板提供「回退到此步之前」（时间倒序批量撤销），不存在「删除单步不重算」的欺骗语义。
- **放弃保护**：顶栏 back 在有已提交修改时弹放弃确认（destructive action sheet），确认后返回 null（宿主不更新）；无修改直接退出。顶栏「完成」为显式提交出口，多图另有「下一步」进入创作页。
- 会话级（面板内）撤销/对比：HSL/黑白/局部保留既有会话栈与长按对比原图。

## 像素引擎与性能

- 唯一像素真相源 `ImageEditorExportEngine`：解码（`decodeConstrained`，长边上限 4096 防 OOM；预览降采样 1440）、裁剪、旋转/翻转、矩阵应用、局部径向锚点、曲线 LUT、马赛克化与笔画合成、文字合成、PNG/JPEG 编码。预览与导出共用同一几何/参数，禁止第二坐标链或把局部调整退化为全图平均矩阵。
- 曲线预览：降采样底图 rgba 缓存 + LUT CPU 重算（计算中合并连续拖动）；直方图从降采样图按步长采样。
- 导出性能预算：12MP 图片单工具烘焙 P95 ≤ 3s；编辑器峰值内存 ≤ 300MB。

## 观测

- 页面四事件（`page_lifecycle_state`，pageName=`media.image_editor`，surface=`imageEditor`）：enter（带图片数）、exit（带停留时长与步骤数）、submit（带步骤数）、failure（带 copyKey/错误码）。
- 工具使用分布：`image_editor_tool_used`（tool/subType/source），随步骤提交上报，供滤镜/工具运营分析与推荐回流。

## 后续里程碑（不在本 story 当前范围）

- M2（独立 Story）：`FilterCatalogRelease` 云目录（收敛 `assets/filters/filter_presets.json` 第二真相源）；MediaAsset 图片处理管线（压缩/typed variants/CDN）与 `CONTENT_MEDIA_GAMMA_UAT` 收口。
- M3（独立 Story）：`EditRecipe`/`FilterUsageFact`/`FilterUsageStatsView` 配方沉淀与圈子热度交集（「圈内 N 人使用过该配方」的可证实事实 + 一键套用回流）；消除笔/透视/涂鸦/贴纸。
