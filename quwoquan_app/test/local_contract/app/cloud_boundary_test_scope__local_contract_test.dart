/// local_contract 测试期 App↔Cloud 边界机制自身的契约。
///
/// 机制一旦被绕过或退化，这里先红：它保证「封边界」而不是「注环境」始终是
/// local_contract 的默认底座。
///
/// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#req-004
library;

import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/core/di/cloud_http_client_provider.dart';
import 'package:quwoquan_app/core/di/generated_operation_client_dependencies.dart';

import '../../support/harness/cloud_boundary_test_scope.dart';

/// 只在本测试内存在的对象级 typed port 形状，用于证明 override 后 provider 图
/// 不再向下解析到 generated client。
abstract interface class _SampleObjectQuery {
  String readLabel();
}

final class _InMemorySampleObjectQuery implements _SampleObjectQuery {
  const _InMemorySampleObjectQuery(this._label);

  final String _label;

  @override
  String readLabel() => _label;
}

/// 模拟真实 Provider 的形状：typed port 默认经 generated client 装配。
final _sampleObjectQueryProvider = Provider<_SampleObjectQuery>((ref) {
  ref.watch(generatedCloudOperationClientProvider);
  return const _InMemorySampleObjectQuery('remote');
});

void main() {
  group('sealedCloudBoundaryOverrides', () {
    test('generated operation client 构造即失败，且失败信息指出正确做法', () {
      final container = ProviderContainer(
        overrides: sealedCloudBoundaryOverrides(),
      );
      addTearDown(container.dispose);

      Object? captured;
      try {
        container.read(generatedCloudOperationClientProvider);
      } catch (error) {
        captured = error;
      }

      expect(
        captured,
        isSealedCloudBoundaryFailure(
          providerLabel: 'generatedCloudOperationClientProvider',
        ),
      );
      final message = captured.toString();
      expect(message, contains('*CommandWriter / *Query'));
      expect(message, contains('cloud_boundary_test_scope.dart'));
    });

    test('底层 HTTP 传输同样被封死，测试无法从旁路摸到真实网络', () {
      final container = ProviderContainer(
        overrides: sealedCloudBoundaryOverrides(),
      );
      addTearDown(container.dispose);

      expect(
        () => container.read(cloudHttpClientProvider),
        throwsA(
          isSealedCloudBoundaryFailure(
            providerLabel: 'cloudHttpClientProvider',
          ),
        ),
      );
      expect(
        () => container.read(unauthenticatedCloudHttpClientProvider),
        throwsA(
          isSealedCloudBoundaryFailure(
            providerLabel: 'unauthenticatedCloudHttpClientProvider',
          ),
        ),
      );
      expect(
        () => container.read(
          unauthenticatedGeneratedCloudOperationClientProvider,
        ),
        throwsA(
          isSealedCloudBoundaryFailure(
            providerLabel:
                'unauthenticatedGeneratedCloudOperationClientProvider',
          ),
        ),
      );
    });

    test('封边界不提供任何替身实现：只抛纪律违约，不返回可用 client', () {
      final container = ProviderContainer(
        overrides: sealedCloudBoundaryOverrides(),
      );
      addTearDown(container.dispose);

      // 若哪天有人把 seal 改成返回 Noop/Mock client，本断言会立刻红。
      expect(
        () => container.read(cloudRuntimeEnvironmentProvider),
        throwsA(
          isSealedCloudBoundaryFailure(
            providerLabel: 'cloudRuntimeEnvironmentProvider',
          ),
        ),
      );
    });

    test('叠加对象级 typed port override 后，provider 图不再解析到 generated client', () {
      final container = ProviderContainer(
        overrides: <Override>[
          ...sealedCloudBoundaryOverrides(),
          _sampleObjectQueryProvider.overrideWithValue(
            const _InMemorySampleObjectQuery('in-memory'),
          ),
        ],
      );
      addTearDown(container.dispose);

      expect(
        container.read(_sampleObjectQueryProvider).readLabel(),
        'in-memory',
      );
    });

    test('缺 typed port override 时失败落在边界上，而不是 Unsupported APP_RUNTIME_ENV', () {
      final container = ProviderContainer(
        overrides: sealedCloudBoundaryOverrides(),
      );
      addTearDown(container.dispose);

      Object? captured;
      try {
        container.read(_sampleObjectQueryProvider);
      } catch (error) {
        captured = error;
      }

      expect(captured, isSealedCloudBoundaryFailure());
      expect(
        captured.toString(),
        isNot(contains('Unsupported APP_RUNTIME_ENV')),
      );
    });
  });

  group('testCloudRuntimeEnvironment', () {
    test('不依赖 dart-defines 即得到确定 environment，且默认域名不可解析', () {
      final environment = testCloudRuntimeEnvironment();

      expect(environment.environment, CloudEnvironment.alpha);
      expect(environment.gatewayBaseUri.host, endsWith('.test'));
      expect(environment.gatewayBaseUri.scheme, 'https');
    });

    test('同一入参恒等：测试期 environment 不随调用次数或进程状态漂移', () {
      final first = testCloudRuntimeEnvironment(
        environment: CloudEnvironment.gamma,
      );
      final second = testCloudRuntimeEnvironment(
        environment: CloudEnvironment.gamma,
      );

      expect(first.environment, second.environment);
      expect(first.gatewayBaseUri, second.gatewayBaseUri);
    });
  });

  group('generatedClientBoundaryOverrides', () {
    test('environment 由测试显式声明，不读 compile-time define', () {
      final container = ProviderContainer(
        overrides: generatedClientBoundaryOverrides(
          transport: MockClient(
            (request) async =>
                http.Response(jsonEncode(<String, Object?>{}), 200),
          ),
          environment: CloudEnvironment.beta,
          gatewayBaseUri: Uri.parse('https://api.beta.quwoquan.test'),
        ),
      );
      addTearDown(container.dispose);

      final environment = container.read(cloudRuntimeEnvironmentProvider);
      expect(environment.environment, CloudEnvironment.beta);
      expect(
        environment.gatewayBaseUri,
        Uri.parse('https://api.beta.quwoquan.test'),
      );
    });

    test('generated client 可构造，但传输只能是测试交出的 MockClient', () {
      final requestedPaths = <String>[];
      final container = ProviderContainer(
        overrides: generatedClientBoundaryOverrides(
          transport: MockClient((request) async {
            requestedPaths.add(request.url.path);
            return http.Response(jsonEncode(<String, Object?>{}), 200);
          }),
        ),
      );
      addTearDown(container.dispose);

      expect(container.read(generatedCloudOperationClientProvider), isNotNull);
      expect(requestedPaths, isEmpty);
    });
  });
}
