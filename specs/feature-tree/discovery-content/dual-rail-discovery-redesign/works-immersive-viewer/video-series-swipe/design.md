# video-series-swipe 设计

## 设计动因
微博式视频内嵌卡片 + 入焦自动播放，提供沉浸感同时不打断刷流体验。系列关联让作者创作的多段视频保持叙事连贯性。

## 适用场景与约束
适用：`VideoPostDto`。约束：Flutter `video_player` 包不支持直接设置音量 tween，需手动 `Timer.periodic` 每 50ms 步进 +0.1。

## 关键决策
```dart
// 入焦自动播放
VisibilityDetector(
  onVisibilityChanged: (info) {
    if (info.visibleFraction >= 0.6) _play();
    else _pause();
  },
)
// 音量淡入
void _play() {
  _controller.play();
  final timer = Timer.periodic(Duration(milliseconds: 50), (t) {
    _volume = min(1.0, _volume + 0.1);
    _controller.setVolume(_volume);
    if (_volume >= 1.0) t.cancel();
  });
}
```

系列切换：水平 `PageView`，`itemCount = seriesIds.length`，每项独立 `VideoPlayerController`（懒加载）。

## 未来演进
- Picture-in-Picture（依赖平台能力）
- 视频预加载（相邻 ±1 预加载）
