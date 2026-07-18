import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/cloud/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_context_provider.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_outbox.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_session_store.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_transport.dart';
import 'package:quwoquan_app/infrastructure/local/actor_queue/actor_queue_storage.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempDirectory;
  late DateTime now;
  late AppTelemetrySessionStore sessionStore;
  late AppTelemetryContextProvider contextProvider;
  late _CapturingTransport transport;
  late AppTelemetryOutbox outbox;
  late AppTelemetryReporter reporter;

  setUp(() async {
    tempDirectory = await Directory.systemTemp.createTemp(
      'telemetry_reporter_',
    );
    Hive.init(tempDirectory.path);
    now = DateTime.utc(2026, 7, 18, 8);
    sessionStore = AppTelemetrySessionStore(
      guestKeyStore: _GuestKeyStore(),
      now: () => now,
    );
    await sessionStore.initialize(authenticatedUserKey: 'account.with.dot');
    contextProvider = AppTelemetryContextProvider(
      staticContextLoader: () async => const AppTelemetryStaticContext(
        deviceManufacturer: 'Apple',
        deviceModel: 'iPhone17,1',
        appVersion: '1.2.3+45',
      ),
      connectivityLoader: () async => const <ConnectivityResult>[
        ConnectivityResult.wifi,
      ],
      connectivityChanges: const Stream<List<ConnectivityResult>>.empty(),
    );
    await contextProvider.initialize();
    AppPageContextStore.instance.setPageName('home');
    transport = _CapturingTransport();
    outbox = AppTelemetryOutbox(
      partition: ActorQueuePartition(
        environment: 'gamma',
        accountId: 'account.with.dot',
        deviceId: 'install-a',
      ),
      storage: ActorQueueStorage(keyStore: _KeyStore()),
      transport: transport,
      now: () => now,
    );
    reporter = AppTelemetryReporter(
      sessionStore: sessionStore,
      contextProvider: contextProvider,
      outbox: outbox,
      now: () => now,
    );
  });

  tearDown(() async {
    await reporter.dispose();
    await contextProvider.dispose();
    sessionStore.dispose();
    AppPageContextStore.instance.markBootstrap();
    await Hive.deleteFromDisk();
    if (await tempDirectory.exists()) {
      await tempDirectory.delete(recursive: true);
    }
  });

  test('生成严格九字段公共信封并以规范化 body 摘要作为幂等键', () async {
    expect(
      await reporter.record(AppTelemetryPayload.pageOpen()),
      AppTelemetryRecordResult.accepted,
    );
    expect(await reporter.flush(), AppTelemetryFlushResult.delivered);

    final body = jsonDecode(transport.body!) as Map<String, Object?>;
    final event =
        (body['events']! as List<Object?>).single as Map<String, Object?>;
    expect(event.keys.toSet(), AppTelemetryCatalog.commonFields.toSet());
    expect(event['pageName'], 'home');
    expect(event['networkClass'], 'wifi');
    expect(
      AppTelemetrySessionStore.parseSessionId(
        event['sessionId']! as String,
      ).userKey,
      'account.with.dot',
    );
    expect(transport.idempotencyKey, hasLength(64));
  });

  test('未登记页面和越界时间在本地拒绝，正常、慢和异常启动全部保留', () async {
    expect(
      await reporter.record(
        AppTelemetryPayload.pageOpen(),
        pageName: 'unknown_page',
      ),
      AppTelemetryRecordResult.rejected,
    );
    expect(
      await reporter.record(
        AppTelemetryPayload.pageOpen(),
        occurredAt: now.subtract(const Duration(hours: 73)),
      ),
      AppTelemetryRecordResult.rejected,
    );
    expect(AppTelemetryCatalog.events['app_startup']!.normalSampleRate, 1);
    expect(
      await reporter.record(
        AppTelemetryPayload.appStartup(
          tClickToFirstFrameMs: 100,
          tFirstFrameToShellMs: 200,
          tShellToContentMs: 700,
          tClickToContentMs: 1000,
          hasError: false,
        ),
      ),
      AppTelemetryRecordResult.accepted,
    );
    expect(
      await reporter.record(
        AppTelemetryPayload.appStartup(
          tClickToFirstFrameMs: 100,
          tFirstFrameToShellMs: 200,
          tShellToContentMs: 2700,
          tClickToContentMs: 3000,
          hasError: false,
        ),
      ),
      AppTelemetryRecordResult.accepted,
    );
    expect(
      await reporter.record(
        AppTelemetryPayload.appStartup(
          tClickToFirstFrameMs: 100,
          tFirstFrameToShellMs: 200,
          tShellToContentMs: 300,
          tClickToContentMs: 600,
          hasError: true,
        ),
      ),
      AppTelemetryRecordResult.accepted,
    );
    expect(
      await reporter.record(
        AppTelemetryPayload.runtimeException(errorCode: 'APP.RUNTIME.test'),
      ),
      AppTelemetryRecordResult.accepted,
    );
  });

  test('视频 QoE 保持强类型且不允许推荐归因字段进入 Ops 遥测', () async {
    final payload = AppTelemetryPayload.videoPlaybackQoe(
      readyMs: 420,
      rebufferCount: 1,
      rebufferMs: 240,
      seekCount: 2,
      playbackMode: 'autoplay',
      declaredDurationMs: 15000,
      observedDurationMs: 14900,
      durationMismatch: false,
      result: 'success',
    );

    expect(AppTelemetryCatalog.validate(payload), isNull);
    expect(payload.extensions.containsKey('postId'), isFalse);
    expect(payload.extensions.containsKey('feedRequestId'), isFalse);
    expect(await reporter.record(payload), AppTelemetryRecordResult.accepted);
  });
}

final class _CapturingTransport implements AppTelemetryTransport {
  String? body;
  String? idempotencyKey;

  @override
  Future<AppTelemetryBatchAck> sendSealedBatch({
    required String canonicalBody,
    required String idempotencyKey,
  }) async {
    body = canonicalBody;
    this.idempotencyKey = idempotencyKey;
    final decoded = jsonDecode(canonicalBody) as Map<String, Object?>;
    return AppTelemetryBatchAck(
      acceptedCount: (decoded['events']! as List<Object?>).length,
      duplicateBatch: false,
    );
  }
}

final class _GuestKeyStore implements AppTelemetryGuestKeyStore {
  String value = 'guest_01ARZ3NDEKTSV4RRFFQ69G5FAV';

  @override
  Future<String?> read() async => value;

  @override
  Future<void> write(String value) async => this.value = value;
}

final class _KeyStore implements ActorQueueEncryptionKeyStore {
  final Map<String, String> values = <String, String>{};

  @override
  Future<void> delete(String key) async => values.remove(key);

  @override
  Future<String?> read(String key) async => values[key];

  @override
  Future<void> write(String key, String value) async => values[key] = value;
}
