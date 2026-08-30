# L2 Design：运行时客户端基础 (`runtime-client-foundation`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“为 Flutter App 提供网络、缓存、本地化、日志、媒体与语义门禁等跨域基础能力”需要 `app-locale-infrastructure`、`app-remote-config`、`app-theme-infrastructure`、`article-editor-refactor`、`cold-start-performance`、`unrecoverable-runtime-recovery`、`cross-platform-portability`、`dart-semantic-gate`、`dual-theme-page-coverage`、`entity-link-templates-metadata`、`error-permission-display-semantics`、`external-inbound-deeplink-routing`、`ios-native-page-enforcement`、`local-cache-architecture`、`metadata-driven-client-data-contract`、`page-horizontal-quality`、`page-layout-semantics`、`public-content-web-entry`、`s8-p8-semantic-token`、`unified-app-page-access` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：为 Flutter App 提供网络、缓存、本地化、日志、媒体与语义门禁等跨域基础能力。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`app-locale-infrastructure`](./app-locale-infrastructure/spec.md)：通过 ARB 与 flutter gen-l10n 生成本地化资源，并在 locale 切换后保持页面文案一致。
- [`app-remote-config`](./app-remote-config/spec.md)：冷启动首帧可在无远程配置的情况下正常进入欢迎页和首页。
- [`app-theme-infrastructure`](./app-theme-infrastructure/spec.md)：必须坚持 `Cupertino-first`：Material 仅用于兼容和平台必要能力，不得成为主要视觉语法来源。
- [`article-editor-refactor`](./article-editor-refactor/spec.md)：不可用时 **置灰**；可用时符合对比度与触控热区（≥44pt）。
- [`cold-start-performance`](./cold-start-performance/spec.md)：启动时限用于性能告警而不是致命判定，已确认致命异常由原生最小恢复层接管。
- [`unrecoverable-runtime-recovery`](./unrecoverable-runtime-recovery/spec.md)：业务 ProviderScope 外的恢复宿主持有一次性主容器重建次数和恢复终态。
- [`cross-platform-portability`](./cross-platform-portability/spec.md)：业务层不新增直接平台分支。
- [`dart-semantic-gate`](./dart-semantic-gate/spec.md)：**约束**：gate 必须调用 verify_dart_semantic，失败即阻塞。
- [`dual-theme-page-coverage`](./dual-theme-page-coverage/spec.md)：优先 **替换为语义色 + 双模式分支**；能统一走 `Theme` / `CupertinoTheme.of(context)` 的 **不重复传 `isDark`**。
- [`entity-link-templates-metadata`](./entity-link-templates-metadata/spec.md)：归因 query 解析单测覆盖注入与剥离两端。
- [`error-permission-display-semantics`](./error-permission-display-semantics/spec.md)：统一错误组件、分身页、评论区及栈页面宿主的 local_contract 同时通过。
- [`external-inbound-deeplink-routing`](./external-inbound-deeplink-routing/spec.md)：每种失败路径都有明确 UI 与文案，无静默失败。
- [`ios-native-page-enforcement`](./ios-native-page-enforcement/spec.md)：不禁止 `Material(type: transparency)` 作为 **Cupertino 子树** 的防溢出/字体渲染宿主（与现有 `AppScaffold` 模式一致）。
- [`local-cache-architecture`](./local-cache-architecture/spec.md)：feed 与 userPosts 共用 ContentQuerySnapshotStore，清理临时资源不删除 post metadata，离线内容清理可删除 query snapshot。
- [`metadata-driven-client-data-contract`](./metadata-driven-client-data-contract/spec.md)：同一 **Repository 抽象接口** 的 `Mock*` 与 `Remote*` 实现：对同一业务操作返回 **同一 codegen 类型**（或经同一 `fromMap`/工厂解析到该类型），**禁止** Mock 返回「另一套 Map 键名」而 Remote 另一套。
- [`page-horizontal-quality`](./page-horizontal-quality/spec.md)：在受支持屏宽、文字缩放和本地化文案下保持页面无横向溢出且关键动作可达。
- [`page-layout-semantics`](./page-layout-semantics/spec.md)：Cupertino 场景不混用 Material 交互组件（Checkbox/SnackBar），选择态统一 iOS 语义。
- [`public-content-web-entry`](./public-content-web-entry/spec.md)：公开内容网页同时提供可访问的 landing URL 与可恢复目标的 deep link。
- [`s8-p8-semantic-token`](./s8-p8-semantic-token/spec.md)：横向质量矩阵 **P8** 要求：间距、字阶、圆角、色等走 **语义 token**，禁止魔法数与非语义混用（与 `verify_dart_semantic.py` 同向）。
- [`unified-app-page-access`](./unified-app-page-access/spec.md)：**P4（横向质量）**：页面级 **open / return /（可选）停留** 进入 **`AppLogService`** 统一管道，与 `AppTraceContextStore` 的 `sessionId` / `pageVisitId` 对齐。

