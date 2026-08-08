// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-003
// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#sit-003
// readiness_case: recovery_failure_report_recovery_failure_app_local
import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/product_ops_service/product_ops/recovery_failure/adapters/remote_recovery_failure_writer.dart';
import 'package:quwoquan_app/service/product_ops_service/product_ops/recovery_failure/application/recovery_failure_writer.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/context/cloud_operation_header_factory.dart';
import 'package:quwoquan_app/runtime/platform/app_recovery_native_bridge.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/shell/recovery/recovery_failure_reporter.dart';
import 'package:quwoquan_app/runtime/shell/recovery/recovery_operation_gateway.dart';
import 'package:quwoquan_app/runtime/transport/generated/ops/ops_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('test/quwoquan/recovery_failure');

  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
  });

  test('persists secure envelope before exact ten-field upload', () async {
    final store = _MemoryStore();
    final executor = _RecoveryFailureExecutor();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          if (call.method != 'getRecoveryContext') return null;
          return _nativeContext;
        });
    final reporter = RecoveryFailureReporter(
      store: store,
      nativeBridge: AppRecoveryNativeBridge(channel: channel),
      gateway: _gateway(executor),
      now: () => DateTime.utc(2026, 7, 26, 0, 25),
    );

    expect(
      await reporter.record(
        errorSource: 'flutter',
        errorType: 'DatabaseOpenException',
        errorMessage: 'authorization=secret user@example.com',
        stackTrace: 'at /Users/alice/app.dart https://quwoquan.com/p?a=1',
      ),
      isTrue,
    );
    await reporter.flush();

    expect(executor.body?.keys.toSet(), _exactFailureFields);
    expect(executor.body?['errorMessage'], contains('<redacted>'));
    expect(executor.body?['errorMessage'], isNot(contains('user@example.com')));
    expect(executor.body?['stackTrace'], isNot(contains('/Users/alice')));
    expect(executor.body?['stackTrace'], isNot(contains('a=1')));
    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.opsRecoveryFailureReportRecoveryFailure,
    );
    // canonical 契约只把恢复上报绑定在 `welcome` 面；换成其他 surface 会被
    // header 工厂 fail-closed 拒绝。
    expect(executor.context?.surfaceId, AppUiSurfaces.welcome.id);
    expect(
      executor.context?.clientPageId,
      OpsRequestPageIds.reportRecoveryFailure,
    );
    expect(executor.context?.routeId, isNull);
    final headers = CloudOperationHeaderFactory(
      clientContextProvider: const _RecoveryClientContextProvider(),
      now: () => DateTime.utc(2026, 7, 26, 0, 25),
      entropy: () => 7,
    ).build(operation: executor.operation!, invocation: executor.context!);
    expect(headers.containsKey('X-Client-Route-Id'), isFalse);
    expect(store.raw, isNull);
  });

  test(
    'retains failures after network errors and caps queue at twenty',
    () async {
      final store = _MemoryStore();
      final executor = _RecoveryFailureExecutor(failure: StateError('offline'));
      var now = DateTime.utc(2026, 7, 26);
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async {
            if (call.method != 'getRecoveryContext') return null;
            return _nativeContext;
          });
      final reporter = RecoveryFailureReporter(
        store: store,
        nativeBridge: AppRecoveryNativeBridge(channel: channel),
        gateway: _gateway(executor),
        now: () => now,
      );

      for (var index = 0; index < 22; index += 1) {
        now = now.add(const Duration(seconds: 16));
        expect(
          await reporter.record(
            errorSource: 'flutter',
            errorType: 'Failure$index',
            errorMessage: 'failure $index',
            stackTrace: 'stack $index',
          ),
          isTrue,
        );
      }
      await reporter.flush();
      final queue = jsonDecode(store.raw!) as List<Object?>;
      expect(queue, hasLength(RecoveryFailureReporter.maxRecords));
      expect(((queue.first as Map)['failure'] as Map)['errorType'], 'Failure2');
      expect((queue.first as Map)['attempts'], greaterThan(0));
    },
  );

  test(
    'native queue store is available through the minimal recovery bridge',
    () async {
      String? raw;
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async {
            switch (call.method) {
              case 'readRecoveryFailureQueue':
                return raw;
              case 'writeRecoveryFailureQueue':
                raw = (call.arguments as Map)['value'] as String;
                return true;
              case 'clearRecoveryFailureQueue':
                raw = null;
                return true;
            }
            return null;
          });
      final store = NativeRecoveryFailureStore(
        nativeBridge: AppRecoveryNativeBridge(channel: channel),
      );

      await store.write('[{"encryptedByNative":true}]');
      expect(await store.read(), '[{"encryptedByNative":true}]');
      await store.clear();
      expect(await store.read(), isNull);
    },
  );

  test(
    'corrupt and expired queue entries are discarded without throwing',
    () async {
      final store = _MemoryStore()..raw = '{corrupt';
      final executor = _RecoveryFailureExecutor(failure: StateError('offline'));
      var now = DateTime.utc(2026, 7, 26);
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async {
            if (call.method != 'getRecoveryContext') return null;
            return _nativeContext;
          });
      final reporter = RecoveryFailureReporter(
        store: store,
        nativeBridge: AppRecoveryNativeBridge(channel: channel),
        gateway: _gateway(executor),
        now: () => now,
      );

      await reporter.flush();
      expect(store.raw, isNull);
      expect(
        await reporter.record(
          errorSource: 'native',
          errorType: 'FatalStartup',
          errorMessage: 'failed',
          stackTrace: 'stack',
        ),
        isTrue,
      );
      await reporter.flush();
      expect(store.raw, isNotNull);

      now = now.add(const Duration(days: 8));
      await reporter.flush();
      expect(store.raw, isNull);
    },
  );
}

