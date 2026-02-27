# works-immersive-viewer 任务清单

## 当前交付任务

### 框架级任务
- [ ] **B1** 扩展 `videoForceDarkProvider` → `worksForceDarkProvider`（`lib/ui/discovery/providers/works_force_dark_provider.dart`）
- [x] **B2** 新建 `WorksImmersiveViewer`（`lib/ui/discovery/widgets/works_immersive_viewer.dart`）：垂直 `PageView.builder`，`PageScrollPhysics`，接入 `WorksFeedNotifier`（当前 feed 端侧混排占位）
- [ ] **B3** 实现 drag angle 过滤：外层 PageView 仅在角度 ≥ 45° 时消费垂直拖拽；< 45° 传给子 Widget
- [ ] **B4** 边缘 15px 保护：`HorizontalDragGestureRecognizer` 中判断 `details.globalPosition.dx > 15` 才接受手势
- [x] **B5** 实现 `_buildWorkItem` 类型派发：`PhotoPostDto` → `PhotoGalleryItem`，`VideoPostDto` → `VideoAutoPlayItem`，`ArticlePostDto` → `ArticleCardItem`
- [ ] **B6** 滑到底触发 `appendNextPage`（`PageController.addListener` 监听 `page >= items.length - 2`）
- [x] **B7** Drawer Stack 结构：`AnimatedSlide` + `BackdropFilter`；关闭时卸载 BackdropFilter（`Visibility(maintainState: false)`）

### 底部工具栏交互精化（已完成）
- [x] **UI1** `_WorksBottomToolbar` 响应式布局：3 档位（compact<360/regular/expanded≥600），action 单元宽 40/44/52px，间距 4/6/8px，跨组分隔 6/8/12px；同一设备不同作品间 action 位置严格不变
- [x] **UI2** 关注按钮延迟显示：`Timer` 驱动，图片 3s / 视频&文章 5s 后出现；已关注者进入即同步显示，无延迟
- [x] **UI3** 关注按钮入场动画：`AnimatedSize(alignment: Alignment.centerRight)` 从右侧向左展开，右边缘固定于 action 区左侧，视觉上从操作组方向滑入
- [x] **UI4** 文字动态压缩：关注按钮可见且当前未关注时，`AnimatedDefaultTextStyle` 将名字字号 14→12px、圈子名字号 10→9px；已关注状态不压缩
- [x] **UI5** 名字渐变遮挡：关注按钮可见时用 `ShaderMask` 在名字列右侧叠加固定 18px 渐变（白→透明），配合 `TextOverflow.clip` 实现视觉淡出，代替硬截断 "..."
- [x] **UI6** 数字格式化 `_formatCount`：< 10 000 原值显示；10 000–99 999 显示 `m.n万+`（如 32 999 → 3.2万+，10 001 → 1万+）；≥ 100 000 显示 `10万+`
- [x] **UI7** 一级 Tab（微趣/作品）响应式：字号 compact 16/regular 18/expanded 20px，Tab 间距 compact 12/regular 16/expanded 24px；移除固定宽度约束
- [x] **UI8** 更多按钮（⋯）打开帖级操作面板 `_WorksMoreOptionsSheet`（非助手对话）：3 组卡片（① 正向操作：保存图片/视频、收藏、分享、复制链接；② 反馈：不感兴趣、举报红色警示；③ 取消），组间 6px 间距，组内 0.5px 分割线
- [x] **UI9** 设计系统增补：`AppTypography.xxs = 9.0`（压缩态最小字号）；`UITextConstants` 新增 `savePhoto / saveVideo / savePost / savedLabel / notInterested`

### 美图水平翻页修复（已完成）
- [x] **UI10** `_WorksPhotoCanvas` 手势重构：顶层 `GestureDetector` 处理水平拖拽，内层 `PageView.builder` 使用 `NeverScrollableScrollPhysics`，`DecoratedBox` 渐变层用 `IgnorePointer` 包裹，确保图片可水平滑动

### 测试
- [ ] **T1** Widget test：垂直分页切换 PostBaseDto 类型正确派发
- [ ] **T2** Widget test：`worksForceDarkProvider` 激活/关闭主题切换正确
- [ ] **T3** Widget test：关注按钮 3s/5s 延迟显示逻辑；已关注即时显示
- [ ] **T4** Widget test：底部工具栏 3 档位响应式宽度，同一设备 action 位置不变

> L4 子节点各自有独立 tasks，本节点只负责框架级任务。

## 搁置任务（带规划）

暂无。

## 未来演进任务

- [ ] 视频 Picture-in-Picture 支持（依赖平台能力评估）
- [ ] 真视频自动播放与音量淡入（当前仅视觉态）
