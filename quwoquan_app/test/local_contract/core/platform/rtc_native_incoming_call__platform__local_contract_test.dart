import 'dart:async';
import 'dart:convert';

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/rtc/call_session/incoming_call_presentation_acknowledger.dart';
import 'package:quwoquan_app/application/user/device_registration/device_push_endpoint_writer.dart';
import 'package:quwoquan_app/cloud/remote/notification/incoming_call/incoming_call_presentation_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/device_registration/device_push_endpoint_remote.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/core/platform/firebase_incoming_call_runtime.dart';
import 'package:quwoquan_app/core/platform/incoming_call_envelope.dart';
import 'package:quwoquan_app/core/platform/incoming_call_native_bridge.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';
import 'package:quwoquan_app/core/platform/push_endpoint_gateway.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const callId = '550e8400-e29b-41d4-a716-446655440000';
  final now = DateTime.utc(2026, 7, 20, 10);

  IncomingCallEnvelope envelope({
    String id = callId,
    String deliveryKey = 'delivery-1',
    DateTime? expiresAt,
  }) {
    return IncomingCallEnvelope(
      callId: id,
      deliveryKey: deliveryKey,
      targetPersonaId: 'target-persona',
      callType: 'audio',
      callerName: '来电用户',
      sourceLabel: '联系人',
      trustRelation: 'known',
      expiresAt: expiresAt ?? now.add(const Duration(minutes: 1)),
    );
  }

  test('来电信封只接受 metadata 定义的信任关系闭集', () {
    expect(
      () => IncomingCallEnvelope(
        callId: callId,
        deliveryKey: 'delivery-invalid-trust',
        targetPersonaId: 'target-persona',
        callType: 'audio',
        callerName: '来电用户',
        sourceLabel: '联系人',
        trustRelation: 'following',
        expiresAt: now.add(const Duration(minutes: 1)),
      ),
      throwsFormatException,
    );
  });

  test('来电信封拒绝过期且 WS/native Push 竞态只允许一次展示', () {
    final dedupe = BoundedIncomingCallDedupe(capacity: 2);

    expect(
      dedupe.claim(envelope(expiresAt: now), now: now),
      IncomingCallClaimResult.expired,
    );
    expect(
      dedupe.claim(envelope(), now: now),
      IncomingCallClaimResult.accepted,
    );
    expect(
      dedupe.claim(
        envelope(
          id: '3d594650-3436-4b65-9f6a-0d7c4f2c7cb0',
          deliveryKey: 'delivery-1',
        ),
        now: now,
      ),
      IncomingCallClaimResult.duplicate,
    );
    expect(
      dedupe.claim(
        envelope(id: callId, deliveryKey: 'native-delivery'),
        now: now,
      ),
      IncomingCallClaimResult.duplicate,
    );

    final cancelledFirst = BoundedIncomingCallDedupe();
    final cancelledEnvelope = envelope(
      id: '44da235a-f99e-4e76-a617-ea074f697d8d',
      deliveryKey: 'cancel-before-ring',
    );
    cancelledFirst.suppress(cancelledEnvelope);
    expect(
      cancelledFirst.claim(cancelledEnvelope, now: now),
      IncomingCallClaimResult.duplicate,
    );
  });

  test('FCM token 初值与刷新均持久化，Web 不初始化 Firebase', () async {
    final gateway = _RecordingPushEndpointGateway();
    final client = _FakeFirebasePushMessagingClient(initialToken: 'fcm-1');
    final runtime = FirebaseIncomingCallRuntime(
      pushEndpointGateway: gateway,
      messagingClient: client,
      platformReader: () => AppPlatform.android,
    );
    final foregroundEnvelopes = <IncomingCallEnvelope>[];
    final foregroundSubscription = runtime.foregroundIncomingCalls.listen(
      foregroundEnvelopes.add,
    );
    addTearDown(foregroundSubscription.cancel);
    final foregroundCancellations = <IncomingCallPushEnvelope>[];
    final cancellationSubscription = runtime.foregroundCancellations.listen(
      foregroundCancellations.add,
    );
    addTearDown(cancellationSubscription.cancel);

    final state = await runtime.start();
    expect(state.supported, isTrue);
    expect(state.configured, isTrue);
    expect(client.notificationPermissionRequested, isFalse);
    expect(
      gateway.upserts,
      contains(DevicePushEndpoint(kind: PushEndpointKind.fcm, token: 'fcm-1')),
    );

    client.emitToken('fcm-2');
    await Future<void>.delayed(Duration.zero);
    expect(
      gateway.upserts,
      contains(DevicePushEndpoint(kind: PushEndpointKind.fcm, token: 'fcm-2')),
    );
    final foregroundEnvelope = envelope(
      expiresAt: DateTime.now().toUtc().add(const Duration(minutes: 1)),
    );
    final occurredAt = DateTime.now().toUtc();
    client.emitForeground(
      RemoteMessage(
        data: <String, dynamic>{
          'action': 'ring',
          ...foregroundEnvelope.toMap(),
          'occurredAt': occurredAt.toIso8601String(),
        },
      ),
    );
    await Future<void>.delayed(Duration.zero);
    expect(foregroundEnvelopes, <IncomingCallEnvelope>[foregroundEnvelope]);
    client.emitForeground(
      RemoteMessage(
        data: <String, dynamic>{
          'action': 'cancel',
          ...foregroundEnvelope.toMap(),
          'occurredAt': occurredAt
              .add(const Duration(seconds: 1))
              .toIso8601String(),
        },
      ),
    );
    await Future<void>.delayed(Duration.zero);
    expect(foregroundCancellations, hasLength(1));
    expect(
      foregroundCancellations.single.action,
      IncomingCallPushAction.cancel,
    );
    await runtime.stop();

    final webClient = _FakeFirebasePushMessagingClient(initialToken: 'unused');
    final webRuntime = FirebaseIncomingCallRuntime(
      pushEndpointGateway: gateway,
      messagingClient: webClient,
      platformReader: () => AppPlatform.web,
    );
    expect((await webRuntime.start()).supported, isFalse);
    expect(webClient.initializeCount, 0);
  });

  test('缺少真实 Firebase 配置时 fail-closed 且不写入假 token', () async {
    final gateway = _RecordingPushEndpointGateway();
    final runtime = FirebaseIncomingCallRuntime(
      pushEndpointGateway: gateway,
      messagingClient: _FakeFirebasePushMessagingClient(
        initialToken: null,
        initializationError: PlatformException(code: 'missing-config'),
      ),
      platformReader: () => AppPlatform.android,
    );

    final state = await runtime.start();
    expect(state.supported, isTrue);
    expect(state.configured, isFalse);
    expect(gateway.upserts, isEmpty);
  });

  test('原生 pending action 以 typed action 消费', () async {
    const channel = MethodChannel('test/quwoquan/rtc/incoming_call');
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    var flutterReady = false;
    messenger.setMockMethodCallHandler(channel, (call) async {
      if (call.method == 'setIncomingCallFlutterReady') {
        flutterReady =
            (call.arguments as Map<Object?, Object?>)['ready'] == true;
        return null;
      }
      if (call.method == 'consumePendingIncomingCallActions') {
        return <Map<String, Object>>[
          <String, Object>{
            'callId': callId,
            'action': 'accept',
            'occurredAt': now.toIso8601String(),
          },
        ];
      }
      return null;
    });
    addTearDown(() => messenger.setMockMethodCallHandler(channel, null));

    const bridge = MethodChannelIncomingCallNativeBridge(channel: channel);
    await bridge.setFlutterReady(true);
    final actions = await bridge.consumePendingActions();

    expect(flutterReady, isTrue);
    expect(actions, hasLength(1));
    expect(actions.single.callId, callId);
    expect(actions.single.type, IncomingCallNativeActionType.accept);
  });

  test('token mutation 仅在真实 writer 成功后 ack，登出排队 remove', () async {
    final gateway = _RecordingPushEndpointGateway()
      ..pending.add(
        PushEndpointMutation(
          mutationId: 'mutation-1',
          kind: PushEndpointMutationKind.upsert,
          endpoint: DevicePushEndpoint(
            kind: PushEndpointKind.fcm,
            token: 'fcm-token',
          ),
          occurredAt: now,
        ),
      );
    final writer = _RecordingDevicePushEndpointWriter();
    final coordinator = DevicePushEndpointCoordinator(
      gateway: gateway,
      writer: writer,
    );

    await coordinator.syncAfterLogin();
    expect(writer.upserts.single.token, 'fcm-token');
    expect(gateway.acknowledged, <String>['mutation-1']);

    await coordinator.removeForLogout();
    expect(gateway.removalsQueued, isTrue);
  });

  test('push endpoint token 与 mutation 只写入安全存储并串行收敛', () async {
    const channel = MethodChannel('test/quwoquan/rtc/push_endpoint_store');
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(channel, (call) async {
      if (call.method == 'readPushEndpointMutations') {
        return const <Object>[];
      }
      return null;
    });
    addTearDown(() => messenger.setMockMethodCallHandler(channel, null));
    final secretStore = _MemoryPushEndpointSecretStore();
    var legacyPurgeCount = 0;
    final gateway = PersistentPushEndpointGateway(
      secretStore: secretStore,
      legacyPlaintextMigrator: () async {
        legacyPurgeCount += 1;
      },
      channel: channel,
    );
    final endpoint = DevicePushEndpoint(
      kind: PushEndpointKind.fcm,
      token: 'fcm-secret-token',
    );

    await Future.wait(<Future<void>>[
      gateway.recordUpsert(endpoint),
      gateway.recordUpsert(endpoint),
    ]);
    final upserts = await gateway.readPendingMutations();
    expect(upserts, hasLength(1));
    expect(upserts.single.kind, PushEndpointMutationKind.upsert);
    expect(secretStore.values.values.join(), contains('fcm-secret-token'));

    await gateway.queueActiveEndpointRemovals();
    final pending = await gateway.readPendingMutations();
    expect(pending.map((entry) => entry.kind), <PushEndpointMutationKind>[
      PushEndpointMutationKind.upsert,
      PushEndpointMutationKind.remove,
    ]);
    expect(
      secretStore.values.containsKey('rtc.push_endpoint.active_tokens'),
      isFalse,
    );

    for (final mutation in pending) {
      await gateway.acknowledgeMutation(mutation.mutationId);
    }
    expect(await gateway.readPendingMutations(), isEmpty);
    expect(legacyPurgeCount, 1);
    expect(
      secretStore.values.containsKey('rtc.push_endpoint.pending_mutations'),
      isFalse,
    );
  });

  test('旧版 SharedPreferences token 与待同步 mutation 先迁入安全存储再删除明文', () async {
    const pendingKey = 'rtc.push_endpoint.pending_mutations';
    const activeKey = 'rtc.push_endpoint.active_tokens';
    final occurredAt = DateTime.utc(2026, 7, 20, 9);
    SharedPreferences.setMockInitialValues(<String, Object>{
      pendingKey: jsonEncode(<Object>[
        <String, Object>{
          'mutationId': 'legacy-mutation-1',
          'action': 'upsert',
          'endpointKind': 'fcm',
          'token': 'legacy-fcm-token',
          'occurredAt': occurredAt.toIso8601String(),
        },
      ]),
      activeKey: jsonEncode(<String, String>{'fcm': 'legacy-fcm-token'}),
    });
    addTearDown(
      () => SharedPreferences.setMockInitialValues(<String, Object>{}),
    );

    final secretStore = _MemoryPushEndpointSecretStore();
    final gateway = PersistentPushEndpointGateway(
      secretStore: secretStore,
      channel: const MethodChannel(
        'test/quwoquan/rtc/push_endpoint_legacy_migration',
      ),
    );

    final pending = await gateway.readPendingMutations();

    expect(pending, hasLength(1));
    expect(pending.single.mutationId, 'legacy-mutation-1');
    expect(pending.single.endpoint.token, 'legacy-fcm-token');
    expect(secretStore.values[pendingKey], contains('legacy-fcm-token'));
    expect(secretStore.values[activeKey], contains('legacy-fcm-token'));
    final preferences = await SharedPreferences.getInstance();
    expect(preferences.containsKey(pendingKey), isFalse);
    expect(preferences.containsKey(activeKey), isFalse);
  });

  test('设备 endpoint 与展示 ACK 均经 generated operation client', () async {
    final executor = _RecordingCloudOperationExecutor();
    final client = GeneratedCloudOperationClient(executor);
    const invocation = CloudOperationInvocationContext(
      surfaceId: 'rtc.incoming',
      clientPageId: 'rtc.incoming.test',
      actor: CloudOperationActorContext(
        accountId: 'account-1',
        personaId: 'persona-1',
        deviceActorId: 'device-1',
      ),
      idempotencyKey: 'idempotency-1',
    );
    final endpointWriter = RemoteDevicePushEndpointWriter(
      client: client,
      invocationContext: (_) => invocation,
      clientContextSnapshot: () => const CloudClientContextSnapshot(
        sessionId: 'session-1',
        platform: 'ios',
        appVersion: '1.0.0',
        locale: 'zh-CN',
        deviceActorId: 'device-1',
      ),
    );
    final acknowledger = RemoteIncomingCallPresentationAcknowledger(
      client: client,
      invocationContext: (_) => invocation,
    );
    final receipt = IncomingCallPresentationReceipt(
      callId: callId,
      deliveryKey: 'delivery-1',
      source: IncomingCallPresentationSource.nativePush,
      presentedAt: now,
    );

    await endpointWriter.upsert(
      DevicePushEndpoint(kind: PushEndpointKind.fcm, token: 'fcm-token'),
    );
    await endpointWriter.remove(
      DevicePushEndpoint(kind: PushEndpointKind.fcm, token: 'fcm-token'),
    );
    await acknowledger.acknowledge(receipt);
    expect(executor.operationIds, <String>[
      AppCloudOperationIds.userDeviceRegistrationUpsertDevicePushEndpoint,
      AppCloudOperationIds.userDeviceRegistrationRemoveDevicePushEndpoint,
      AppCloudOperationIds
          .notificationNotificationDeliveryJobAckIncomingCallPresentation,
    ]);
    expect(executor.payloads.first.pathParameters, <String, String>{
      'deviceId': 'device-1',
      'endpointKind': 'fcm',
    });
    expect(executor.payloads.first.body, <String, Object?>{
      'token': 'fcm-token',
      'appVersion': '1.0.0',
    });
    expect(executor.payloads.last.body, <String, Object?>{
      'deliveryKey': 'delivery-1',
    });
  });

  test('Web/OHOS 原生桥显式返回不支持能力', () async {
    const bridge = UnsupportedIncomingCallNativeBridge();
    final capability = await bridge.readCapability();

    expect(capability.nativeUiAvailable, isFalse);
    expect(capability.backgroundPushConfigured, isFalse);
    expect(await bridge.readPendingEnvelopes(), isEmpty);
  });
}

