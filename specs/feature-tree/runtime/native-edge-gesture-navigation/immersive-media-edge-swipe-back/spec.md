# L3 Story：沉浸式媒体边缘滑动返回 Story (`immersive-media-edge-swipe-back`)

> 所属能力：[`native-edge-gesture-navigation`](../spec.md)
>
> Journey / Scenario：[`JNY-006 / SCN-006`](../../../spec.md#scn-006)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，我希望沉浸式媒体浏览器边缘滑动返回，从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- iOS left/right edge swipe
- Android left/right edge swipe or predictive back equivalent

### Out of Scope

- media paging business rules

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 沉浸式媒体边缘滑动返回上一页

- iOS 与 Android 均验证边缘返回成功。
- 返回动画无可见卡顿。

<a id="req-002"></a>
### REQ-002 Route contract：沉浸式媒体浏览器必须暴露可 pop 的路由状态

- Route contract：沉浸式媒体浏览器必须暴露可 pop 的路由状态。
- Gesture policy contract：边缘热区与媒体横滑区域必须可区分。

## 4. 契约引用

- canonical：`quwoquan_app/lib/runtime/shell/navigation/native_back_navigation.dart#AppBackDisposition`
- canonical：`quwoquan_app/lib/runtime/shell/navigation/native_back_navigation.dart#supportedBackEdges`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 沉浸式媒体边缘滑动返回上一页

- GIVEN 用户已从 feed 或详情页进入沉浸式媒体浏览器。
- WHEN 用户从屏幕左边缘或右边缘发起返回手势。
- THEN App 返回上一页，沉浸式媒体浏览器关闭。
- THEN 媒体左右翻页不被误触发。

## 6. 依赖

- 前置要求：[`native-edge-gesture-navigation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
