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
- 同一制品身份上一进程在进入安全 Shell 前发生且有平台强证据的硬崩溃恢复；制品身份至少绑定平台 Build 与环境运行配置摘要，禁止跨环境或重打包复用失败标记。
- 启动恢复 S0 检查中、S1 有新版、S2 已最新、S3 检查未完成四个状态。
- 原生最小恢复页、版本确认、公众 iOS PWA、Android 官网 APK 和官方网页版恢复。
- 脱敏异常先保存、后异步上报与后续补报。
- 正常启动性能采样、Welcome 动效和安全 Shell 交接。

### Out of Scope

- 普通断网、接口超时、登录失效、权限拒绝、非关键模块故障和可局部降级错误。
- 只有启动等待超时但没有捕获到致命异常的情形。
- 启动恢复页的重试、自动重启、自动重复跳转商店或下载页。
- 应用内 APK 下载器、iOS 应用内安装、强制退出应用。
- 在恢复页向用户展示启动尝试 ID、诊断编号、异常指纹和启动检查点列表。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 能进入安全 Shell 就不得显示恢复页

- 正常启动目标仍为 3 秒进入 Shell；启动时限只用于性能观测和告警，不作为致命异常判定。
- 登录页、首页、新用户流程或明确可安全运行的降级 Shell 首帧完成后，当前 Build 标记为已进入安全 Shell并清除该 Build 的启动失败状态。
- 普通网络、登录、权限、业务接口或非关键依赖失败必须留在应用内按所属错误语义降级。
- API、Media、登录或内容服务不可达只产生 readiness 诊断和应用内恢复状态，不得创建、更新或推广启动 fatal marker。
- 系统 Splash 之后的原生静态帧与 Flutter Welcome 终态必须消费同一品牌视觉源；受支持手机视口切换时，花瓣、slogan、渐变和底部品牌名不得跳位、拉伸或回退为纯色过渡。

<a id="req-002"></a>
### REQ-002 启动致命异常采用闭集判定

- Flutter Engine、根组件、必要数据库、核心资源或配置、无安全降级的必要依赖、根路由或主容器确认无法创建时停止后续初始化并进入 S0。
- 受支持构建入口必须在安装前验证完整 runtime package；缺失环境、Gateway、Media、RTC 或 native runtime identity 是构建失败，不得把可预防的开发/打包错误包装成一次“成功启动到恢复页”。运行时配置校验仅是畸形或被篡改制品的最后防线。
- Android 的 exported launcher 必须是 Flutter Engine、`FlutterFragmentActivity` 和插件装配之前的原生 gate：先完成平台强证据与制品身份核对，有确认致命异常时直接承载原生恢复页，无确认致命异常时才单向进入 Flutter 主 Activity。恢复分支不得创建 Flutter Engine，正常分支不得并行保留第二套启动状态机。
- iOS 必须在 `FlutterAppDelegate` 的 `willFinish`/`didFinish` 主线和 implicit Flutter Engine 之前核对同制品致命证据；恢复分支必须在 `configurationForConnecting` 阶段移除 `Main.storyboard` 并改用纯原生 recovery scene，且不得调用 Flutter AppDelegate 生命周期或注册插件，正常分支才进入唯一 Flutter 主线。
- Android 只依据同一制品身份的 Java 未处理异常或 `ApplicationExitInfo` 最近一次退出明确为 crash/native crash；iOS 当前只依据同一制品身份的未处理 NSException 判定上一进程启动崩溃。无法与上轮启动窗口可靠关联的 MetricKit signal/crash diagnostic 不得直接触发恢复，边界由 `OPEN-002` 持续跟踪。
- Dart 只能以当前原生 `attemptId + canonical failureCode` 请求写入 fatal marker；原生层仅在非 Hot Restart、尚未进入安全 Shell、startup build identity 与当前 artifact identity 一致且 safe-shell 明确为 false 时接受。Hot Restart、attempt 不匹配、运行期 recovery 或安全 Shell 后请求均必须拒绝。
- 同一 artifact 若同时存在 `safeShell=true` 与 fatal marker，原生 gate 必须删除 fatal/fatalAt/queuedIdentity 并继续正常启动；artifact identity 不匹配的旧 marker 同样自愈清理。只有 `safeShell=false + 同制品 fatal` 可进入原生恢复页。
- 用户强制结束、系统回收、低内存终止、设备关机或只有未完成标记不得判为启动崩溃。

