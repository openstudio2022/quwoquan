# L3 特性：全局无底栏页面边缘返回 Story

## 最小价值点

用户离开底栏根页进入详情、搜索结果、聊天详情、设置、主页实体、资料子页等无底栏页面后，可通过平台原生边缘返回手势回到上一页，而不是停留、退出 App 或跳到硬编码兜底 tab。

## 归属

- 领域服务：`runtime`
- 业务能力：`native-edge-gesture-navigation`
- 关联 Scenario：`global-route-edge-pop-contract`

## 行为规则

- Given：用户位于非底栏根路由，当前路由栈存在上一页。
- When：用户发起平台原生 back 手势。
- Then：App 返回上一页，并保持业务页面状态与埋点退出一致。
- iOS：只承认 leading edge interactive pop；中文 LTR 场景即左边缘。
- Android：左右边缘 back / predictive back 均进入同一 Router pop。

## 接口契约

- Page factory contract：普通非 shell 页面必须通过 `AppRoutePageFactory` 构造平台 Page。
- Platform policy contract：iOS / Android 差异只存在于 `NativeBackNavigationPolicy`。
- Back guard contract：需要业务拦截的页面只暴露 guard，不直接决定平台退出。
- Route fallback contract：非根页优先 pop；只有无法 pop 且策略允许时才进入根页退出保护。

## 验收关注点

- `MaterialApp.router` 下普通页面不再因默认 Material route 破坏 iOS interactive pop。
- 新增普通页面不得使用未登记的 `GoRoute.builder` 绕过 Page 工厂。
- 全屏搜索、创作、通话、WebView 等特殊页面必须显式声明 route kind 或 guard。
- 返回行为不依赖单页自写 `context.canPop() ? pop : go(...)` 作为主要路径。