final class _FakeFirebasePushMessagingClient
    implements FirebasePushMessagingClient {
  _FakeFirebasePushMessagingClient({
    required this.initialToken,
    this.initializationError,
  });

  final String? initialToken;
  final Object? initializationError;
  final _refreshes = StreamController<String>.broadcast(sync: true);
  final _foregroundMessages = StreamController<RemoteMessage>.broadcast(
    sync: true,
  );
  int initializeCount = 0;
  bool notificationPermissionRequested = false;

  void emitToken(String token) => _refreshes.add(token);

  void emitForeground(RemoteMessage message) =>
      _foregroundMessages.add(message);

  @override
  Future<void> initialize() async {
    initializeCount += 1;
    final error = initializationError;
    if (error != null) {
      throw error;
    }
  }

  @override
  Future<String?> readToken() async => initialToken;

  @override
  Stream<String> get tokenRefreshes => _refreshes.stream;

  @override
  Stream<RemoteMessage> get foregroundMessages => _foregroundMessages.stream;

  @override
  Future<bool> readNotificationAuthorization() async => false;
}

final class _RecordingPushEndpointGateway implements PushEndpointGateway {
  final upserts = <DevicePushEndpoint>[];
  final pending = <PushEndpointMutation>[];
  final acknowledged = <String>[];
  bool removalsQueued = false;