<a id="req-003"></a>
### REQ-003 启动恢复状态由版本服务可靠推进

- S0 固定显示“应用暂时无法启动／正在检查可用版本／正在检查…／使用网页版”，网页版从首帧起可用。
- 版本服务确认远端 Build 大于当前 Build 后进入 S1，显示“当前版本需要更新／更新后即可正常启动／前往更新／使用网页版”。
- 版本服务确认当前 Build 已是最新后进入 S2，只显示“当前已是最新版本／请使用网页版继续／使用网页版”。
- 版本检查在可见截止时间内未完成时进入 S3，只显示“应用暂时无法启动／请使用网页版继续／使用网页版”；随后获得可靠结果可平滑进入 S1 或 S2。
- 本地缓存、网络失败或解析失败不得推断“需要更新”或“已是最新版本”。

<a id="req-004"></a>
### REQ-004 iOS 与 Android 使用不同受信恢复通道

- 公众 iOS 不提供“前往更新”原生包动作；版本服务返回空 `updateUrl`，恢复页提供已验证的官方 PWA/网页版地址。只有已认证且设备已登记的内测成员才可由官网受控入口使用 Ad Hoc 安装通道。
- Android 的“前往更新”只打开趣我圈官方 HTTPS 下载端点，下载端点重定向至受信 CDN 上的当前正式签名 APK；不打开第三方商店或来源不明 APK。
- 通用官网下载页按可信平台提示自动识别 iOS、Android/鸿蒙或桌面；iOS 展示 PWA 安装指引，Android/鸿蒙进入 APK 下载，桌面提供 Android 下载与 iOS PWA 指引两个明确入口。
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
- 队列最多保留 20 条、最长保留 7 天，且单条不超过 64KiB。消息最多 2KiB、堆栈最多 32KiB；损坏记录必须安全丢弃。

<a id="req-007"></a>
### REQ-007 环境构建、安装与运行证据必须绑定同一启动清单

- 每次受支持构建必须生成符合 `app_launch_manifest.app_effective_launch_manifest` 共享协议的 immutable effective launch manifest；构建、安装、启动与发布证据不满足 canonical target/environment、摘要或 transport 约束时必须 fail closed。
- `quwoquan_app/run.sh -d <device>` 是显式设备选择与 transport 准备入口。裸 `flutter run` 和 IDE 直接 Flutter Debug 也必须由 Xcode/Gradle backend 在安装前按 `QWQ_ENVIRONMENT=alpha|beta|gamma` 选择同一份 canonical handoff，默认 Alpha。
- 两条路径都必须把完整 handoff、entrypoint 和全部 runtime defines 交给 Flutter resident compiler，使冷启动、Hot Reload 与 Hot Restart 消费同一环境、target 与 digest。禁止 native build phase 临时拼装第二份 URL、密钥或 release 配置。
- 本地 Debug 安装前必须执行只读 App 预检。Alpha/Beta/Gamma `test_live` 未绑定内容或 runtime、Provider、内容证据不健康时只记录结构化 warning，并进入 `no_active_release`/typed unavailable 安全 Shell；`content-live`、immutable candidate 与 Prod 的 release、readiness、rollback/replay、首页、视频书、Creator/头像及媒体任一必要证据不成立时仍 fail closed，并只输出首个 typed blocker。该分层不改变正式 App 的网络恢复语义，普通运行期网络或服务故障仍进入安全 Shell 内的页面级恢复。
- Android `BuildConfig` 与 iOS `QWQNativeRuntime.plist` 必须内嵌 effective launch manifest 摘要；启动失败标记、runtime probe 和制品 provenance 必须回报同一摘要，禁止跨 target、跨环境或重打包复用。
- package-only 四环境编译只能证明组件可构建，不得标记为 runtime UAT。运行证据必须来自真实 `MAIN/LAUNCHER` 或 iOS scene 启动，且包含非 `unknown` 的本次 attempt ID、当前 motion contract、safe terminal、Gate/Main 或 scene 结果和单一 task。
- Prod Android AAB/APK 与 iOS IPA 必须先验证平台签名、禁止 Mock/test/local transport 泄漏，并证明内嵌清单摘要与发布 handoff 一致，才可从 component-ready 推进到 deployable。
- Debug、Profile 与 Release 对同一启动错误必须渲染同一 canonical surface；Debug 只允许追加脱敏日志与诊断面，不得保留开发红屏或第二套用户终态。BuildMode 不得改变路由、数据源、空态、错误态或恢复动作。
- 应用市场可能对上传制品重签、拆分或优化；安装后启动必须回读嵌入 launch manifest 摘要、version/build 与当前签名身份，并与发布 provenance 的 source candidate 绑定验证，不得要求下载二进制与上传二进制逐字节相同，也不得因市场处理差异改变启动行为。
- 安装后首次点击图标冷启动与后续任意次点击图标启动必须读取同一嵌入 manifest 与 runtime package，进入同一安全 Shell 行为；首启只在性能采样中以 first-install 维度区分，不得拥有独立业务分支。

