/// local_contract 测试期的 App↔Cloud 边界纪律。
///
/// 本文件是「测试怎样满足 generated operation client 所在 provider 图」的唯一被
/// 认可入口。它只存在于 `test/**`，`lib/**` 不得引用；它不提供任何第一方业务数据，
/// 因此不构成 `.cursor/rules/08-mock-data-isolation.mdc` 所禁止的 mock/fixture 数据源。
///
/// ## 为什么需要它
///
/// `cloudRuntimeEnvironmentProvider` 走 `CloudRuntimeEnvironment.fromCompileTime()`。
/// 裸 `flutter test` 不注入 `--dart-define=APP_RUNTIME_ENV`，于是任何 transitively
/// watch 到 generated operation client 的 Provider/Widget 测试都在 provider 构造期
/// 抛 `Unsupported APP_RUNTIME_ENV`。
///
/// 反过来，一旦用「中心化 hydrate」或 dart-define 让该 provider 可构造，Widget 测试
/// 就会真的去摸 Gateway、留下 pending timer，把另一批原本绿的测试弄红。两个方向都
/// 是错的：**local_contract 测试根本不该构造真实 operation client**。
///
/// 所以这里不做环境注入，而是把 App↔Cloud 的 HTTP 边界**封死**：构造即失败，并在
/// 失败信息里说明正确做法。测试因此只有一条路可走——显式 override 自己真正依赖的
/// 对象级 typed port（`*CommandWriter` / `*Query`）。
///
/// ## 两种被认可的用法（二选一，没有第三种）
///
/// 1. Provider / Widget 测试 → [sealedCloudBoundaryOverrides]，再叠加本测试真正
///    依赖的对象级 typed port override。
/// 2. generated client / decoder 契约测试 → [generatedClientBoundaryOverrides]，
///    由测试自己显式声明测试期 environment 与 `MockClient` 传输。
///
/// 两者都是 per-suite、在测试自己的调用点声明，不存在全局钩子
/// （`test/flutter_test_config.dart`），也不依赖 `flutter test` 的调用方式：
/// 无论裸跑还是经 `scripts/env/run_flutter_test_guarded.py` 注入 dart-define，
/// 同一个测试的行为完全一致。
///
/// ## per-suite typed-port override 模板（Provider / Widget 测试，直接抄）
///
/// ```dart
/// import 'package:flutter_riverpod/flutter_riverpod.dart';
/// import 'package:flutter_riverpod/misc.dart' show Override;
///
/// import '../../../support/harness/cloud_boundary_test_scope.dart';
///
/// // 1. 每个真正被依赖的对象级 typed port 写一个最小 in-memory double。
/// //    只实现被测路径要用到的方法；不造业务数据集合、不做聚合 Repository。
/// final class _InMemoryFooCommandWriter implements FooCommandWriter {
///   final List<FooCommand> submitted = <FooCommand>[];
///
///   @override
///   Future<FooReceipt> submit(FooCommand command) async {
///     submitted.add(command);
///     return const FooReceipt(accepted: true);
///   }
/// }
///
/// // 2. 一个 suite 一个 _boundaryOverrides()：先封边界，再声明本 suite 的依赖。
/// //    可选参数用于个别用例需要观察/替换某个 double 的场合。
/// List<Override> _boundaryOverrides({
///   FooCommandWriter? fooCommandWriter,
///   List<Override> extra = const <Override>[],
/// }) {
///   return <Override>[
///     ...sealedCloudBoundaryOverrides(),
///     fooCommandWriterProvider.overrideWithValue(
///       fooCommandWriter ?? _InMemoryFooCommandWriter(),
///     ),
///     ...extra,
///   ];
/// }
///
/// // 3. 所有 ProviderScope / ProviderContainer 都走同一个入口。
/// await tester.pumpWidget(
///   ProviderScope(overrides: _boundaryOverrides(), child: const FooPage()),
/// );
/// ```
///
/// 定位「还缺哪个 typed port」的方法：跑失败测试，[SealedCloudBoundaryError] 会指出
/// 被触碰的边界 provider；沿栈上方的 `*Provider.<anonymous closure>` 逐层往上读，第一个
/// 属于本 domain 的 provider 就是要 override 的那一层。**不要**在栈底那一层
/// （generated client / http client）打补丁。
library;

import 'package:flutter_riverpod/misc.dart' show Override, ProviderException;
import 'package:flutter_test/flutter_test.dart' show Matcher, predicate;
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/core/di/cloud_http_client_provider.dart';
import 'package:quwoquan_app/core/di/generated_operation_client_dependencies.dart';

/// 被封死的 App↔Cloud 边界被测试触碰时抛出的结构化失败。
///
/// 它刻意不是 `CloudException` / `RuntimeFailure`：这不是一个业务失败，而是一条
/// 测试装配纪律的违约，必须让测试作者去补 typed port override，而不是被当成可以
/// 断言或降级的运行时错误。
final class SealedCloudBoundaryError extends Error {
  SealedCloudBoundaryError(this.providerLabel);

  /// 被触碰的边界 provider 名，用于直接指出缺哪一层 override。
  final String providerLabel;

  @override
  String toString() =>
      'SealedCloudBoundaryError: local_contract 测试触碰了被封死的 App↔Cloud 边界 '
      '`$providerLabel`。\n'
      'local_contract 不得构造真实 generated operation client 或真实 HTTP 传输。\n'
      '正确做法：override 本测试真正依赖的对象级 typed port（*CommandWriter / *Query），'
      '让 provider 图根本走不到 generated client。\n'
      '若本测试的被测对象就是 generated client / decoder 本身，改用 '
      'generatedClientBoundaryOverrides(transport: MockClient(...))。\n'
      '写法见 quwoquan_app/test/support/harness/cloud_boundary_test_scope.dart '
      '与 quwoquan_app/AGENTS.md「local_contract 测试的 App↔Cloud 边界」。';
}