  @override
  Future<void> recordUpsert(DevicePushEndpoint endpoint) async {
    upserts.add(endpoint);
  }

  @override
  Future<List<PushEndpointMutation>> readPendingMutations() async =>
      List<PushEndpointMutation>.of(pending);

  @override
  Future<void> acknowledgeMutation(String mutationId) async {
    acknowledged.add(mutationId);
    pending.removeWhere((entry) => entry.mutationId == mutationId);
  }

  @override
  Future<void> queueActiveEndpointRemovals() async {
    removalsQueued = true;
  }
}

final class _MemoryPushEndpointSecretStore implements PushEndpointSecretStore {
  final values = <String, String>{};

  @override
  Future<String?> read(String key) async => values[key];

  @override
  Future<void> write(String key, String value) async {
    values[key] = value;
  }

  @override
  Future<void> delete(String key) async {
    values.remove(key);
  }
}

final class _RecordingDevicePushEndpointWriter
    implements DevicePushEndpointWriter {
  final upserts = <DevicePushEndpoint>[];
  final removals = <DevicePushEndpoint>[];

  @override
  Future<void> upsert(DevicePushEndpoint endpoint) async {
    upserts.add(endpoint);
  }

  @override
  Future<void> remove(DevicePushEndpoint endpoint) async {
    removals.add(endpoint);
  }
}

final class _RecordingCloudOperationExecutor implements CloudOperationExecutor {
  final operationIds = <String>[];
  final payloads = <CloudOperationRequestPayload>[];

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    operationIds.add(operation.canonicalOperationId);
    payloads.add(requestEncoder());
    final response =
        operation.canonicalOperationId ==
            AppCloudOperationIds
                .notificationNotificationDeliveryJobAckIncomingCallPresentation
        ? <String, Object?>{
            'deliveryKey': 'delivery-1',
            'deviceId': 'device-1',
            'status': 'acknowledged',
            'raced': false,
            'acknowledgedAt': DateTime.utc(2026, 7, 20).toIso8601String(),
          }
        : <String, Object?>{
            'endpointRef': 'device-1:fcm',
            'deviceId': 'device-1',
            'endpointKind': 'fcm',
            'status': 'active',
            'version': 1,
            'aggregateVersion': 1,
            'idempotentReplay': false,
            'updatedAt': DateTime.utc(2026, 7, 20).toIso8601String(),
          };
    return responseDecoder(response);
  }
}
