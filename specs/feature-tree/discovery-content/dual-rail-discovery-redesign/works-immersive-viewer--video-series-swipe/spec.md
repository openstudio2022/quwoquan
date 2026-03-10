# L4 契约/任务：video-series-swipe

## 功能说明
视频作品的全屏沉浸播放：进入视口自动播放，音量 500ms 淡入，水平滑切换同作者关联系列片段；无关联时水平滑展示"作者作品集卡片"。

## 范围
- `VideoAutoPlayItem`（接收 `VideoPostDto`）
- 全屏 `VideoPlayer`，无边框，自动循环
- 进入视口 → `VideoPlayerController.play()` + 音量 0→1 Tween 500ms
- 水平滑：若 `VideoPostDto.seriesIds` 非空 → 切换系列片段；否则展示 `AuthorWorksCard`
- 离开视口 → 暂停并重置音量

## 适用范围与约束
- 适用：`VideoPostDto`（`videoUrl` 非空）
- 约束：视频加载失败时展示缩略图 + 加载指示器；音量淡入用 Dart `Timer.periodic` 渐进设置
- `seriesIds` 字段若当前 `VideoPostDto` 缺失，视为无系列

## 验收标准概要
- A1：进入视口自动播放，音量 500ms 淡入到 1.0
- A2：有系列：水平滑切换系列片段（复用 `VideoAutoPlayItem`）
- A3：无系列：水平滑出现 `AuthorWorksCard`（作者头像 + 作品缩略图列表）
- A4：离开视口暂停，音量重置为 0
