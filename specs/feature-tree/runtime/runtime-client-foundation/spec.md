# L2 Business Capability：运行时客户端基础 (`runtime-client-foundation`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

为 Flutter App 提供网络、缓存、本地化、日志、媒体与语义门禁等跨域基础能力

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“runtime-client-foundation”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-001 / SCN-004`](../../spec.md#scn-004)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：为 Flutter App 提供网络、缓存、本地化、日志、媒体与语义门禁等跨域基础能力，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-002 / SCN-005`](../../spec.md#scn-005)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：为 Flutter App 提供网络、缓存、本地化、日志、媒体与语义门禁等跨域基础能力，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-010 / SCN-024`](../../spec.md#scn-024)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：为 Flutter App 提供网络、缓存、本地化、日志、媒体与语义门禁等跨域基础能力，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-010 / SCN-025`](../../spec.md#scn-025)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：为 Flutter App 提供网络、缓存、本地化、日志、媒体与语义门禁等跨域基础能力，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`app-locale-infrastructure`](./app-locale-infrastructure/spec.md)：通过 ARB 与 flutter gen-l10n 生成本地化资源，并在 locale 切换后保持页面文案一致。
- [`app-remote-config`](./app-remote-config/spec.md)：冷启动首帧可在无远程配置的情况下正常进入欢迎页和首页。
- [`app-theme-infrastructure`](./app-theme-infrastructure/spec.md)：必须坚持 `Cupertino-first`：Material 仅用于兼容和平台必要能力，不得成为主要视觉语法来源。
- [`article-editor-refactor`](./article-editor-refactor/spec.md)：不可用时 **置灰**；可用时符合对比度与触控热区（≥44pt）。
- [`cold-start-performance`](./cold-start-performance/spec.md)：正常启动优先进入安全 Shell，只有已确认的启动致命异常进入无重试恢复链路。
- [`unrecoverable-runtime-recovery`](./unrecoverable-runtime-recovery/spec.md)：运行时根级不可恢复异常只允许一次主容器重建，失败后转入版本或网页版恢复且不得循环。
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

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 runtime client foundation 能力 SIT

- 本能力必须组合直属 Story 与公开契约，交付“为 Flutter App 提供网络、缓存、本地化、日志、媒体与语义门禁等跨域基础能力”所定义的业务结果；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 所有客户端横切能力必须经此 L2 统一定义，禁止在业务域 L2（如 `discovery-content`）下新建客户端基础设施节点

- 所有客户端横切能力必须经此 L2 统一定义，禁止在业务域 L2（如 `discovery-content`）下新建客户端基础设施节点
- 对象级缓存、查询快照、资源缓存和用户缓存清理统一归属 `local-cache-architecture`；业务域只登记对象策略与验收，不得自建第二套缓存合同或页面级 TTL。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 runtime client foundation 能力 SIT

- GIVEN 执行“runtime client foundation 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“runtime client foundation 能力”对应动作。
- THEN 直属 Story 共同交付“为 Flutter App 提供网络、缓存、本地化、日志、媒体与语义门禁等跨域基础能力”，失败终态可区分且不产生伪成功事实。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 runtime client foundation 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：为 Flutter App 提供网络、缓存、本地化、日志、媒体与语义门禁等跨域基础能力。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
