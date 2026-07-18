# cold-start-performance

## 归属

- Journey：应用冷启动 → 品牌欢迎 → 主壳
- L1_domain_service：`runtime`
- L2_business_capability：`runtime-client-foundation`
- L3_story：`cold-start-performance`
- 验收：`GWT + SIT + UAT`；证据为 `local_contract + api_integration + user_acceptance`。
  其中状态机与视觉合同以本地契约为主，匿名启动遥测接入、幂等、投影和告警以
  `api_integration` 为主，真机/网页完整路径以 `user_acceptance` 为主。

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

## 启动故障终态合同

- `runApp` 前的配置、绑定或初始化失败不得只写 Zone 日志。最小 Flutter 绑定建立后，
  必须挂载不依赖 Router、Repository 或远端配置的恢复根；恢复根显示结构化、脱敏的
  失败语义，并提供重新尝试或支持引导。
- Root 在首个 Flutter 帧提交时即武装绝对截止，不能等待 Welcome 可见回调。该截止从
  原生/Web 最早单调时钟起算；`onFinish`、Router 预加载、生命周期恢复、observer
  异常和 shell 首帧彼此竞争时，只能单向进入 `safeRecovery`、`safeShell` 或
  `routerShell` 之一。
- Router deferred load 有单次共享的、带超时的尝试状态。加载失败、永不完成或 Router
  builder 抛错时，显示可操作安全 Shell；重试创建新的受控加载尝试，不能仅重绘既有
  失败 future。
- Android/iOS 在前台预算内未收到 Flutter renderer 首帧确认时显示无动画原生恢复面，并把该
  attempt 原子写入本地 journal；后台暂停预算，恢复后重新判断。收到首帧确认后原生层只能
  记录 `startup_safe_terminal_slow`，不得覆盖已可见的 Flutter 恢复根、Welcome 或 Shell。
- 每个 attempt 在首次 arm 时固定单一单调时钟 origin；native process clock 迟到只能补充
  诊断，不能重新 arm、rebase 或改变该 attempt 的绝对 deadline。
- 原生“重试”必须生成新的 attemptId，并隔离旧 watchdog/journal；`Activity.recreate()` 不是
  进程冷启动，不能被记录或宣称为冷启动重试。
- 安全 Shell 或 Router Shell 的真实首帧绘制后，欢迎 overlay 才能在剩余 120ms 预算内
  淡出和移除；`child == null`、Router redirect/error 或失败回调不得退化为空白页。

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

## 启动遥测与隐私

- 每次启动由 native/Web 最早阶段生成 `StartupAttempt`，以 `attemptId + sequence` 作为
  幂等主键。该标识只能用于单次启动下钻，禁止作为 Prometheus label 或用户身份。
- 统一阶段为 `native_pre_flutter`、`dart_bootstrap`、`configuration_validation`、
  `flutter_first_frame`、`router_preload`、`router_ready`、`router_failure`、
  `shell_first_paint`、`home_feed_first_usable` 和 terminal/recovery；每条记录只含
  phase、单调耗时、终态/恢复面、平台、版本、环境与脱敏 failure code/source。
- `home_feed_first_usable` 只在默认推荐首页的非空内容卡片已经完成首帧、且欢迎遮罩已经
  实际移除后记录；Router ready、Provider `AsyncData`、空态、错误态、其他频道与后台
  `IndexedStack` 页面均不得伪造该阶段。
- 首帧、失败、恢复和 attempt summary 100% 写入容量受限的本地 journal；正常详细阶段可
  受控采样，但每次启动至少保留一条 summary。journal 不按登录 actor 分区，只有服务端
  ACK 覆盖整批稳定 eventId 后才能删除，零 ACK 或部分 ACK 必须保留重试。
- `/ops/startup-events` 是专用、受限、固定 schema 的匿名接收面；它复用 Ops 投影但不
  放宽 `/ops/events` 的登录主体要求。客户端和服务端都必须拒绝用户标识、原始异常、
  堆栈、token、业务文本及未声明字段。
- Android/iOS 原生 fatal/timeout 仅落盘，下一次成功启动补传；Web 使用 IndexedDB，
  `sendBeacon` 仅作 pagehide 加速，不能替代可恢复 drain。

## 指标与告警

| 指标 | 定义 / 目标 |
|---|---|
| TTID | 品牌静态终态可见；P50 ≤1s、P95 ≤2s |
| `shellFirstPaintMs` | `processStart → shellFirstPaint`；正常目标 ≤3s |
| `welcomeExitMs` | `processStart → welcomeExit`；硬门 ≤6s，超限率 0 |
| `overlayRemovedMs` | `processStart → Flutter 欢迎层实际移除`；硬门 ≤6s，超限率 0 |

`startup_welcome_sequence` 是本地启动探针事实，必须记录：`phase`、`motionSpecVersion=petal_bloom_v2`、`cycleIndex`、`replayCount`、`deadlineOrigin`、`elapsedSinceProcessStartMs`、`remainingBudgetMs`、`readyAtCycleStart`、`readyAtCycleEnd`、`hintVisible`、`motionReduced`、`animationCompressed`、`exitReason`、`buildFrameP95Ms`、`rasterFrameP95Ms`、`shellFirstPaintMs`、`overlayRemovedMs`。它只进入设备/Web 发布 UAT 证据，不再投影为不存在生产者的 `ops_events_total` 或 `ops_event_metrics_*`。

启动投影必须产生 `ops_startup_phase_total` 和阶段耗时 histogram；标签只能包含低基数
`phase`、`outcome`、`platform`、`runtime_env` 与 `recovery_surface`。Mongo→ES 与指标
投影使用可重试 outbox/DLQ，投影失败、journal 丢弃、未终态 attempt 和补传延迟均需
可查询和可告警。

`ops_startup_phase_duration_seconds` 的首帧 P95 不得超过 2 秒、`shell_first_paint`
阶段 P95 不得超过 3 秒；`native_pre_flutter → terminal` 漏斗缺口超过 1%、`recovery`
比例超过 0.1% 或任意 `terminal/journal_drop` 都必须触发告警。上述指标只由
`/ops/startup-events` 新插入的受限事件生产，不能以旧 Analytics/AppLog 的采样事件替代。

在线告警只使用受限启动遥测的低基数阶段指标，以及 SLS 中 100% 采集的 `app_startup`
产品事件。`app_startup` 的内容可用 P95 超过 3 秒或 `hasError` 比例超过 0.1% 时告警。

以下阈值属于 Android、iPhone 与 Web 发布 UAT 硬门，由启动探针报告阻断放量，不冒充在线指标：

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
