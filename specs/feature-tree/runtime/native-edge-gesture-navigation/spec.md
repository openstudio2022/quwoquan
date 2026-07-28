# L2 Business Capability：原生边缘手势导航规格 (`native-edge-gesture-navigation`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

让用户在 iOS 与 Android 上通过符合平台习惯的边缘手势返回、退出或保持沉浸内容，并避免与翻页手势冲突。

## 2. 范围与非目标

### In Scope

- global route edge pop contract
- immersive media edge swipe back
- home edge swipe exit guard

### Out of Scope

- system-level OS gesture settings

## 3. Journey / Scenario 贡献

- [`JNY-006 / SCN-006`](../../spec.md#scn-006)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：iOS/Android 边缘手势导航能力 SIT，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-006 / SCN-021`](../../spec.md#scn-021)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：iOS/Android 边缘手势导航能力 SIT，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-006 / SCN-022`](../../spec.md#scn-022)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：iOS/Android 边缘手势导航能力 SIT，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`global-route-edge-pop-contract`](./global-route-edge-pop-contract/spec.md)：普通非 shell 页面通过 AppRoutePageFactory 构造平台 Page。
- [`home-edge-swipe-exit-guard`](./home-edge-swipe-exit-guard/spec.md)：第二次边缘滑动在保护窗口内退出或交给系统返回。
- [`immersive-media-edge-swipe-back`](./immersive-media-edge-swipe-back/spec.md)：iOS 与 Android 均验证边缘返回成功。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 边缘手势导航能力 SIT

- Ordinary non-bottom-nav pages can return to the previous route through platform-native back gestures.
- iOS leading-edge pop and Android left/right back gestures follow platform expectations.
- Android home root exit guard blocks accidental first exit.
- Immersive media viewer returns without misfiring media page swipe.

<a id="req-002"></a>
### REQ-002 路由 Page 工厂、防腐策略层与根壳返回状态机的统一契约

- 路由 Page 工厂、防腐策略层与根壳返回状态机的统一契约。
- 路由承载：普通页面必须经统一 Page 工厂生成原生路由，禁止新增普通页面绕过工厂使用默认 `GoRoute.builder`。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 边缘手势导航能力 SIT

- GIVEN 执行“边缘手势导航能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“边缘手势导航能力”对应动作。
- THEN Ordinary non-bottom-nav pages can return to the previous route through platform-native back gestures.
- THEN iOS leading-edge pop and Android left/right back gestures follow platform expectations.
- THEN Android home root exit guard blocks accidental first exit.
- THEN Immersive media viewer returns without misfiring media page swipe.
