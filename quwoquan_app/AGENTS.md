# quwoquan_app Codex Guide

在 `quwoquan_app/` 工作时，除仓库根 `AGENTS.md` 外，默认补读仓库根 `.cursor/rules/` 下与 App 文件类型直接相关的规则：

1. `.cursor/rules/02-dart-coding.mdc`
2. `.cursor/rules/08-mock-data-isolation.mdc`

按触达范围追加：

- 触及 `lib/service/**/presentation/**` 页面或 `lib/runtime/shell/*.dart`：补读 `.cursor/rules/09-page-horizontal-quality.mdc`
- 触及登录入口、登录成功/关闭回退路径：补读 `.cursor/rules/15-auth-entry-no-loop.mdc`
- 触及平台差异、Web/鸿蒙能力：补读 `.cursor/rules/14-cross-platform-portability.mdc`
- 触及 `lib/design_system/pageflip/**` 或 `lib/service/content_service/content/post/presentation/article_reader/pageflip/**`：补读 `.cursor/rules/11-pageflip-geometry-guardrails.mdc`；若为 BACK 方向，再补读 `.cursor/rules/12-pageflip-backward-mainline.mdc`

## App 端硬约束

- UI 不得硬编码颜色、间距、字号、交互热区、中文文案；统一走 `AppColors`、`AppSpacing`、`AppTypography`、`UITextConstants`/`l10n`。
- 对象 `presentation/**`、`application/**` 与横切 `lib/runtime/**` 不直连 mock 目录，也不直接实例化 Mock/Remote Repository。
- Repository、route、surface、operation、错误码、decoder context 以 metadata/codegen 为真相源。
- 结构化错误统一走 `RuntimeFailure`、`RuntimeRecoveryPolicy`、runtime mapper；不要回退到原始字符串异常。
- 用户可见错误提示必须来自 codegen 错误枚举、`toDisplayMessage(context.l10n)`、`UITextConstants` 或 l10n；禁止在 UI/Provider 中 switch 硬编码错误码字符串或中文提示。
- `CloudException` 必须由 runtime mapper 生成并暴露 `runtimeFailure`；UI 状态只消费 `RuntimeFailure`、`runtimeErrorDisplayMessage` 和 `RuntimeRecoveryPolicy`，不得展示 raw exception/debugMessage。
- 新页面或页面行为变化，要同步核对页面横向质量矩阵、metadata-driven UI 清单与相关测试。
- 搬迁或改名页面文件时**不要手改** `quwoquan_service/contracts/metadata/_shared/page_object_contract.yaml`：
 该契约的 `source_path`、`route_registration_evidence`、`mount_evidence` 由
 `python3 quwoquan_service/scripts/contracts/sync_page_object_source_paths.py` 统一同步，
 它是该文件迁移期的唯一写入口，避免多条并发流整文件覆写互相清掉改动。搬完页面跑一次即可；
 `--check` 只检测不落盘。工具无法唯一定位新落点时会 `MANUAL` 报错退出，此时补人工裁决，
 不要绕过它直接改 YAML。
- 页面的业务归属仍以 `page_object_contract.yaml` 的 `object_ids` 为真相源：多对象页面被物理搬进
 某个对象的 `presentation/` **不等于**已经拆页，`object_path_map.py` 会按 `app_target_shape`
 判成单对象、`multi_object_page` 信号随之消失。不得为了让派生器闭嘴而删减 `object_ids`；
 同步工具会把这类页面报成 `REVIEW [multi_object_single_presentation]` 等待拆页裁决。
- App 端在 `alpha/beta/gamma/prod` 全部使用同一个 production Remote composition；环境只提供 runtime package/endpoints，App 可见第一方业务数据只来自环境已激活的 canonical immutable release。任何 runner、UAT support 或启动脚本均不得注入 Mock/fixture，也不得保留 Mock/Remote 切换入口。
- `local_contract` 对象级 double 直接消费语言内 typed builder/generator 或最小 contract example；禁止在 Dart builder 中重建 `seedSets`、`repositoryExpectations`、`requiresSeedReset` 等场景文档结构，也禁止让独立 eval corpus 选择 App Repository 或环境数据重置策略。
- 新页面、入口、详情、搜索、创作、消息或推荐相关改动，必须补曝光、停留、异常、关键点击、`referralSource`/`feedRequestId`/trace 传递；内容消费页还要补消费深度和互动反馈。
- 用户反馈、点赞/评论/收藏/分享/关注、搜索点击、内容停留等行为必须能回流到推荐和运营分析，不得只停留在 UI 状态。
- 当前阶段未上线：发现不合理 UI/Repository/Provider/路由实现时直接替换为正确模式，不为旧错误保留兼容分支、fallback 或 allowlist。
- production 装配按 domain 分片：`lib/runtime/di/<domain>_dependencies.dart` 是该 domain
 唯一可以命名 `Remote*` 实现的地方，Provider 只声明 typed port。缺文件时按同一范式新建，
 不要重建跨 domain 的单一 composition 或 adapter 枚举。
