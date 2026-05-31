# 原生边缘手势导航设计

## 能力设计目标

统一 App 级边缘返回策略，让 iOS / Android 的系统手势、Flutter Router、页面沉浸态和根页退出保护在同一状态机下工作。

## 能力边界

- runtime/app shell 拥有根页退出保护和系统 back dispatcher 集成。
- runtime/app navigation 拥有平台防腐策略与路由 Page 工厂。
- 内容沉浸 surface 提供“当前是否允许边缘返回、是否存在媒体横滑冲突”的状态。
- 业务页面不直接决定退出 App，不直接判断 iOS / Android；只暴露路由类型和可选返回 guard。

## 防腐层

```text
GoRouter route
  -> AppRoutePageFactory
  -> NativeBackNavigationPolicy
  -> CupertinoPage / MaterialPage / custom page
  -> AppNativeBackScope
  -> Router pop / root exit guard / page guard
```

### NativeBackNavigationPolicy

- iOS 实现：普通 drill-down 路由使用 `CupertinoPage`，只承认 leading edge 返回；根页无可 pop 栈时不退出应用。
- Android 实现：普通路由使用 Android 平台合适承载；系统 back / predictive back 进入根壳状态机；左右边缘均视为 back 输入。
- 策略层只描述平台能力、根页退出保护窗口和 Page 构造，不读取业务页面内部状态。

### AppRoutePageFactory

- `app_router.dart` 中普通页面必须经统一工厂构造 Page，避免 `MaterialApp.router` 下 `GoRoute.builder` 默认为 Material route 而破坏 iOS interactive pop。
- fullscreen dialog、贴底 sheet、无转场 shell、全屏搜索等特殊页面必须显式声明 `AppRoutePageKind`。
- 迁移期允许保留已登记 custom transition，但新增普通页面不得绕过工厂。

## 当前路由审计

- `ShellRoute` 根壳使用 `NoTransitionPage` + `AppNativeBackScope`，仅负责底栏根页 Android 二次退出保护。
- 普通 drill-down 页面统一使用 `appRoutePage`，由平台策略映射为 iOS `CupertinoPage` 或 Android `MaterialPage`。
- 全屏 dialog 类页面显式声明 `AppRoutePageKind.fullscreenDialog`。
- 全局搜索、搜索结果、主页选择器已收口到 Page 工厂，创作入口贴底抽屉继续保留已登记 transparent modal custom transition。
- 静态门禁 `verify_native_edge_navigation.py` 禁止新增普通 `GoRoute.builder` 与裸 `MaterialPage`。

### AppBackGuard

- 创作未保存、通话小窗、WebView 内部历史等业务拦截通过 guard contract 暴露。
- guard 的职责是“当前是否允许离开或先执行业务动作”，不得直接调用平台退出或硬编码目标 tab。
- guard 允许后，统一交回 `AppNativeBackScope` / Router 执行 pop。

## 状态机

```text
idle
  -> edgeSwipeOnNonRoot: popRoute
  -> firstEdgeSwipeOnHome: showExitGuard
  -> secondEdgeSwipeWithinWindow: exitOrSystemBack
  -> timeout: idle
```

## 冲突仲裁

- iOS：leading-edge interactive pop 区域优先于媒体横滑；中文 LTR 下仅左边缘视为系统返回。
- Android：predictive back / system back dispatcher 优先；左右系统边缘均可触发 back，Flutter 内部横滑只处理非系统边缘区域。
- Android 左右边缘与 iOS leading edge 均必须被测试覆盖，避免 RTL、横屏或媒体 viewer 自定义手势造成盲区。

## 根页退出保护

- 保护仅适用于 Android 底栏根页，且当前 Router 不可 pop、无业务 guard 拦截。
- 第一次 back 显示再次滑动退出提示；保护窗口为 2 秒。
- 2 秒内第二次 back 触发 `SystemNavigator.pop()` 或交给系统返回。
- 切换 tab、进入子页、窗口超时都会重置保护状态。
- iOS 根页不主动退出 App；如产品要求 iOS 也二次退出，必须标为自定义体验并单独评审。

## 测试切面

- `T1`：手势策略配置、页面类型、平台和保护窗口契约。
- `T2`：Widget/Provider 状态机、Page 工厂输出与 back guard 模拟。
- `T3`：Router/Navigator/back dispatcher 集成。
- `T4`：iOS / Android Patrol 旅程。

## 性能与观测

- 动作到首反馈延迟不超过 100ms。
- 返回动画无可见 jank。
- 记录边缘手势触发、取消、冲突仲裁、二次退出命中率。
