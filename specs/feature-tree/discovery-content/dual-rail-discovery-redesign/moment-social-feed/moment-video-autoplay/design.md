# moment-video-autoplay 设计

## 设计动因
微博视频的"刷到自动播放"体验已成用户默认预期。微趣视频采用相同模式，但不使用作品频道的沉浸主题，保持明亮社交场风格。

## 关键决策
复用 `video-series-swipe` 中的 `VisibilityDetector` + 音量淡入逻辑（可提取为 `VideoPlaybackMixin`），但不继承 `worksForceDarkProvider`。

## 未来演进
暂无。
