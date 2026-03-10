# L4 契约/任务：moment-image-grid

## 功能说明
微趣帖子的图片自适应宫格布局（微博规则）：1 图全宽，2 图两列，3-9 图 n×3 宫格；点击图片进入轻量全屏浏览器（支持左右滑，无 Drawer 评论）。

## 范围
- `MomentImageGrid`（根据 `imageUrls.length` 选择布局）
- 轻量图片浏览器：`MomentImageBrowser`（`PageView`，黑色背景，关闭按钮，基础手势）
- 图片圆角：4px（宫格内），单图无圆角

## 适用范围与约束
- 适用：`MomentPostDto.imageUrls` 非空
- 约束：宫格内图片统一高度（`AspectRatio` 适配）；浏览器无 BackdropFilter 评论 Drawer

## 验收标准概要
- A1：1/2/3-9 图宫格布局正确
- A2：点击图片 → 轻量全屏浏览器，左右滑切换，关闭按钮退出
