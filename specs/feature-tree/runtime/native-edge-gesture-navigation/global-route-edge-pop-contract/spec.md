# L3 Story：全局无底栏页面边缘返回 Story (`global-route-edge-pop-contract`)

> 所属能力：[`native-edge-gesture-navigation`](../spec.md)
>
> Journey / Scenario：[`JNY-006 / SCN-006`](../../../spec.md#scn-006)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，我希望全局无底栏页面原生边缘返回上一页，从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- ordinary non-bottom-nav route page factory
- platform native back policy
- explicit special-page back guard boundary

### Out of Scope

- unsaved form leave protection internals

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 无底栏页面通过平台原生边缘手势返回上一页

- 普通非 shell 页面通过 AppRoutePageFactory 构造平台 Page。
- iOS 普通页面使用 CupertinoPage 承载并支持 leading-edge interactive pop。
- Android 普通页面经系统 back / predictive back 返回上一页。
- 特殊页面通过 route kind 或 AppBackGuard 显式登记。

<a id="req-002"></a>
### REQ-002 Page factory contract：普通非 shell 页面必须通过 `AppRoutePageFactory` 构造平台 Page

- Page factory contract：普通非 shell 页面必须通过 `AppRoutePageFactory` 构造平台 Page。
- 新增普通页面不得使用未登记的 `GoRoute.builder` 绕过 Page 工厂。
- 全屏搜索、创作、通话、WebView 等特殊页面必须显式声明 route kind 或 guard。

## 4. 契约引用

- canonical：`quwoquan_app/lib/app/navigation/native_back_navigation.dart#appRoutePage`
- canonical：`quwoquan_app/lib/app/navigation/native_back_navigation.dart#NativeBackNavigationPolicy`
- canonical：`quwoquan_app/lib/app/navigation/native_back_navigation.dart#AppBackGuard`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 无底栏页面通过平台原生边缘手势返回上一页

- GIVEN 用户位于非底栏根路由，且 Router 栈存在上一页。
- WHEN 用户发起平台原生 back 手势。
- THEN App 返回上一页，不退出应用，不跳转硬编码兜底 tab。

## 6. 依赖

- 前置要求：[`native-edge-gesture-navigation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 无底栏页面通过平台原生边缘手势返回上一页

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：普通非 shell 页面通过 AppRoutePageFactory 构造平台 Page。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效
