# works-glass-drawer 任务清单

## 当前交付任务
- [ ] **D1** 新建 `WorksGlassDrawer`（`lib/ui/discovery/widgets/works_glass_drawer.dart`）
- [ ] **D2** 触发区：右侧 40% `GestureDetector`，`onTap` + `onHorizontalDragEnd(dx < -20)` 展开
- [ ] **D3** `AnimatedSlide`：`Offset(1.0→0.6, 0)` → `Offset(0.6→0, 0)`，duration 280ms，`Curves.easeOut`（注：offset 单位为 fraction of own width）
- [ ] **D4** `BackdropFilter(ImageFilter.blur(sigmaX: 20, sigmaY: 20))`，背景 `Color(0x80000000)` + 蓝色叠加 `Color(0x1A0A0E14)`
- [ ] **D5** `Visibility(maintainState: false)` 包裹 BackdropFilter，关闭时卸载
- [ ] **D6** 评论列表 `ScrollController`：阻止 scroll 事件传到外层（`ScrollConfiguration.of(context).copyWith(overscroll: false)` 或 `NotificationListener`）
- [ ] **T1** Widget test：右侧 40% tap → Drawer 展开；左侧遮罩 tap → 关闭
- [ ] **T2** Widget test：关闭后 BackdropFilter 不再绘制（Visibility maintainState false）

## 搁置任务（带规划）
暂无。

## 未来演进任务
- [ ] 接入真实评论列表（依赖 comment-thread L3 完成）
- [ ] 点位评论 P2：Drawer 接收坐标高亮评论
