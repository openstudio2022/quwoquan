# L4 契约/任务：works-annotation-dot

## 功能说明
长按点位评论入口（P1 UI）：全局长按 500ms 在原位生成克莱因蓝脉冲光点，同时锁定 PageView 双向滑动；点击光点打开 `WorksGlassDrawer`；松手/取消后光点 200ms 淡出，PageView 解锁。P2（坐标持久化）搁置。

## 范围
- `WorksAnnotationLayer`：覆盖在作品内容上的手势捕获层
- `LongPressMixin`：500ms 触发，记录 `Offset` 坐标（本地相对坐标）
- `AnnotationDot`：`ScaleTransition`（0→1）+ `AnimatedOpacity` 脉冲（1→0.6→1 循环），克莱因蓝 `#002FA7`，直径 18px，`BoxShadow` 蓝色光晕
- PageView 锁定：长按触发后设置 `NeverScrollableScrollPhysics`，松手恢复
- 点击光点 → `worksFeedProvider`/`drawerController.open()`

## 适用范围与约束
- 适用：三类作品媒体；P1 仅 UI，坐标不持久化
- P2 前置条件：评论服务 `Comment` 模型支持 `position_x/y` 字段（`publish-comment-reaction` 扩展后）
- 约束：同一作品只允许存在一个光点（新长按替换旧光点）

## 验收标准概要
- A1：长按 500ms → 原位出现蓝色脉冲光点，PageView 锁定
- A2：点击光点 → 打开 WorksGlassDrawer，光点保持显示
- A3：松手/取消 → 光点 200ms 淡出，PageView 解锁
- A4：新长按 → 替换旧光点位置，PageView 保持锁定直至松手