- `lib/runtime/di/app_providers.dart` 只是 domain 级 barrel，不得声明 Provider。新增或
 搬迁 Provider 落到所属 domain 的 provider 库，再由 barrel `export`。

## l10n ARB key 归属约定

`lib/l10n/app_zh.arb` 与 `lib/l10n/app_en.arb` 是无法按 domain 分片的共享写点，只能靠
key 命名表达归属，避免 15 条 domain 并行流互相覆盖。

- 新增或重命名的 key 一律使用 `<domain>_` 前缀，前缀后仍为 lowerCamelCase，例如
 `content_postDeleteConfirmTitle`、`user_loginPhoneCodeResendTemplate`。
- `<domain>` 只能取 `quwoquan_ops/gate/object_path_map.py` 派生出的 15 个 domain：
 `assistant`、`chat`、`circle`、`content`、`entity`、`gateway`、`integration`、
 `notification`、`ops`、`realtime`、`recommendation`、`rtc`、`search`、`tag`、
 `user`。不属于任何 domain 的横切文案使用 `runtime_` 或 `design_system_` 前缀，与
 `object_path_map.py` 的两个横切根同名。
- 两个 arb 文件必须同 key 同序改动；`@key` 元数据紧跟其 key。
- 存量 579 个无前缀 key 不做批量重命名：每条 domain 流搬迁自己对象时，顺带把该对象用到的
 key 改成带前缀形式并同步全部引用；禁止为旧 key 保留别名或双写。
- 冲突判定只看前缀：两条流同时改 arb 时，只要各自 key 前缀不同就不算语义冲突，按文本合并即可。

## 错误体验与观测

- 每个用户可见错误都必须有提示、恢复动作和观测语义：提示用户发生了什么，恢复动作告诉用户下一步能做什么，观测记录 code/operation/surface/recovery/disruption/requestId/traceId。
- 权限、登录、网络、限流、服务不可用、数据校验、第三方依赖失败要有不同 UI 语义和恢复按钮，不得统一显示“出错了”。
- 登录返回账号摘要遵守“文本稳定、头像渐进增强”：头像仅在可信图片成功解码后显示；空值、加载中或失败时必须零占位、零间距、零头像语义，不得生成轮廓、首字、品牌图标或文字 fallback，昵称与脱敏账号提示不依赖头像。
- 登录入口必须区分返回会话与运营商能力：返回账号只有“具体账号线索 + 可立即执行恢复动作”同时成立才展示，主动作称“继续登录”；运营商入口只有 vendor/token/有效期完整正向证明后才展示，否则静默进入手机号验证码，不允许通过点击后的失败探测能力。
- 短信验证码发送成功后折叠大号手机号输入框，仅保留脱敏发送摘要和“更换手机号”；错误卡不得复制页面主按钮已经承担的恢复动作。
- 页面级错误要同时覆盖空态/错误态/权限态/加载态；可恢复错误提供重试或目标动作，不可恢复错误提供安全返回或联系支持路径。
- 错误埋点不得泄露 PII/SECRET/debug detail；用户看到的是本地化提示，日志/telemetry 看到的是结构化 code 与脱敏 context。

## 典型触发与 E2E

- 用户说“页面、登录、搜索、创作、消息、错误提示、恢复按钮、推荐曝光、行为反馈”时，默认加载本文件。
- 若同时涉及服务错误码、Remote API、数据导入、推荐反馈或环境发布，必须按根 `AGENTS.md` 的 Pre-work Reflection 启用跨域 E2E 模式。
- App 不得单独完成端云链路：`api_integration` Remote 行为必须能回到 `local_contract` generated-client/object-level typed double/Widget/Provider 断言。

## Review 与测试要求

- 每次改动都要按产品、架构、代码评审、质量、测试、用户、运维、运营八角色自检。
- `local_contract` 覆盖 metadata/codegen/静态规则、provider/widget/Mock 行为；`api_integration` 覆盖 Remote/API/真实存储或集成环境；`user_acceptance` 覆盖用户旅程、权限、弱网、性能或发布前 UAT。
- Remote 行为的 `api_integration` 断言必须在 `local_contract` generated-client/object-level typed double/Widget/Provider 测试中有对应断言；测试 double 不能进入任何环境 App，也不能替代集成测试。
- 错误码链路的 `local_contract` 必须覆盖 mapper、Provider 状态、UI 文案、恢复按钮和 typed 错误响应；`api_integration` 必须覆盖 RemoteRepository 对服务错误响应的映射。
- 新增页面必须同步检查页面矩阵、P1-P8、metadata-driven UI 清单、Mock 隔离、设计系统语义 token 和登录无死循环。

## local_contract 测试的 App↔Cloud 边界

`cloudRuntimeEnvironmentProvider` 走 `CloudRuntimeEnvironment.fromCompileTime()`，因此
「测试怎样满足 generated operation client 所在的 provider 图」是一个跨全部 domain 的共享
写点。唯一被认可的机制在 `test/support/runtime/cloud_boundary_test_scope.dart`。