/// 封死 App↔Cloud 边界：generated operation client 与底层 HTTP 传输构造即失败。
///
/// Provider / Widget 测试的默认底座。放在 `overrides` 最前面，本测试自己的对象级
/// typed port override 追加在后面即可——Riverpod 取最后一个同 provider override，
/// 所以顺序天然表达「先封边界，再声明本测试真正需要的依赖」。
///
/// 它不引入任何 mock 数据源、不引入聚合 Repository、不提供 mock/remote 运行时开关：
/// 被封死的 provider 只会抛 [SealedCloudBoundaryError]，永远不返回替身实现。
List<Override> sealedCloudBoundaryOverrides() => <Override>[
  cloudRuntimeEnvironmentProvider.overrideWith(
    (ref) => throw SealedCloudBoundaryError('cloudRuntimeEnvironmentProvider'),
  ),
  generatedCloudOperationClientProvider.overrideWith(
    (ref) =>
        throw SealedCloudBoundaryError('generatedCloudOperationClientProvider'),
  ),
  unauthenticatedGeneratedCloudOperationClientProvider.overrideWith(
    (ref) => throw SealedCloudBoundaryError(
      'unauthenticatedGeneratedCloudOperationClientProvider',
    ),
  ),
  cloudHttpClientProvider.overrideWith(
    (ref) => throw SealedCloudBoundaryError('cloudHttpClientProvider'),
  ),
  unauthenticatedCloudHttpClientProvider.overrideWith(
    (ref) => throw SealedCloudBoundaryError(
      'unauthenticatedCloudHttpClientProvider',
    ),
  ),
];

/// 断言「读某个 provider 会撞上被封死的 App↔Cloud 边界」。
///
/// Riverpod 3 会把 provider 构造期异常包进 [ProviderException]，且传递依赖链上每
/// 一层还会再包一次，直接 `isA<SealedCloudBoundaryError>()` 断不到。统一用本
/// matcher，避免每个套件自己拆包装、拆出不同形状。
///
/// [providerLabel] 非空时还会校验失败指向的正是那一层边界 provider。
Matcher isSealedCloudBoundaryFailure({String? providerLabel}) {
  return predicate<Object?>(
    (error) {
      var cause = error;
      while (cause is ProviderException) {
        cause = cause.exception;
      }
      if (cause is! SealedCloudBoundaryError) {
        return false;
      }
      return providerLabel == null || cause.providerLabel == providerLabel;
    },
    'is a sealed App↔Cloud boundary failure${providerLabel == null ? '' : ' on `$providerLabel`'}',
  );
}

/// 测试期确定性 [CloudRuntimeEnvironment]，不读任何 compile-time define。
///
/// 这是 local_contract 唯一被认可的「不依赖真实 dart-defines 就拿到确定 environment」
/// 的来源：既服务 [generatedClientBoundaryOverrides] 的 provider 装配，也服务直接
/// `new` 出 Remote adapter 的对象级契约测试，避免每个套件各自手写 gateway URI 而
/// 出现十几种测试期 base URL。
///
/// 它不是第二真相源：生产的 environment 仍然只能来自
/// `CloudRuntimeEnvironment.fromCompileTime()`；这里只是测试为自己声明输入值，
/// 与 `MockClient` 声明自己的响应同性质。域名固定用不可解析的 `.test` 保留后缀，
/// 万一有测试真的发起请求也只会立刻失败，不会打到任何真实环境。
CloudRuntimeEnvironment testCloudRuntimeEnvironment({
  CloudEnvironment environment = CloudEnvironment.alpha,
  Uri? gatewayBaseUri,
}) {
  return CloudRuntimeEnvironment(
    environment: environment,
    gatewayBaseUri:
        gatewayBaseUri ??
        Uri.parse('https://gateway.${environment.name}.quwoquan.test'),
  );
}

/// generated client / decoder 契约测试专用的测试期 runtime-env provisioning。
///
/// 被测对象是 generated client 自身（path、header、鉴权、decoder、错误映射）时，
/// 必须真的构造 client，因此需要一个 [CloudRuntimeEnvironment]。约束是 environment
/// 只能来自 [testCloudRuntimeEnvironment]，且 [transport] 是必填参数——测试必须交出
/// 自己的 `MockClient`，没有默认真实传输可以回退。
///
/// 只有「被测对象就是出站边界本身」的套件可以用它。Provider / Widget 测试一律用
/// [sealedCloudBoundaryOverrides]：一旦让 generated client 在 Widget 测试里可构造，
/// `AppGeneratedCloudOperationExecutor.send` 就会真的发出请求并留下 pending timer。
List<Override> generatedClientBoundaryOverrides({
  required http.Client transport,
  CloudEnvironment environment = CloudEnvironment.alpha,
  Uri? gatewayBaseUri,
}) {
  final httpClient = CloudHttpClient(client: transport);
  return <Override>[
    cloudRuntimeEnvironmentProvider.overrideWithValue(
      testCloudRuntimeEnvironment(
        environment: environment,
        gatewayBaseUri: gatewayBaseUri,
      ),
    ),
    cloudHttpClientProvider.overrideWithValue(httpClient),
    unauthenticatedCloudHttpClientProvider.overrideWithValue(httpClient),
  ];
}
