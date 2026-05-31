# 原生边缘手势导航规格

## 定位

`native-edge-gesture-navigation` 是 `runtime` 领域服务下的业务能力，负责 iOS / Android 屏幕左右边缘手势在不同页面层级中的导航安全、冲突仲裁和用户可感知体验。

## 范围

### In Scope

- 全局普通二级/三级页面的原生边缘手势返回上一页。
- 沉浸式媒体浏览器边缘滑动返回上一页。
- 主页根页第一次边缘滑动提示再次滑动退出。
- 主页根页第二次边缘滑动在保护窗口内退出或交给系统返回。
- iOS 与 Android 的手势区域、触发阈值、系统返回动画和提示差异。
- 媒体左右切换与边缘返回手势的冲突仲裁。
- 路由 Page 工厂、防腐策略层与根壳返回状态机的统一契约。

### Out of Scope

- 单个内容类型的媒体翻页业务规则。
- Android/iOS 系统级手势设置本身。
- 非根页业务表单未保存退出保护。
- iOS 根页主动退出 App；iOS 原生语义下根页无可 pop 栈时不模拟退出。

## Story 列表

- `global-route-edge-pop-contract`：无底栏页面通过平台原生边缘手势返回上一页。
- `immersive-media-edge-swipe-back`：沉浸式媒体浏览器边缘滑动返回。
- `home-edge-swipe-exit-guard`：主页根页边缘滑动退出保护。

## 平台口径

- iOS：遵循 `UINavigationController.interactivePopGestureRecognizer` 的 leading-edge pop。中文 LTR 场景为左边缘返回；根页不主动退出应用。
- Android：遵循系统手势导航与 predictive back，左右边缘均可触发 back；底栏根页需要二次返回保护。
- Flutter：业务页面不直接判断平台。页面只声明路由类型和可选返回 guard，平台差异由 `NativeBackNavigationPolicy` 与路由 Page 工厂屏蔽。

## SIT 关注点

- 平台差异：iOS interactive pop 与 Android predictive back / back dispatcher。
- 状态机：idle -> firstEdgeSwipeWarned -> secondSwipeExit -> reset。
- 路由承载：普通页面必须经统一 Page 工厂生成原生路由，禁止新增普通页面绕过工厂使用默认 `GoRoute.builder`。
- 冲突仲裁：媒体横滑翻页优先级低于系统边缘返回热区。
- 性能：边缘滑动首反馈延迟、返回动画 jank、误触率。
