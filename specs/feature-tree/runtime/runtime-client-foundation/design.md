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
- 异常与发布：异常日志严格十字段并静默后台化。版本与跳转由原生能力接口完成，Android 官网 APK、公众 iOS PWA 与已登记设备受控 Ad Hoc 分流由服务端受信 release contract 决定。不得提供公众 IPA 或 App Store 假入口。
- 关联要求：`REQ-001`
- 影响 Story：[`cold-start-performance`](./cold-start-performance/spec.md)、[`unrecoverable-runtime-recovery`](./unrecoverable-runtime-recovery/spec.md)、[`public-content-web-entry`](./public-content-web-entry/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 沿用父 L1 质量约束；新增特有 SLO 时在本节声明。
