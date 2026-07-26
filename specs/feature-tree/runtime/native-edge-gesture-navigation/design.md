# L2 Design：原生边缘手势导航规格 (`native-edge-gesture-navigation`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“iOS/Android 边缘手势导航能力 SIT”需要 `global-route-edge-pop-contract`、`home-edge-swipe-exit-guard`、`immersive-media-edge-swipe-back` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：iOS/Android 边缘手势导航能力 SIT。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`global-route-edge-pop-contract`](./global-route-edge-pop-contract/spec.md)：普通非 shell 页面通过 AppRoutePageFactory 构造平台 Page。
- [`home-edge-swipe-exit-guard`](./home-edge-swipe-exit-guard/spec.md)：第二次边缘滑动在保护窗口内退出或交给系统返回。
- [`immersive-media-edge-swipe-back`](./immersive-media-edge-swipe-back/spec.md)：iOS 与 Android 均验证边缘返回成功。

## 3. 端云与数据流

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 App 级策略统一仲裁系统返回与页面横向手势
- 决策：App 级策略统一仲裁系统返回与页面横向手势。
- 理由：iOS/Android 边缘手势导航能力 SIT。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`global-route-edge-pop-contract`](./global-route-edge-pop-contract/spec.md)、[`home-edge-swipe-exit-guard`](./home-edge-swipe-exit-guard/spec.md)、[`immersive-media-edge-swipe-back`](./immersive-media-edge-swipe-back/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- `local_contract`：手势策略配置、页面类型、平台和保护窗口契约。
