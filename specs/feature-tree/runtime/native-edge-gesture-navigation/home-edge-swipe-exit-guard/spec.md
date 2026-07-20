# L3 特性：主页边缘滑动退出保护 Story

## 最小价值点

用户停留在主页根页面时，第一次 iOS / Android 屏幕边缘滑动不直接退出 App，而是提示再次滑动退出；第二次在保护窗口内触发退出或交给系统返回。

## 归属

- 领域服务：`runtime`
- 业务能力：`native-edge-gesture-navigation`
- 关联 Scenario：`home-edge-swipe-exit-guard`

## 行为规则

- Given：用户位于主页根路由，当前没有可 pop 的子页面。
- When：用户第一次从屏幕边缘发起返回手势。
- Then：App 显示退出保护提示，不退出。
- When：用户在保护窗口内第二次发起边缘返回。
- Then：App 退出或交给系统返回。

## 接口契约

- Root route contract：主页根路由必须能声明不可直接 pop。
- Exit guard contract：首次提示、保护窗口、二次退出状态必须统一。
- Telemetry contract：记录 firstGuard、secondExit、guardTimeout。

## 验收关注点

- iOS 与 Android 均覆盖。
- 左右边缘均覆盖。
- 保护窗口超时后再次滑动应重新提示。
- 提示反馈及时且不阻塞主页交互。