const _nativeContext = <String, Object>{
  'platform': 'android',
  'appVersion': '1.8.2',
  'buildNumber': 18201,
  'osVersion': '15',
  'deviceModel': 'Pixel',
  'environment': 'alpha',
  'recoveryBaseUrl': 'https://api.quwoquan.com',
  'runtimeConfigDigest':
      'sha256:1111111111111111111111111111111111111111111111111111111111111111',
  'effectiveLaunchManifestDigest':
      'sha256:2222222222222222222222222222222222222222222222222222222222222222',
  'publicWebUrl': 'https://quwoquan.com',
  'appDownloadBaseUrl': 'https://cdn.quwoquan.com/download',
};

const _exactFailureFields = <String>{
  'occurredAt',
  'appVersion',
  'buildNumber',
  'platform',
  'osVersion',
  'deviceModel',
  'errorSource',
  'errorType',
  'errorMessage',
  'stackTrace',
};

final class _MemoryStore implements RecoveryFailureStore {
  String? raw;

  @override
  Future<void> clear() async => raw = null;

  @override
  Future<String?> read() async => raw;

  @override
  Future<void> write(String value) async => raw = value;
}

RecoveryOperationGateway _gateway(_RecoveryFailureExecutor executor) {
  return RecoveryOperationGateway(
    operations: _FailureOperations(
      RemoteRecoveryFailureWriter(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: () => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.welcome.id,
          clientPageId: OpsRequestPageIds.reportRecoveryFailure,
          actor: const CloudOperationActorContext(
            deviceActorId: 'recovery-device-actor',
          ),
        ),
      ),
    ),
  );
}

final class _FailureOperations implements RecoveryRuntimeOperations {
  const _FailureOperations(this.writer);

  final RecoveryFailureWriter writer;

  @override
  Future<RecoveryVersionResponse> getVersion(RecoveryVersionRequest request) =>
      throw UnsupportedError('not used by recovery failure contract');

  @override
  Future<void> reportFailure(RecoveryFailurePayload payload) {
    return writer.write(
      RecoveryFailureRecord(
        occurredAt: payload.occurredAt,
        appVersion: payload.appVersion,
        buildNumber: payload.buildNumber,
        platform: payload.platform,
        osVersion: payload.osVersion,
        deviceModel: payload.deviceModel,
        errorSource: payload.errorSource,
        errorType: payload.errorType,
        errorMessage: payload.errorMessage,
        stackTrace: payload.stackTrace,
      ),
    );
  }
}

final class _RecoveryFailureExecutor implements CloudOperationExecutor {
  _RecoveryFailureExecutor({this.failure});

  final Object? failure;
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
  Map<String, Object?>? body;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    this.operation = operation;
    this.context = context;
    final encodedBody = requestEncoder().body;
    body = encodedBody == null
        ? null
        : (encodedBody as Map).cast<String, Object?>();
    final configuredFailure = failure;
    if (configuredFailure != null) throw configuredFailure;
    return responseDecoder(null);
  }
}

final class _RecoveryClientContextProvider
    implements CloudClientContextProvider {
  const _RecoveryClientContextProvider();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'recovery-failure-contract',
      platform: 'android',
      appVersion: '1.8.2',
      locale: 'zh-CN',
      deviceActorId: 'recovery-device-actor',
    );
  }
}
