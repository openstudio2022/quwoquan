# L3 Story：主页边缘滑动退出保护 Story (`home-edge-swipe-exit-guard`)

> 所属能力：[`native-edge-gesture-navigation`](../spec.md)
>
> Journey / Scenario：[`JNY-006 / SCN-006`](../../../spec.md#scn-006)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，我希望主页根页边缘滑动退出保护，从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- first edge swipe guard prompt
- second edge swipe exit within guard window
- guard timeout reset

### Out of Scope

- unsaved form leave protection

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 主页首次边缘滑动提示，二次边缘滑动退出

- 第二次边缘滑动在保护窗口内退出或交给系统返回。
- 保护窗口超时后再次滑动重新显示提示。

<a id="req-002"></a>
### REQ-002 Root route contract：主页根路由必须能声明不可直接 pop

- Root route contract：主页根路由必须能声明不可直接 pop。
- Exit guard contract：首次提示、保护窗口、二次退出状态必须统一。

## 4. 契约引用

- canonical：`quwoquan_app/lib/runtime/shell/navigation/native_back_navigation.dart#isBottomNavRootLocation`
- canonical：`quwoquan_app/lib/runtime/shell/navigation/native_back_navigation.dart#rootExitGuardWindow`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 主页首次边缘滑动提示，二次边缘滑动退出

- GIVEN 用户位于主页根路由，当前没有可 pop 的子页面。
- WHEN 用户第一次从屏幕左边缘或右边缘发起返回手势。
- THEN App 显示再次滑动退出提示，且不退出。

## 6. 依赖

- 前置要求：[`native-edge-gesture-navigation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