- Provider / Widget 的 `local_contract` 测试**不得**让 provider 图解析到 generated
  operation client：`ProviderScope` / `ProviderContainer` 的 `overrides` 必须以
  `sealedCloudBoundaryOverrides()` 开头，再叠加本测试真正依赖的对象级 typed port
  （`*CommandWriter` / `*Query`）override。样板见
  `test/local_contract/runtime/shell/interest_match/interest_match_page__local_contract_test.dart`。
- 被测对象就是 generated client / decoder / 错误映射本身时，改用
  `generatedClientBoundaryOverrides(transport: MockClient(...))`：environment 由测试显式
  声明为字面值，传输必须是测试交出的 `MockClient`。样板见
  `test/local_contract/runtime/cloud_boundary_test_scope__local_contract_test.dart`。
- 撞上 `SealedCloudBoundaryError` 时唯一正确动作是补对象级 typed port override。禁止改成
  给测试注入 environment、放宽 seal、返回 Noop/Mock client 或 skip 测试。失败信息里已经写明
  缺哪一层边界 provider，按它往上找 `ref.watch` 链即可定位该 override 的 typed port。
- 禁止新增 `test/flutter_test_config.dart` 之类全局钩子，禁止在测试里调用
  `CloudRuntimeConfig.hydrateFromNativeRuntimePackage`，也禁止靠 `--dart-define` 让该
  provider 变得可构造：那会让 Widget 测试摸到真实 Gateway 并留下 pending timer，等于用一批
  红换另一批红，还掩盖真实的 DI 缺口。
- 测试是否通过不得依赖 `flutter test` 的调用方式：同一套件在裸 `flutter test` 与
  `scripts/env/run_flutter_test_guarded.py`（会注入 `APP_RUNTIME_ENV` 等 dart-define）下必须
  同样绿。搬迁 domain 测试树时顺带完成本节改造，不要留给后续统一整改。
- 断言被封边界时统一用 `isSealedCloudBoundaryFailure()`；Riverpod 3 会把 provider 构造异常
  逐层包进 `ProviderException`，各套件不得自己拆包装。
- 需要确定性 environment 值（provider override 之外，例如直接 `new` 出 Remote adapter 的
  对象级契约测试）时用 `testCloudRuntimeEnvironment()`，不要各套件自己手写 gateway URI。

### per-suite typed-port override 模板

搬 domain 测试树时按此形状改，一个 suite 一个 `_boundaryOverrides()`：

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;

// 对象测试位于 test/local_contract/service/<service>/<context>/<object>/，
// 相对 test/ 根共五级，因此指向 test/support/runtime/ 的相对深度如下。
import '../../../../../support/runtime/cloud_boundary_test_scope.dart';

final class _InMemoryFooCommandWriter implements FooCommandWriter {
  final List<FooCommand> submitted = <FooCommand>[];

  @override
  Future<FooReceipt> submit(FooCommand command) async {
    submitted.add(command);
    return const FooReceipt(accepted: true);
  }
}

List<Override> _boundaryOverrides({
  FooCommandWriter? fooCommandWriter,
  List<Override> extra = const <Override>[],
}) {
  return <Override>[
    ...sealedCloudBoundaryOverrides(),
    fooCommandWriterProvider.overrideWithValue(
      fooCommandWriter ?? _InMemoryFooCommandWriter(),
    ),
    ...extra,
  ];
}
```

要点：in-memory double 只实现被测路径用到的方法，不造业务数据集合、不做聚合 Repository；
suite 内所有 `ProviderScope` / `ProviderContainer` 都走同一个 `_boundaryOverrides()`；个别
用例需要观察某个 double 时用具名可选参数传入，不要另起第二套装配。定位「还缺哪个 typed
port」：跑失败测试，沿 `SealedCloudBoundaryError` 栈上方的 `*Provider.<anonymous closure>`
逐层往上读，第一个属于本 domain 的 provider 就是要 override 的那一层——不要在栈底的
generated client / http client 那一层打补丁。

## 推荐验证

- 改 Dart 文件后读取最近改动文件的 lint。
- 页面/壳层改动：执行 `make verify-app-page-horizontal-quality`。
- 搬迁/改名页面文件后：先执行 `python3 quwoquan_service/scripts/contracts/sync_page_object_source_paths.py`
 收敛契约路径，再跑页面横向质量门禁。
- 改动 runtime error 契约相关代码：执行 `dart quwoquan_ops/tools/runtime_error_codegen/bin/check_runtime_error_cutover.dart`。
- 根据触达范围跑对应 `flutter test`，必要时再跑 `bash quwoquan_ops/gate/gate_repo.sh --scope app`。
- 涉及环境、包纯度或部署验证时，使用 `python3 quwoquan_ops/cli/stackctl.py package/verify/health/inspect`，不要手写第二套 URL、端口或拓扑。