## 3. 端云与数据流

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 端侧基础能力通过稳定接口隔离平台实现和远端契约
- 决策：端侧基础能力通过稳定接口隔离平台实现和远端契约。
- 理由：为 Flutter App 提供网络、缓存、本地化、日志、媒体与语义门禁等跨域基础能力。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`app-locale-infrastructure`](./app-locale-infrastructure/spec.md)、[`app-remote-config`](./app-remote-config/spec.md)、[`app-theme-infrastructure`](./app-theme-infrastructure/spec.md)、[`article-editor-refactor`](./article-editor-refactor/spec.md)、[`cold-start-performance`](./cold-start-performance/spec.md)、[`cross-platform-portability`](./cross-platform-portability/spec.md)、[`dart-semantic-gate`](./dart-semantic-gate/spec.md)、[`dual-theme-page-coverage`](./dual-theme-page-coverage/spec.md)、[`entity-link-templates-metadata`](./entity-link-templates-metadata/spec.md)、[`error-permission-display-semantics`](./error-permission-display-semantics/spec.md)、[`external-inbound-deeplink-routing`](./external-inbound-deeplink-routing/spec.md)、[`ios-native-page-enforcement`](./ios-native-page-enforcement/spec.md)、[`local-cache-architecture`](./local-cache-architecture/spec.md)、[`metadata-driven-client-data-contract`](./metadata-driven-client-data-contract/spec.md)、[`page-horizontal-quality`](./page-horizontal-quality/spec.md)、[`page-layout-semantics`](./page-layout-semantics/spec.md)、[`public-content-web-entry`](./public-content-web-entry/spec.md)、[`s8-p8-semantic-token`](./s8-p8-semantic-token/spec.md)、[`unified-app-page-access`](./unified-app-page-access/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 根级恢复采用平台证据单轨与外层恢复宿主
- 决策：启动致命异常由不依赖业务 Router、登录和延迟插件的原生最小恢复层承接；Android exported launcher 作为 Flutter Engine 与插件装配前的唯一 gate，按平台强证据在原生恢复与 Flutter 主 Activity 之间单向分流。Flutter 运行时恢复由业务 ProviderScope 外的固定宿主持有，运行时主容器最多重建一次。单纯超时、进程未留下成功标记、用户强制结束或系统回收均不得推断为致命崩溃。
- 理由：恢复能力必须在故障业务框架不可用时仍可操作，同时避免无限重启、误判崩溃和第二套 Crash 体系。
- 被否决方案：先创建 Flutter Engine 再用覆盖层伪装原生恢复、恢复 Activity 与 Flutter Activity 各自推导失败状态、6 秒超时直接显示错误页、用户反复重启 Flutter Engine、以 pending 标记推断硬崩溃、新增远程 Crash SDK 或不安全 signal handler。
- 约束与影响：原生 gate、崩溃标记与安全 Shell 清除必须消费同一制品身份，至少绑定平台 Build 与环境运行配置摘要。
- 清单所有权：runtime 是 effective launch manifest 的组合语义 owner，跨 Android、iOS、App 与 Ops 的字段、target/environment 约束和摘要算法只来自 `quwoquan_service/contracts/metadata/_shared/app_launch_manifest.yaml`。
- 协作边界：Product Ops 只拥有版本与官方恢复路由输入，Ops 只装配和验证，平台端只消费生成结果，任何脚本不得维护第二套 schema。
- 异常与发布：异常日志严格十字段并静默后台化。版本与跳转由原生能力接口完成，Android 官网 APK/受信市场、iOS App Store、公众 PWA 与已登记设备受控 Ad Hoc 分流由服务端受信 release contract 决定。不得提供公众 IPA；App Store 与市场入口只在对应渠道真实上架事实存在时展示，禁止假入口。
- 关联要求：`REQ-001`
- 影响 Story：[`cold-start-performance`](./cold-start-performance/spec.md)、[`unrecoverable-runtime-recovery`](./unrecoverable-runtime-recovery/spec.md)、[`public-content-web-entry`](./public-content-web-entry/spec.md)
- 关联验收：`SIT-001`

<a id="dec-003"></a>
### DEC-003 iOS 安装下限先锁 16.0，满五年才允许抬升
- 决策：App 可安装的最低 iOS 先限定为 **16.0**。只有当前下限对应的系统正式发布已满五年，才允许把 `IPHONEOS_DEPLOYMENT_TARGET` / `platform :ios` 再往上抬；抬升是许可不是义务。
- 理由：产品要求覆盖「出厂系统从未升级」的机器。五年窗口从当前下限对应的系统正式发布日起算；未满五年就抬到 17 会挡掉停在 iOS 16 的未升级出厂机。
- 被否决方案：现在就跟 Flutter 默认或 WebRTC 二进制再抬到 17；或为迁就 2021 年 iOS 14 出厂机把下限降到 14（与 Flutter 3.47 的 15.0 引擎底线冲突）。
- 约束与影响：真相源是 `quwoquan_app/ios/Podfile` 与 `Runner.xcodeproj` 的 16.0。本决策管 iOS 操作系统安装下限，不管 Product Ops 的 App Build minimum。Android 安装下限见 [DEC-006](#dec-006)。
- 关联要求：`REQ-003`
- 影响 Story：DEC-003 与 DEC-006 共同影响 [`cross-platform-portability`](./cross-platform-portability/spec.md)
- 关联验收：`GWT-002`

<a id="dec-004"></a>
### DEC-004 启动身份六维正交与运行时内容身份解析
- 决策：把启动链路的身份事实拆为六个正交维度——环境（environment）、平台（platform）、BuildMode、启动来源（launch provenance）、安装渠道（install channel）与内容激活身份（content activation identity）。任一维度只允许作为观测事实记录，业务行为只由环境与服务端状态决定。App 端由单一不可变 production `RuntimePackageResolver/Validator` 解析并校验 runtime package，`app_bootstrap` 与 local_contract 测试直接调用同一实现，不设 `ForTest` 后门；内容身份由 Content API 响应经 typed `ContentActivationIdentity` 值对象送达 Query Slice 与缓存层，App 不拥有内容激活写入。
- 对象边界由以下不可变值对象与派生投影组成。
  - `RuntimeManifest`：runtime 拥有的 immutable value object，随 artifact 嵌入，进程内只读，不是 aggregate。
  - `LaunchProvenance`：`StartupAttempt` runtime session 的 value object，只用于观测，禁止业务消费。
  - `ContentActivationIdentity`（`releaseId + manifestDigest`）：content activation owner 下发到 Query Slice 的 value object；有内容、`no_eligible_content` 与 continuation 必须携带完整 identity，`no_active_release` 必须明确缺席 identity，Remote/解码失败只能是 failure。
  - `BehaviorFingerprint`：UAT `CaseResult` 的 derived projection，不是业务 aggregate，不回写 App runtime。
- App 读取边界：App 读取走 `RuntimePackageReader → RuntimePackageResolver/Validator`，平台实现留在 `lib/runtime/platform/**`。
- 内容只读边界：`ContentDiscoveryFeedQuery` 返回带 identity 的 Slice。
- 启动观测边界：`StartupAttemptRecorder` 追加 provenance，`StartupAttemptQuery` 供 telemetry/UAT 回读。
- 测试证据边界：`StartupCaseEvidenceAppender/Query` 生成并比较 `BehaviorFingerprint`，不得成为业务 runtime 依赖。
- 缓存切换：`ContentQuerySnapshotStore` 以 `manifestDigest` 为 namespace 原子切换；新 digest 切新 namespace，`no_active_release` 清当前可见快照且不回放旧 release，网络失败可在最大年龄内展示“已验证但可能过期”的 LKG 而不冒充当前成功，服务端回滚到旧 release 时可恢复其保留 namespace。
- 无内容 surface：`no_active_release` 是无 CTA 的 `AppEmptyState`。
- 可重试失败 surface：网络、协议或身份错误是带 canonical 重试的 `AppPageErrorState`。
- 致命失败 surface：只有配置或签名致命错误进入 bootstrap/native recovery。Debug/Profile/Release 对同一错误渲染同一 surface，Debug 仅追加脱敏诊断。
- 被否决方案：`launchMode` 参与业务分支（如 `blocksRemoteForDirectUnboundLaunch` 判死 direct debug）、构建期把内容三元烘焙进 App 制品、Provider 直接解析 wire 或持有可变全局内容身份、测试经 `hydrate*ForTest` 后门旁路生产解析。
- 约束与影响：`app_effective_launch_manifest` 不再携带 `contentBindingState` 或内容三元。
- 发布边界：内容发布或回滚不要求重新打包 App。
- 行为不变量：同一 runtime 输入下改变 provenance/channel/BuildMode 时 `BehaviorFingerprint` 必须不变，该性质由 local_contract 穷举验证。
- 关联要求：`REQ-001`
- 影响 Story：[`cold-start-performance`](./cold-start-performance/spec.md)、[`public-content-web-entry`](./public-content-web-entry/spec.md)、[`local-cache-architecture`](./local-cache-architecture/spec.md)、[`app-remote-config`](./app-remote-config/spec.md)
- 关联验收：[`cold-start-performance GWT-005`](./cold-start-performance/spec.md#gwt-005)、[`environment-topology-and-packaging GWT-003`](../runtime-config/environment-topology-and-packaging/spec.md#gwt-003)

<a id="dec-005"></a>
### DEC-005 Web 引擎前只允许一个平台实现的 bootstrap surface
- 决策：Flutter Web 引擎启动前的 loading 与致命恢复态由唯一 `WebBootstrapSurface` 平台实现承载：loading 为 `role=status + aria-live=polite` 无动作状态；字体 404/首次离线为 `startupDependencyUnavailable` 全屏恢复态，唯一动作是重新加载。文案 key 与视觉 token 来自设计系统生成的 canonical CSS variables/l10n 产物。引擎启动后一切网络/内容错误回到 `AppPageErrorState/AppEmptyState`，HTML 壳不再承载业务页面。
- 理由：引擎前无法复用 Flutter canonical 组件，但也不允许 HTML 壳演化成第二套品牌/错误体系。
- 被否决方案：HTML 壳复制品牌字面值、engine 启动后继续用 HTML 覆盖层、为 Web 单独发明重试状态机。
- 约束与影响：`WebBootstrapSurface` 覆盖 compact/regular/expanded、2× 文字与键盘可达；字体文件名 URL-safe 且 FontManifest URL 与产物文件一一对应由发布门禁校验。
- 关联要求：`REQ-001`
- 影响 Story：[`public-content-web-entry`](./public-content-web-entry/spec.md)
- 关联验收：[`public-content-web-entry GWT-006`](./public-content-web-entry/spec.md#gwt-006)

<a id="dec-006"></a>
### DEC-006 Android 安装下限跟随 Flutter SDK，且对应系统必须已满五年
- 决策：Android `minSdk` 跟随当前 Flutter SDK 的 `flutter.minSdkVersion`，不人为抬高。该下限对应的 Android 正式发布必须已满五年；未满五年时不得跟随 SDK 上浮，也不得写死更高 API。
- 理由：Android 机型碎片化，能下探就下探；五年窗口保证「出厂系统从未升级」的机器仍能安装。
- 被否决方案：人为锁到固定 API（例如 29）；或在对应系统未满五年时把 `minSdk` 写得比 Flutter 更高。
- 约束与影响：真相源是 `quwoquan_app/android/app/build.gradle.kts` 的 `minSdk = flutter.minSdkVersion`。五年约束由合同对照 Flutter SDK 解析值与 Android 正式发布日裁定。本决策管操作系统安装下限，不管 `targetSdk` / `compileSdk`，也不管 Product Ops 的 App Build minimum。
- 关联要求：`REQ-004`
- 关联验收：`GWT-003`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 沿用父 L1 质量约束；新增特有 SLO 时在本节声明。

### Web 恢复面证据分工

| 层级 | 唯一观察面 | 禁止替代 |
| --- | --- | --- |
| `local_contract` | `quwoquan_app/test/local_contract/runtime/web_bootstrap_surface__local_contract_test.py` 验证生成资产、状态机、语义和键盘合同 | 不证明真实 HTTP、字体下载或浏览器像素 |
| `api_integration` | Ops public-Web runner 从 exact AppArtifactManifest 启动真实 HTTP 服务，验证 HTML/字体 status、UTF-8、MIME、digest、缓存和 Service Worker，并在 API plane 停止时证明静态恢复面仍可用 | 源码字符串和 package 文件存在性不计通过 |
| `user_acceptance` | `quwoquan_app/test/user_acceptance/journeys/app_startup/` 消费 Chrome/Safari 实际页面、中文像素、恢复动作和 artifact digest | 报告 schema 读取、`UIApplication.open` 或浏览器进程创建不计通过 |

字体 200、首次慢载、字体 404、首次离线、已缓存离线与 Service Worker 更新对 Alpha/Beta/Gamma/Prod 使用同一行为用例，环境只替换 exact artifact/origin。Prod 公网 DNS/TLS、Safari/Android 浏览器与正式发布授权缺失时继续保留 [`public-content-web-entry OPEN-004`](./public-content-web-entry/spec.md#open-004)，不得由本地浏览器或 package-only 结果填绿。
