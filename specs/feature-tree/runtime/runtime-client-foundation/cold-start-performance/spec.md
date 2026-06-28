# cold-start-performance

## 归属

- Journey：应用冷启动 → 品牌欢迎 → 主壳
- L1_domain_service：`runtime`
- L2_business_capability：`runtime-client-foundation`
- L3_story：`cold-start-performance`

## 目标

release 中端 Android 真机与 iPhone 真机冷启动 TTID（品牌欢迎首帧可见）达到：

- P50 ≤ 1000ms
- P95 ≤ 2000ms

600ms 内仅允许品牌蓝过渡屏，不得长时间 plain `#050608` 无反馈。

## 指标定义

| 指标 | 定义 |
|------|------|
| TTID | 探针 `brandedOrContentVisible` 或 Dart `welcomeShownMs` |
| TTI | 主壳首页可交互（独立 Story，不与 TTID 混报） |
| 分段 | `activity_on_create` → `engine_configured` → `runAppMs` → `firstFrameMs` → `welcomeShownMs` → `welcomeWindowInitMs` |

## 架构约束

- 原生层禁止花瓣/文案；Flutter `WelcomeScreen` 为唯一品牌欢迎实现
- 业务 IO 不得出现在 `runApp` 前；auth restore 不得早于 `markWelcomeShown`
- 欢迎完成前不得 eager 构建 `GoRouter` / 全量路由 import 图
- Android 高 risk 插件（RTC / 创作）允许延后注册，首次进入对应入口前必须 `ensure*`

## Out of Scope

- 缩短欢迎动效（TTID 达标后再评估）
- 恢复 native 镜像欢迎页
- 用背景同色冒充「变快」
