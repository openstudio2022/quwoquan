// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-003
// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#sit-003
import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/app/recovery/recovery_failure_reporter.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/ops_api_metadata.g.dart';
import 'package:quwoquan_app/core/platform/app_recovery_native_bridge.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('test/quwoquan/recovery_failure');

  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
  });

  test('persists secure envelope before exact ten-field upload', () async {
    final store = _MemoryStore();
    Map<String, Object?>? uploaded;
    Uri? uploadUri;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          if (call.method != 'getRecoveryContext') return null;
          return _nativeContext;
        });
    final reporter = RecoveryFailureReporter(
      store: store,
      nativeBridge: AppRecoveryNativeBridge(channel: channel),
      client: MockClient((request) async {
        uploadUri = request.url;
        uploaded = (jsonDecode(request.body) as Map).cast<String, Object?>();
        return http.Response('', 204);
      }),
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

    expect(uploaded?.keys.toSet(), _exactFailureFields);
    expect(uploaded?['errorMessage'], contains('<redacted>'));
    expect(uploaded?['errorMessage'], isNot(contains('user@example.com')));
    expect(uploaded?['stackTrace'], isNot(contains('/Users/alice')));
    expect(uploaded?['stackTrace'], isNot(contains('a=1')));
    expect(uploadUri?.path, OpsApiMetadata.reportRecoveryFailurePath);
    expect(store.raw, isNull);
  });

  test(
    'retains failures after network errors and caps queue at twenty',
    () async {
      final store = _MemoryStore();
      var now = DateTime.utc(2026, 7, 26);
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async {
            if (call.method != 'getRecoveryContext') return null;
            return _nativeContext;
          });
      final reporter = RecoveryFailureReporter(
        store: store,
        nativeBridge: AppRecoveryNativeBridge(channel: channel),
        client: MockClient((_) async => throw StateError('offline')),
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
      var now = DateTime.utc(2026, 7, 26);
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async {
            if (call.method != 'getRecoveryContext') return null;
            return _nativeContext;
          });
      final reporter = RecoveryFailureReporter(
        store: store,
        nativeBridge: AppRecoveryNativeBridge(channel: channel),
        client: MockClient((_) async => throw StateError('offline')),
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
  'recoveryBaseUrl': 'https://api.quwoquan.com',
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
