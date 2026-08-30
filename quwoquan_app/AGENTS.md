# quwoquan_app Agent Guide

本文件只声明 `quwoquan_app/**` 每次变更都成立的 App 不变量，并与根 `AGENTS.md` 同时生效。功能行为、页面几何、手势、BACK 主路径、文案和验收从 `make feature-context TARGET=<path>` 返回的 Feature spec/design/contracts 按需加载，不放在子树全局规则里。

## 归属与真相源

- App 业务实现位于 `lib/service/<service>/<context>/<object>/{domain,application,adapters,presentation}`；对象分层、页面 participant 与依赖方向由 [`system-architecture-and-engineering-guide` DEC-018/019](../specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md#dec-018) 拥有。
- `lib/runtime/**`、`lib/design_system/**`、`lib/l10n/**` 是横切边界，不得反向拥有业务对象事实。无法唯一归属的代码先修 Feature owner，不靠目录猜测。
- Repository、route、surface、operation、字段、枚举、错误码与 decoder context 以服务 contracts/metadata 及 codegen 为真相源；禁止手写第二 DTO/枚举、手改 `.g.dart` 或放宽未知值。
- 第一方 Dart 跨目录引用使用 `package:quwoquan_app/...`，不用 `../` 相对穿越；路径与标识符按领域语义命名，不绑定产品品牌。generated contract 的业务消费者只读类型化属性，裸 Map key 只允许留在 codegen decoder/factory 边界。
- 结果状态、模型属性和显式配置判定分别消费 [DEC-025](../specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md#dec-025)、[DEC-030](../specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md#dec-030) 和 [DEC-029](../specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md#dec-029)，不从 Review 角色 reference 间接追链。

## 组合与测试隔离

- `alpha/beta/gamma/prod` 全部使用同一 production Remote composition。环境只提供 runtime package、endpoint、容量和发布阶段；App 可见第一方业务数据只来自该环境已激活的 canonical immutable release。
- production、runner、UAT support 与启动脚本不得注入 Mock/fixture、直接数据库 seed 或 Mock/Remote 切换入口。`presentation/**`、`application/**` 和 `runtime/**` 不导入 test/mock 目录。
- production 依赖按 domain 分片：`lib/runtime/di/<domain>_dependencies.dart` 是该 domain 唯一可命名 `Remote*` 实现的地方；Provider 只声明 typed port。`lib/runtime/di/app_providers.dart` 只是 export barrel，不声明 Provider。
- Riverpod 状态纪律：State 类不可变（`const` 构造 + `copyWith` + `==`/`hashCode`）；StateNotifier 异步操作必须有错误处理并防重复加载；`ref.watch` 只在 build 监听，`ref.read` 执行动作，`ref.listen` 处理副作用。
- `local_contract` 的对象级 double 只实现被测 typed port，不复制场景文档、不选择 Repository、不重置环境数据。测试 double 不得进入任何环境 App。
- Provider/Widget `local_contract` 默认从 `test/support/runtime/cloud_boundary_test_scope.dart` 的 `sealedCloudBoundaryOverrides()` 开始，再补本对象 typed port。只有直接测 generated client/decoder/mapper 时使用 `generatedClientBoundaryOverrides(transport: MockClient(...))`。禁止放宽 seal、注入真实 Gateway、新建全局 `flutter_test_config.dart` 或依赖 `--dart-define` 使测试变绿。

## UI、l10n 与可访问性

- UI 不硬编码颜色、间距、字号、交互热区或用户文案；使用 `AppColors`、`AppSpacing`、`AppTypography`、`UITextConstants`/l10n 与所属 Feature 设计 token。
- 新页面或页面行为变化必须有加载、空、错误/权限和成功终态，并满足所属 Story 的手势、焦点、Reduce Motion、热区与弱网验收；这些功能约束不在本文件复制。
- ARB 新 key 使用 `<domain>_lowerCamelCase`；横切文案使用 `runtime_` 或 `design_system_`。`app_zh.arb` 与 `app_en.arb` 同 key、同序更新，`@key` 紧跟该 key；不为存量 key 保留别名或双写。文案 key 按领域归属，不得跨域借用语义不同的既有 key。
- 搬迁/改名页面后用 `python3 quwoquan_service/scripts/contracts/sync_page_object_source_paths.py`
  更新 `_shared/page_object_contract.yaml`；不手改其派生路径，不为了让门禁通过而删减多对象 `object_ids`。

## 错误、恢复与观测

- 结构化错误经 `RuntimeFailure`、`RuntimeRecoveryPolicy` 与 runtime mapper 传递。`CloudException` 必须暴露 mapped `runtimeFailure`；UI 不展示 raw exception/debugMessage，不 switch 硬编码错误码或中文。
- 每个用户可见错误同时具有本地化提示、恢复动作和脱敏观测语义；telemetry 记录 code/operation/surface/recovery/disruption/requestId/traceId，不记录 PII/secret/debug detail。
- 新页面、入口、详情、搜索、创作、消息或推荐行为声明曝光、停留、异常、关键点击和 trace/referral 传递；用户反馈与消费行为要能回流推荐/运营，不只改 UI 状态。

## 验证入口

- 先执行 manifest 与 Review plan 列出的命名 evidence；同一命令不由 Reviewer 重复执行。
- Dart 变更至少跑受影响的 analyzer/test；页面壳层与横向质量执行 `make verify-app-page-horizontal-quality`；具体功能 gate 只从其 Feature 设计/验收加载。
- `local_contract`、`api_integration`、`user_acceptance` 分层报告。静态门、Widget test 或首帧不替代 Remote/API、真实环境或设备 UAT。
- 环境、runtime package 或发布验证使用 `environment-ops` 及 `python3 quwoquan_ops/cli/stackctl.py`，不手写第二 URL、端口或拓扑。
