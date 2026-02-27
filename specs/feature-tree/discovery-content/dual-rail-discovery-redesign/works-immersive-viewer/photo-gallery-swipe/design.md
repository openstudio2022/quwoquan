# photo-gallery-swipe 设计

## 设计动因
大片展示效果的关键在于图片最大化 + 背景色沉浸感。环境色技术（从图片提取主色填充背景）让不同比例的图片都有"画廊框裱"的视觉效果。

## 适用场景与约束
适用于多图美图作品。约束：环境色计算使用 `palette_dart` 或 `flutter_palette`，异步提取，提取失败降级到 `#0A0E14`。

## 关键决策
```dart
// 环境色：PaletteGenerator.fromImageProvider(NetworkImage(url)) → dominantColor
// 进度条：LinearProgressIndicator(value: (currentPage+1)/total, color: Color(0xFF4A8BF5))
// 进度条高度：SizedBox(height: 1.5)
```

## 未来演进
暂无演进项。
