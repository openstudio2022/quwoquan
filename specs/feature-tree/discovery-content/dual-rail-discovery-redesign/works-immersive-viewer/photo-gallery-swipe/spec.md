# L4 契约/任务：photo-gallery-swipe

## 功能说明
美图作品的水平翻页浏览：水平 PageView 切换同作品多图，底部极细蓝色线性进度条，非 16:9 图片填充环境色模糊背景。

## 范围
- `PhotoGalleryItem` Widget（接收 `PhotoPostDto`）
- 水平 `PageView`：多图翻页（`imageUrls`），`PageScrollPhysics`
- 底部进度条：高 1.5px，颜色 `#4A8BF5`，宽度 = 当前页/总页比例
- 环境色背景：`imageUrls[0]` 提取主色 → `ColorFilter` 模糊底层（仅非全宽图片时显示）
- 单图时无翻页手势，无进度条

## 适用范围与约束
- 适用：`PhotoPostDto`（`imageUrls.length >= 1`）
- 约束：图片加载失败时降级到纯色占位符（墨浆蓝 `#0A0E14`）

## 验收标准概要
- A1：多图水平翻页，进度条随页码更新
- A2：非全宽图片（比例 < 16:9）显示环境色模糊背景
- A3：单图时无翻页手势、无进度条
