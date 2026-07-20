# L3 特性：沉浸式媒体边缘滑动返回 Story

## 最小价值点

用户在沉浸式媒体浏览器中从 iOS / Android 屏幕左右边缘滑动时，应返回上一页或退出沉浸浏览器，不应误触媒体左右切换。

## 归属

- 领域服务：`runtime`
- 业务能力：`native-edge-gesture-navigation`
- 关联 Scenario：`immersive-media-edge-swipe-back`

## 行为规则

- Given：用户从 feed 或详情页打开沉浸式媒体浏览器。
- When：用户从屏幕左或右边缘发起系统返回手势。
- Then：路由 pop 到上一页，媒体浏览器清理沉浸态，媒体横滑翻页不被触发。

## 接口契约

- Route contract：沉浸式媒体浏览器必须暴露可 pop 的路由状态。
- Gesture policy contract：边缘热区与媒体横滑区域必须可区分。
- Telemetry contract：记录 edgeSwipeBack、edgeSwipeCancel、gestureConflictResolved。

## 验收关注点

- iOS interactive pop 与 Android predictive back / back dispatcher 均覆盖。
- 左右边缘均覆盖。
- 横滑媒体翻页与边缘返回冲突可测。
- 返回动画无明显卡顿。
