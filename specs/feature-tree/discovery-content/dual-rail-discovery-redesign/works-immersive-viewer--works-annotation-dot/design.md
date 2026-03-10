# works-annotation-dot 设计

## 设计动因
长按点位作为"沉浸评论"入口，与内容深度绑定，比右下角固定评论按钮更有仪式感。P1 仅实现 UI 入口（光点 + 打开 Drawer），不做坐标持久化，降低本期复杂度。

## 适用场景与约束
适用：三类作品。P2 坐标持久化搁置，原因：评论服务尚不支持位置元数据；Flutter 坐标系与服务端坐标系的映射需要约定（百分比 vs 像素）。

## 关键决策
```dart
// 长按检测（500ms）
GestureDetector(
  onLongPressStart: (details) {
    _dotPosition = details.localPosition;
    _locked = true;  // 通知父 Widget 切换 PageScrollPhysics
    _showDot = true;
  },
  onLongPressEnd: (_) {
    _showDot = false;  // 200ms AnimatedOpacity fade out
    _locked = false;
  },
)
// 光点
Positioned(
  left: _dotPosition.dx - 9,
  top: _dotPosition.dy - 9,
  child: AnnotationDot(),
)
// 脉冲：RepeatCurve + AnimationController(vsync, duration: 1200ms, repeat)
// Tween<double>(begin: 0.6, end: 1.0) 作用于 opacity
```

PageView 锁定：父 Widget 通过 `ValueNotifier<bool> _pagingLocked` 切换 `physics`。

## 未来演进
- P2：记录 `position_x = dx / renderBox.size.width`，`position_y = dy / renderBox.size.height`，随评论提交到服务端
