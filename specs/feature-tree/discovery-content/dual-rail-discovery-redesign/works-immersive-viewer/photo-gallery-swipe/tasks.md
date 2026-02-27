# photo-gallery-swipe 任务清单

## 当前交付任务
- [ ] **W1** 新建 `PhotoGalleryItem`（接收 `PhotoPostDto`）
- [ ] **W2** 水平 `PageView.builder`，`PageScrollPhysics`，`imageUrls` 数量决定 `itemCount`
- [ ] **W3** 底部 1.5px 蓝色进度条（`#4A8BF5`），`PageController` 监听页码
- [ ] **W4** 环境色背景：`PaletteGenerator` 提取 `dominantColor`，异步填充背景，降级到 `#0A0E14`
- [ ] **W5** 图片加载失败：降级纯色占位符
- [ ] **T1** Widget test：翻页 → 进度条页码更新
- [ ] **T2** Widget test：单图 → 无进度条，无翻页

## 搁置任务（带规划）
暂无。

## 未来演进任务
暂无。
