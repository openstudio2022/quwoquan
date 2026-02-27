# works-annotation-dot 任务清单

## 当前交付任务
- [ ] **An1** 新建 `WorksAnnotationLayer`（覆盖层，`GestureDetector` 长按 500ms 监听）
- [ ] **An2** 长按触发：记录 `localPosition`，通知父 Widget 锁定 PageView（`ValueNotifier<bool>`）
- [ ] **An3** 新建 `AnnotationDot`：直径 18px，克莱因蓝 `#002FA7`，`BoxShadow` 蓝色光晕，`ScaleTransition` 0→1 入场
- [ ] **An4** 脉冲动画：`AnimationController(repeat, duration: 1200ms)`，`Tween(0.6, 1.0)` 作用于 `AnimatedOpacity`
- [ ] **An5** 点击光点 → 调用 `WorksGlassDrawer` 展开
- [ ] **An6** 松手/取消：`AnimatedOpacity` 200ms 淡出，解锁 PageView
- [ ] **An7** 新长按替换旧光点（更新 `_dotPosition`，重置脉冲 AnimationController）
- [ ] **T1** Widget test：长按 500ms → 光点出现，PageView locked
- [ ] **T2** Widget test：松手 → 光点淡出，PageView unlocked
- [ ] **T3** Widget test：新长按 → 旧光点消失，新光点在新位置出现

## 搁置任务（带规划）
| 任务 | 搁置原因 | 计划重启 |
|------|----------|----------|
| P2 坐标持久化（`position_x/y` 随评论提交） | 评论服务 `Comment` 模型未扩展 `position` 字段；端云坐标映射协议未定 | `publish-comment-reaction` 评论模型扩展完成后 |

## 未来演进任务
- [ ] P2：坐标归一化（`dx/width`, `dy/height`）随评论 API 提交，服务端存储