## 4. 契约引用

- 启动清单：`quwoquan_service/contracts/metadata/_shared/app_launch_manifest.yaml`
- 版本与下载：`quwoquan_service/services/product-ops-service/contracts/product_ops/app_release/operations.yaml`
- 版本与下载字段：`quwoquan_service/services/product-ops-service/contracts/product_ops/app_release/fields.yaml`
- 版本与下载配置：`quwoquan_service/services/product-ops-service/config/schema.yaml`
- 恢复异常：`quwoquan_service/services/product-ops-service/contracts/product_ops/recovery_failure/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 正常、缓慢和可降级启动进入安全 Shell

- GIVEN 启动没有闭集中的致命异常，或只发生等待超时、网络、登录、权限或非关键依赖故障。
- WHEN 应用完成可用根路由或降级 Shell 的首帧。
- THEN 用户进入应用而不是恢复页，当前 Build 被标记为已进入安全 Shell，启动性能另行记录。
- AND 系统 Splash、原生静态帧与 Flutter Welcome 在受支持视口保持品牌视觉连续，不出现第二套花瓣、纯色蓝屏或静态帧拉伸。

<a id="gwt-002"></a>
### GWT-002 启动致命异常无重试并可靠分流

- GIVEN 当前进程捕获启动致命异常，或平台强证据确认同一制品身份上次在安全 Shell 前崩溃。
- WHEN 恢复页检查版本。
- THEN Android 在创建 Flutter Engine 和注册插件前由原生 gate 进入恢复页。
- THEN 无确认致命异常时 gate 只进入 Flutter 主 Activity 且不显示恢复页。
- AND iOS 在调用 Flutter AppDelegate 启动生命周期和创建 implicit Flutter Engine 前进入原生恢复 root；恢复分支不初始化 Flutter 或商业插件。
- AND 缺失 runtime package 的 Android/iOS 构建在安装前失败；恢复页、safeRecovery 或 Flutter 首帧均不得作为构建入口可用性的成功证据。
- AND 连续冷启动、Hot Restart 与再次冷启动中，每个 attempt 的 `launchMode` 均与本次入口绑定为 `canonical_launcher` 或 `direct_flutter_run`，且 `configurationState=complete`；Hot Restart 的 fatal 请求被拒绝，安全 Shell 与 fatal 矛盾 marker 在 Flutter Engine 创建前自愈清理。
- AND 首帧立即提供网页版。有新版且存在当前平台可安装通道时，Android 经官网 HTTPS 端点下载正式签名 APK，公众 iOS 继续使用 PWA/网页版。已最新、没有合规原生通道或检查未完成时提供网页版且不存在启动重试。

<a id="gwt-003"></a>
### GWT-003 异常日志失败不影响恢复

- GIVEN 无网络、日志服务失败、本地队列已接近上限或单条记录损坏。
- WHEN 启动致命异常进入恢复状态。
- THEN 页面和外部恢复动作立即可用，队列按加密、脱敏、上限和补报规则收敛，日志故障不会产生第二次崩溃。

<a id="gwt-004"></a>
### GWT-004 四环境制品与双端运行证据 fail closed

- GIVEN Alpha、Beta、Gamma、Prod 的 Android/iOS package 与对应 effective launch manifest。
- WHEN CI 执行 package purity、原生 Gate、API integration、AppRoot `UAT-003` 和设备启动矩阵。
- THEN package、native identity、runtime probe 与发布 provenance 的环境、target、URL、entrypoint 和摘要完全一致；Android launcher task 唯一，iOS fatal recovery scene 不创建 implicit Flutter Engine。
- AND 缺失真实设备、签名、hosted Prod、telemetry readback 或公网恢复通道时保持 `GATE_BLOCK`/`OPEN-001`，不得以编译成功、模拟器或 package-only 报告替代。

<a id="gwt-005"></a>
### GWT-005 安装后首启、后续图标启动与市场身份回读一致

- GIVEN 设备经任一有效渠道完成安装——脚本安装、打包 Debug 安装、Android `prod-sim` exact Release、Android/iOS `prod-hosted` Release、应用市场客户端安装（含市场重签/优化后的制品）、官网签名 APK，或在旧版本上覆盖升级；iOS Simulator Debug 不计作 Release 安装。
- WHEN 首次点击图标冷启动，随后杀进程再次点击图标启动。
- THEN 两次启动读取同一嵌入 launch manifest 与 runtime package，进入同一安全 Shell 行为；首启只在性能采样中携带 first-install 维度。
- AND 市场安装制品的回读证明当前签名身份、version/build 与发布 provenance 的 source candidate 绑定一致，市场处理差异不改变任何启动行为。
- AND Debug 与 Release 对同一注入启动错误渲染同一 canonical surface，Debug 仅追加脱敏诊断。
- AND 覆盖升级后的启动行为指纹与全新安装一致，不存在升级用户独有的启动死路。

## 6. 依赖

- 前置要求：[`runtime-client-foundation`](../spec.md) 的范围、要求与 SIT。
- 协作 Story：[`public-content-web-entry`](../public-content-web-entry/spec.md)、[`unrecoverable-runtime-recovery`](../unrecoverable-runtime-recovery/spec.md)。
- 父级设计：[L2 DEC-002](../design.md#dec-002)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 真机致命异常消费正式恢复通道证据

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前缺少 Android/iPhone 真机硬崩溃后消费正式 app release 与 Web/PWA 发布回执的恢复分流、外部跳转和无重试录像证据；生产签名、CDN、DNS/TLS 与 PWA 材料分别由协作 Story 拥有，本 Story 不复制其发布事实。
- 完成判定：`GWT-002` 在 Alpha、Beta、Gamma 和 Prod 对应真实端点完成；每个 CaseResult 绑定 `app-release-recovery-routing` 与 `public-content-web-entry` 的正式回执，并证明 Android/iPhone 真机只消费 canonical 恢复通道。
- 依赖：[`app-release-recovery-routing`](../../../product-ops-growth/product-control-plane-foundation/app-release-recovery-routing/spec.md) `OPEN-001`、[`public-content-web-entry`](../public-content-web-entry/spec.md) `OPEN-004`、实体设备与发布权限。

<a id="open-002"></a>
### OPEN-002 iOS signal 类崩溃即时分类边界

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：在不新增远程 Crash SDK、不安装 signal handler 的约束下，部分 Swift fatal、abort 与 signal 崩溃只能在 MetricKit 后续送达诊断后确认，无法保证下一次启动即时进入恢复页。
- 完成判定：`GWT-002` 的致命异常分流判定在 NSException、MetricKit 与用户终止负例上均有真机证据，未覆盖边界在发布说明和监控中保持可见。

<a id="open-003"></a>
### OPEN-003 静默异常队列端云闭环

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：Prod 真实 Elasticsearch Log sink Provider、Android/iPhone 受保护真机与可供销毁的账号尚未就绪，无法补齐恢复异常断网补报的真实环境证据。
- 完成判定：`GWT-003` 在受保护真机上证明端侧加密队列、服务接收、损坏记录安全处置和断网补报；旧 `/ops/startup-events` 不承载恢复异常。
- 依赖：Prod Elasticsearch Log sink endpoint、受保护认证材料与 Provider receipt，受保护 Android/iPhone 设备与可销毁账号。

<a id="open-004"></a>
### OPEN-004 安装后首启与市场身份回读证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺安装后首启与后续图标启动等价、Debug/Release 同 surface、市场处理后身份回读的完整实现与真实验收证据。市场渠道依赖外部账号、审核与真机（见 [`environment-topology-and-packaging OPEN-003`](../../runtime-config/environment-topology-and-packaging/spec.md#open-003)）；非市场渠道的首启等价与同 surface 断言可先在本地设备矩阵闭环。
- 完成判定：`GWT-005` 的全部结果子句由真实测试逐条绑定（gwt-005.t1..t5）：脚本/Debug/官网 APK/覆盖升级路径由设备矩阵 runner 产出安装回执与启动回读，市场路径绑定真实市场安装回执；缺失渠道保持显式阻断。
