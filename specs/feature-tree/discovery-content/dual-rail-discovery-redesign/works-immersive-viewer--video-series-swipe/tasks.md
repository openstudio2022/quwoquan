# video-series-swipe 任务清单

## 当前交付任务
- [ ] **V1** 新建 `VideoAutoPlayItem`（接收 `VideoPostDto`）
- [ ] **V2** 全屏 `VideoPlayer`，`video_player` 包，自动循环，进入视口自动播放
- [ ] **V3** `VisibilityDetector`（`visibilitydetector` 包）：`visibleFraction >= 0.6` 触发播放
- [ ] **V4** 音量 Tween：`Timer.periodic(50ms)` 步进 +0.1，500ms 淡入到 1.0；离开视口重置为 0
- [ ] **V5** 水平 `PageView`：有 `seriesIds` → 懒加载各 `VideoAutoPlayItem`；无 → `AuthorWorksCard`
- [ ] **V6** 新建 `AuthorWorksCard`（作者头像 + 作品缩略图网格 3×2）
- [ ] **T1** Widget test：视口可见率 ≥ 60% 触发播放，< 60% 暂停
- [ ] **T2** Widget test：有 seriesIds → 水平切换系列；无 seriesIds → 出现 AuthorWorksCard

## 搁置任务（带规划）
暂无。

## 未来演进任务
- [ ] 视频预加载（相邻 ±1）
- [ ] Picture-in-Picture（平台能力具备后）
