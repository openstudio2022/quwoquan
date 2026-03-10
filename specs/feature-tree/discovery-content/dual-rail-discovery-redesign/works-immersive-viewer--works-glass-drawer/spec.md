# L4 契约/任务：works-glass-drawer

## 功能说明
右侧 40% 宽毛玻璃评论 Drawer：右侧热区点击或向左微拉触发，BackdropFilter sigma ≥ 15，深蓝倾向背景；评论列表滚动不影响外层 PageView。

## 范围
- `WorksGlassDrawer`（Overlay Widget，宽 40% 屏宽）
- 触发：右侧 40% 热区 `GestureDetector(onTap/onHorizontalDragEnd)` + `works-annotation-dot` 点击
- 视觉：`BackdropFilter(filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20))`，背景 `#0A0E14` 80% opacity
- 关闭：滑出屏幕或点击左侧遮罩区；关闭后销毁 BackdropFilter 节点（`Visibility(maintainState: false)`）
- 评论列表：独立 `ScrollController`，不传递到外层 PageView

## 适用范围与约束
- 适用：所有三类媒体作品（美图/视频/文章）
- 约束：不遮挡系统状态栏与 Home Indicator（`SafeArea` 内渲染）；sigma > 15 GPU 开销须在关闭时释放

## 验收标准概要
- A1：右侧 40% 热区点击 → Drawer 从右侧 slide-in（280ms）
- A2：BackdropFilter sigma = 20，背景 #0A0E14 80% opacity
- A3：评论列表滚动不触发外层 PageView 换页
- A4：关闭时 BackdropFilter 完全卸载
