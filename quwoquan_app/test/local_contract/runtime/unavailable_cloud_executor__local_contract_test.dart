import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/executor/generated_cloud_operation_executor.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/runtime/transport/executor/unavailable_cloud_operation_executor.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import '../../support/runtime/config/runtime_package_test_hydration.dart';

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const executor = UnavailableCloudOperationExecutor();
  final operation =
      appCloudOperationContracts[AppCloudOperationIds
          .integrationLocationSearchLocations]!;
  const invocation = CloudOperationInvocationContext(
    surfaceId: 'createWorkspace',
    clientPageId: 'location-search',
    actor: CloudOperationActorContext(),
  );

  // spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008
  test('演练执行器仅限离线环境，在线环境不消费全局演练安装', () {
    final httpClient = CloudHttpClient();
    addTearDown(httpClient.close);
    addTearDown(clearInstalledCloudOperationExecutor);
    installCloudOperationExecutor(executor);

    CloudOperationExecutor build(CloudRuntimeEnvironment environment) =>
        buildGeneratedCloudOperationExecutor(
          httpClient: httpClient,
          clientContextProvider: const _IsolationClientContext(),
          telemetrySink: const _IsolationTelemetrySink(),
          environment: environment,
        );

    expect(
      build(CloudRuntimeEnvironment.offline(environment: CloudEnvironment.alpha)),
      same(executor),
    );
    for (final environment in [
      CloudEnvironment.beta,
      CloudEnvironment.gamma,
      CloudEnvironment.prod,
    ]) {
      expect(
        build(CloudRuntimeEnvironment(
          environment: environment,
          gatewayBaseUri: Uri.parse('https://executor-isolation.invalid'),
        )),
        isA<AppGeneratedCloudOperationExecutor>(),
        reason: environment.name,
      );
    }
    clearInstalledCloudOperationExecutor();
    expect(
      build(CloudRuntimeEnvironment.offline(environment: CloudEnvironment.alpha)),
      isA<UnavailableCloudOperationExecutor>(),
    );
  });

  test('已验信离线 source 不可由显式在线环境绕过', () async {
    await hydrateRuntimePackageForTests(environment: 'alpha');
    addTearDown(() => hydrateRuntimePackageForTests(environment: 'beta'));
    final httpClient = CloudHttpClient();
    addTearDown(httpClient.close);
    addTearDown(clearInstalledCloudOperationExecutor);
    installCloudOperationExecutor(executor);
    expect(
      buildGeneratedCloudOperationExecutor(
        httpClient: httpClient,
        clientContextProvider: const _IsolationClientContext(),
        telemetrySink: const _IsolationTelemetrySink(),
      ),
      same(executor),
    );
    expect(
      buildGeneratedCloudOperationExecutor(
        httpClient: httpClient,
        clientContextProvider: const _IsolationClientContext(),
        telemetrySink: const _IsolationTelemetrySink(),
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.beta,
          gatewayBaseUri: Uri.parse('https://executor-isolation.invalid'),
        ),
      ),
      isA<UnavailableCloudOperationExecutor>(),
    );
    await hydrateRuntimePackageForTests(environment: 'beta');
    expect(
      buildGeneratedCloudOperationExecutor(
        httpClient: httpClient,
        clientContextProvider: const _IsolationClientContext(),
        telemetrySink: const _IsolationTelemetrySink(),
        environment: CloudRuntimeEnvironment.offline(
          environment: CloudEnvironment.alpha,
        ),
      ),
      isA<UnavailableCloudOperationExecutor>(),
    );
    expect(
      buildGeneratedCloudOperationExecutor(
        httpClient: httpClient,
        clientContextProvider: const _IsolationClientContext(),
        telemetrySink: const _IsolationTelemetrySink(),
      ),
      isA<AppGeneratedCloudOperationExecutor>(),
    );
  });

  test('离线普通请求在编码与解码前拒绝，不伪造服务器结果', () async {
    var encoded = false;
    var decoded = false;
    await expectLater(
      executor.send<Object?>(
        operation,
        context: invocation,
        requestEncoder: () {
          encoded = true;
          throw StateError('request encoder must not run');
        },
        responseDecoder: (value) {
          decoded = true;
          return value;
        },
      ),
      throwsA(
        isA<CloudException>().having(
          (error) => error.runtimeFailure.kind,
          'kind',
          RuntimeFailureKind.unsupported,
        ),
      ),
    );
    expect(encoded, isFalse);
    expect(decoded, isFalse);
  });

  test('离线流式请求不能启动网络或产出伪造事件', () async {
    var encoded = false;
    await expectLater(
      executor.stream<Object?>(
        operation,
        context: invocation,
        requestEncoder: () {
          encoded = true;
          throw StateError('request encoder must not run');
        },
        responseDecoder: (value) => value,
      ),
      emitsError(isA<CloudException>()),
    );
    expect(encoded, isFalse);
  });
}

final class _IsolationClientContext implements CloudClientContextProvider {
  const _IsolationClientContext();

  @override
  CloudClientContextSnapshot snapshot() => const CloudClientContextSnapshot(
    sessionId: 'isolation-session',
    deviceActorId: 'isolation-device',
    platform: 'test',
    appVersion: 'test',
    locale: 'zh-CN',
  );
}

final class _IsolationTelemetrySink implements CloudOperationTelemetrySink {
  const _IsolationTelemetrySink();

  @override
  void record(CloudOperationTelemetryEvent event) {}
}
