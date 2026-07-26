# L3 Story：冷启动安全进入与致命异常恢复 (`cold-start-performance`)

> 所属能力：[`runtime-client-foundation`](../spec.md)
>
> Journey / Scenario：[`JNY-002 / SCN-005`](../../../spec.md#scn-005)
>
> 设计归属：[L2 DEC-002](../design.md#dec-002)

## 1. 用户价值

作为启动应用的用户，
我希望应用能够安全运行时直接进入登录页、首页、新用户流程或降级 Shell，只有确实无法安全启动时才进入确定、克制且始终可操作的恢复页，
从而避免白屏、技术信息暴露、误判故障和无意义的重复重试。

## 2. 范围与非目标

### In Scope

- Android/iPhone 正常冷启动、Flutter Engine、根组件、必要数据库、核心配置与根依赖的致命失败边界。
- 同 Build 上一进程在进入安全 Shell 前发生且有平台强证据的硬崩溃恢复。
- 启动恢复 S0 检查中、S1 有新版、S2 已最新、S3 检查未完成四个状态。
- 原生最小恢复页、版本确认、iOS App Store、Android 官网 APK 和官方网页版恢复。
- 脱敏异常先保存、后异步上报与后续补报。
- 正常启动性能采样、Welcome 动效和安全 Shell 交接。

### Out of Scope

- 普通断网、接口超时、登录失效、权限拒绝、非关键模块故障和可局部降级错误。
- 只有启动等待超时但没有捕获到致命异常的情形。
- 启动恢复页的重试、自动重启、自动重复跳转商店或下载页。
- 应用内 APK 下载器、iOS 应用内安装、强制退出应用。
- 启动尝试 ID、诊断编号、异常指纹和启动检查点列表。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 能进入安全 Shell 就不得显示恢复页

- 正常启动目标仍为 3 秒进入 Shell；启动时限只用于性能观测和告警，不作为致命异常判定。
- 登录页、首页、新用户流程或明确可安全运行的降级 Shell 首帧完成后，当前 Build 标记为已进入安全 Shell并清除该 Build 的启动失败状态。
- 普通网络、登录、权限、业务接口或非关键依赖失败必须留在应用内按所属错误语义降级。

<a id="req-002"></a>
### REQ-002 启动致命异常采用闭集判定

- Flutter Engine、根组件、必要数据库、核心资源或配置、无安全降级的必要依赖、根路由或主容器确认无法创建时停止后续初始化并进入 S0。
- Android 只依据同 Build 的 Java 未处理异常或 `ApplicationExitInfo` crash/native crash，iOS 只依据同 Build 的未处理 NSException 或后来到达的 MetricKit crash diagnostic 判定上一进程启动崩溃。
- 用户强制结束、系统回收、低内存终止、设备关机或只有未完成标记不得判为启动崩溃。

<a id="req-003"></a>
### REQ-003 启动恢复状态由版本服务可靠推进

- S0 固定显示“应用暂时无法启动／正在检查可用版本／正在检查…／使用网页版”，网页版从首帧起可用。
- 版本服务确认远端 Build 大于当前 Build 后进入 S1，显示“当前版本需要更新／更新后即可正常启动／前往更新／使用网页版”。
- 版本服务确认当前 Build 已是最新后进入 S2，只显示“当前已是最新版本／请使用网页版继续／使用网页版”。
- 版本检查在可见截止时间内未完成时进入 S3，只显示“应用暂时无法启动／请使用网页版继续／使用网页版”；随后获得可靠结果可平滑进入 S1 或 S2。
- 本地缓存、网络失败或解析失败不得推断“需要更新”或“已是最新版本”。

<a id="req-004"></a>
### REQ-004 iOS 与 Android 使用不同受信更新通道

- iOS 的“前往更新”只打开已验证的 App Store 产品页；不能在应用内下载安装或强制退出。
- Android 的“前往更新”只打开趣我圈官方 HTTPS 下载端点，下载端点重定向至受信 CDN 上的当前正式签名 APK；不打开第三方商店或来源不明 APK。
- 通用官网下载页按 User-Agent 自动识别 iOS、Android/鸿蒙或桌面；iOS 进入 App Store，Android/鸿蒙进入 APK 下载，桌面提供两个明确入口。
- 更新或下载页返回前台后只重新读取本地 Build 和查询版本，不自动重新启动流程或重复打开外部页面。

<a id="req-005"></a>
### REQ-005 恢复页只表达事实、状态和动作

- 页面只包含系统状态栏、标题、副标题、一个固定上方操作槽、一个固定下方操作槽和系统底部安全区。
- 不显示 Logo、花瓣、图标、插画、卡片、错误红色、技术原因、错误码、诊断编号、日志状态、版本号、客服或其他说明。
- 背景、文字、按钮、间距、圆角与交互热区只使用现有语义 Token，并向原生资源生成等价值。
- 状态切换只使用 80ms 旧内容淡出、120ms 新内容淡入和 120ms 按钮颜色/透明度过渡，内容簇位置保持固定。

<a id="req-006"></a>
### REQ-006 致命异常日志静默且不阻塞恢复

- 异常数据只包含 `occurredAt`、`appVersion`、`buildNumber`、`platform`、`osVersion`、`deviceModel`、`errorSource`、`errorType`、`errorMessage`、`stackTrace`。
- 错误摘要和堆栈上传前脱敏；禁止诊断编号、启动尝试 ID、发布渠道、检查点、异常指纹、身份与业务内容、Token/Cookie/请求头、用户名路径和完整 URL 查询参数。
- 异常先写入加密本地队列，再展示恢复页并异步上传；失败不改变页面、更新、下载或网页版状态。
- 队列最多 20 条、最长 7 天、单条不超过 64KiB；消息最多 2KiB、堆栈最多 32KiB；损坏记录必须安全丢弃。

## 4. 契约引用

- 版本与下载：`quwoquan_service/services/product-ops-service/contracts/product_ops/app_release/operations.yaml`
- 恢复异常：`quwoquan_service/services/product-ops-service/contracts/product_ops/recovery_failure/operations.yaml`
- 受信公开链接：`quwoquan_service/contracts/metadata/_shared/link_templates.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 正常、缓慢和可降级启动进入安全 Shell

- GIVEN 启动没有闭集中的致命异常，或只发生等待超时、网络、登录、权限或非关键依赖故障。
- WHEN 应用完成可用根路由或降级 Shell 的首帧。
- THEN 用户进入应用而不是恢复页，当前 Build 被标记为已进入安全 Shell，启动性能另行记录。

<a id="gwt-002"></a>
### GWT-002 启动致命异常无重试并可靠分流

- GIVEN 当前进程捕获启动致命异常，或平台强证据确认同 Build 上次在安全 Shell 前崩溃。
- WHEN 恢复页检查版本。
- THEN 首帧立即提供网页版；有新版时 iOS 进入 App Store、Android 经官网 HTTPS 端点下载正式签名 APK，已最新或未完成时提供网页版且不存在启动重试。

<a id="gwt-003"></a>
### GWT-003 异常日志失败不影响恢复

- GIVEN 无网络、日志服务失败、本地队列已接近上限或单条记录损坏。
- WHEN 启动致命异常进入恢复状态。
- THEN 页面和外部恢复动作立即可用，队列按加密、脱敏、上限和补报规则收敛，日志故障不会产生第二次崩溃。

## 6. 依赖

- 前置要求：[`runtime-client-foundation`](../spec.md) 的范围、要求与 SIT。
- 协作 Story：[`public-content-web-entry`](../public-content-web-entry/spec.md)、[`unrecoverable-runtime-recovery`](../unrecoverable-runtime-recovery/spec.md)。
- 父级设计：[L2 DEC-002](../design.md#dec-002)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 正式商店、签名 APK 与真机故障证据

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前缺少正式 iOS App Store 产品 ID、Android 生产签名密钥、官网 CDN 正式 APK URL，以及 Android/iPhone 真机硬崩溃与外部跳转录像证据。
- 完成判定：`GWT-002` 在 Alpha、Beta、Gamma 和 Prod 对应真实端点完成，且 Prod APK 签名、SHA-256、包名与发布配置一致。
- 依赖：Apple 开发者后台、Android 生产签名 Secret、官方域名/CDN 与发布权限。

<a id="open-002"></a>
### OPEN-002 iOS signal 类崩溃即时分类边界

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：在不新增远程 Crash SDK、不安装 signal handler 的约束下，部分 Swift fatal、abort 与 signal 崩溃只能在 MetricKit 后续送达诊断后确认，无法保证下一次启动即时进入恢复页。
- 完成判定：NSException、MetricKit 与用户终止负例均有真机证据，未覆盖边界在发布说明和监控中保持可见。

<a id="open-003"></a>
### OPEN-003 静默异常队列端云闭环

- 类型：`implementation_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：旧启动遥测仍包含 attempt/checkpoint 语义，尚未切换为严格十字段的恢复异常、端侧加密队列与断网补报，不能证明日志失败不会影响恢复操作。
- 完成判定：`GWT-003` 由端侧队列、服务接收、本地损坏负例和断网补报测试直接 `spec_ref` 证明，旧 `/ops/startup-events` 不再承载恢复异常。
- 依赖：`product-ops-service` 的 `recovery_failure` 契约与 iOS/Android 安全存储实现。
