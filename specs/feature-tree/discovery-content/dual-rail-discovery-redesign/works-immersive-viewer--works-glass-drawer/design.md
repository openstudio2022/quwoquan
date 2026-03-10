# works-glass-drawer 设计

## 设计动因
评论层与内容层的空间深度感通过毛玻璃实现："内容在远处，评论在近处"。深蓝倾向背景确保评论区与作品内容有明确的视觉分层，不使用纯黑或纯透明。

## 适用场景与约束
适用：三类作品。约束：BackdropFilter 是 GPU 密集操作，必须在 Drawer 关闭后通过 `Visibility(maintainState: false)` 完全卸载，避免持续绘制。

## 关键决策
```dart
// 触发区：屏幕右侧 40%（x > screenWidth * 0.6）
// Drawer 宽：screenWidth * 0.4
// 动画：AnimatedSlide(Offset(0.6→0, 0), duration: 280ms, curve: Curves.easeOut)
// 毛玻璃关闭后卸载：
Visibility(
  visible: _drawerOpen,
  maintainState: false,
  child: BackdropFilter(filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20), ...),
)
```

## 未来演进
- 评论列表接入真实评论 API（`publish-comment-reaction/comment-thread` 完成后）
- 点位评论 P2：Drawer 接收并高亮定位评论（坐标元数据）
