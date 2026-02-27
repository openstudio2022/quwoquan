# L4 契约/任务：moment-video-autoplay

## 功能说明
微趣帖子内嵌视频卡片：`VisibilityDetector` 监听视口可见率，≥ 60% 时自动播放（音量淡入），< 60% 时暂停；点击卡片可全屏播放（不进入作品频道沉浸模式）。

## 范围
- `MomentVideoCard`：内嵌 `VideoPlayer`，视口触发，音量淡入
- 全屏：`Navigator.push` 简单全屏播放器（关闭按钮），非作品频道 immersive
- 静音指示器：初始显示，播放后淡出

## 适用范围与约束
- 适用：`MomentPostDto.videoUrl` 非空
- 约束：与 `VideoAutoPlayItem`（作品频道）复用 `VisibilityDetector` 逻辑，但不共享 `worksForceDarkProvider`

## 验收标准概要
- A1：进入视口 ≥ 60% 自动播放，音量淡入；离开视口暂停
- A2：点击卡片 → 简单全屏播放器（非 immersive），关闭按钮退出
