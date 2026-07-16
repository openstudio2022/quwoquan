# cold-start-performance

## 归属

- Journey：应用冷启动 → 品牌欢迎 → 主壳
- L1_domain_service：`runtime`
- L2_business_capability：`runtime-client-foundation`
- L3_story：`cold-start-performance`
- 验收：`GWT + UAT`；证据为 `local_contract + user_acceptance`，`api_integration` 不适用

## 用户目标

- 点开应用后尽快看到稳定的品牌终态，不出现被拉伸的整屏图、第二套原生动画或长时间空蓝。
- Flutter 首帧稳定后立即完整播放一次「全开 → 逆序聚拢 → 顺时针逐瓣绽放」，初始化与动效并行。
- Shell 可构建时一轮结束即进入；正常目标为进程启动后 3 秒内完成 Shell 首帧。
- 偶发初始化偏慢时用最多两次重放和一行提示承接；任何可控启动不得晚于进程启动后 6 秒离开欢迎页。

## 时间契约

`StartupWelcomeTiming.production` 是唯一生产默认值：

| 阶段 | 时长 |
|---|---:|
| 原生/Flutter 终态接管 hold | 90ms |
| 逆序聚拢 | 单瓣 240ms、stagger 25ms，总计 415ms |
| 花苞停顿 | 70ms |
| 顺时针绽放 | 单瓣 500ms、stagger 45ms，总计 815ms |
| 全开稳定 | 90ms |
| 首轮合计 | 1480ms |
| 单次重放 | 1390ms |
| 正常 Shell 首帧目标 | ≤3s |
| 欢迎页硬退出上限 | ≤6s |
| 最大重放 | 2 次 |

- `6s` 是从 Android Activity / iOS AppDelegate / Web bootstrap 最早单调时钟起算的硬上限，不是最短停留时间。
- 测试不得改写生产默认值；短时测试只通过 `StartupWelcomeTiming.test` 与 fake clock 注入。
- Flutter 首帧已经消耗大部分预算时，可压缩一次完整周期，比例不得低于 `0.65`；预算不足时保持全开 90ms 内直接进入降级 Shell。

## 状态机

`nativeStatic → handoffHold → gathering → budPause → blooming → openSettle → ready/replay/degraded → shellFirstPaint → fadeOut → overlayRemoved`

- `shellEntryReady` 只表示 Router、Provider 与安全 Shell 可构建，不等待首页、聊天、资料或远端同步。
- readiness 在动效中只锁存，只能在 `openSettle` 全开边界决定退出。
- 首轮未 ready 才显示单行 `启动中，马上进入` 并进入 replay 1；每轮结束重新检查，最多 replay 2。
- 只有剩余预算足够完整播放下一轮并预留 120ms Shell 转场时才重放。
- `onFinish` 使用 terminal latch，readiness、deadline、生命周期恢复与 cycle completion 竞争时整个生命周期恰好调用一次。
- 进入后台暂停 controller，但单调时钟继续；恢复时若超过硬期限，直接进入降级 Shell。
- `disableAnimations=true` 时保持全开静态终态，不做折叠，也不得无限等待。

## 视觉与原生边界

- Android/iOS 原生层只显示自适应渐变背景与同源透明品牌簇，不实现 controller、提示、重放或动画进度。
- Android 12+ 必须使用同源的静态花瓣 icon，避免系统 SplashScreen API 忽略普通 `windowBackground` 品牌簇后退化成纯蓝屏；该 icon 不得包含动画、提示、状态或进度镜像。Launcher 直接进入 `MainActivity`，不得恢复 `StartupActivity`、`NativeWelcomeView` 或 overlay。
- Flutter `WelcomeScreen` 是唯一动效页面；`/welcome` 使用 `WelcomeFlowMode.entry`，固定一轮、零重放、不依赖 startup readiness。
- 每片花瓣使用 `bloomAmount ∈ [0,1]`：`0` 是历史花苞态，`1` 是全开终态；全开不应用动态变换，和原生静态终态、应用图标保持 identity。
- 历史花苞视觉因子固定为 `easeOutCubic(0.24)=0.561024`；`visualFactor=lerp(0.561024, 1, bloomAmount)`。
- 花瓣宽高、花瓣中心半径、透明度和阴影强度统一使用 `visualFactor`；宽高比全程保持 `52:94`，中心半径从 `54×0.561024` 单调增加到 `54`。
- 聚拢使用 `easeInOutCubic` 并按 `7→0` 逆序；绽放使用远端基线的 `easeOutCubic` 并按 `0→7` 顺时针逐瓣执行。
- 禁止 `Matrix4.rotateX/Y`、透视 `setEntry`、`scaleY`、宽高分别插值、spring 或 overshoot；平面品牌标识不使用缺乏深度线索的伪 3D 折叠。
- 单一 `AnimationController` 通过纯函数时间轴计算八片花瓣，不恢复八控制器和 Timer 队列。
- 花蕊、标题、slogan 和品牌簇位置固定；重放提示限一行、24px 高，不使用卡片或阶段列表。

## Shell 与失败边界

- Router deferred library 从欢迎页可见后并行预加载，不串行追加在动效之后。
- 欢迎终态结束后先渲染正常 Shell；Router 构建失败则渲染可操作的安全错误 Shell，禁止回到欢迎页。
- Shell 首帧在欢迎层背后出现后，欢迎静态终帧用 120ms opacity 淡出；动画回调异常时同一 120ms 预算的 terminal fallback 必须移除 Flutter 欢迎层，禁止已画出 Shell 仍被欢迎层遮住。
- auth、appearance、日志、realtime、analytics 和 startup prerequisites 均为 best-effort；失败记录 `failureKind/sourceCode/requestId/traceId`，不得阻断欢迎页退出。
- 首页与业务页面继续由各自的骨架、缓存、失败和重试生命周期承接，不新增客户端私有错误码。

## 指标与告警

| 指标 | 定义 / 目标 |
|---|---|
| TTID | 品牌静态终态可见；P50 ≤1s、P95 ≤2s |
| `shellFirstPaintMs` | `processStart → shellFirstPaint`；正常目标 ≤3s |
| `welcomeExitMs` | `processStart → welcomeExit`；硬门 ≤6s，超限率 0 |
| `overlayRemovedMs` | `processStart → Flutter 欢迎层实际移除`；硬门 ≤6s，超限率 0 |

`startup_welcome_sequence` 必须记录：`phase`、`motionSpecVersion=petal_bloom_v2`、`cycleIndex`、`replayCount`、`deadlineOrigin`、`elapsedSinceProcessStartMs`、`remainingBudgetMs`、`readyAtCycleStart`、`readyAtCycleEnd`、`hintVisible`、`motionReduced`、`animationCompressed`、`exitReason`、`buildFrameP95Ms`、`rasterFrameP95Ms`、`shellFirstPaintMs`、`overlayRemovedMs`。

告警阈值：

- replay 1 比例 >5%
- replay 2 比例 >0.5%
- `degraded/deadline` 比例 >0.1%
- 任一 `welcomeExitMs > 6000`
- 任一 `overlayRemovedMs > 6000` 或字段缺失
- 动效期间单帧 >32ms 连续两帧

## Out of Scope

- 恢复原生动态欢迎、原生提示或 MethodChannel 动画 handoff
- 为等待首页业务数据延长欢迎页
- 用 debug 启动耗时替代 profile/release 商用结论
- 把模拟器截图或 build 成功记录为 Android/iPhone 真机 UAT
