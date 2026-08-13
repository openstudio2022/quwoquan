// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-004
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/one-to-one-call/spec.md#gwt-003
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/service/notification_service/notification_delivery/notification_delivery_job/application/public/incoming_call_presentation_acknowledger.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/incoming_call_coordinator.dart';
import 'package:quwoquan_app/service/user_service/account/device_registration/application/device_push_endpoint_writer.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/rtc_signal_events.dart';
import 'package:quwoquan_app/runtime/platform/incoming_call_envelope.dart';
import 'package:quwoquan_app/runtime/platform/incoming_call_native_bridge.dart';
import 'package:quwoquan_app/runtime/platform/incoming_call_native_presenter.dart';
import 'package:quwoquan_app/runtime/platform/callkit_service.dart';
import 'package:quwoquan_app/runtime/platform/platform_capabilities.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart';
import 'package:quwoquan_app/runtime/platform/push_endpoint_gateway.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/service/rtc_service/rtc/call_session/rtc_contract_test_builders.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // ──────────────────────────────────────────────────────────────────
  // 协调器装配：在不同平台能力位下都能解析（不依赖被删除的 goRouterProvider）。
  // ──────────────────────────────────────────────────────────────────
  group('IncomingCallCoordinator — 装配与能力位', () {
    ProviderContainer makeContainer(PlatformCapabilities caps) {
      final router = GoRouter(
        routes: [
          GoRoute(path: '/', builder: (context, state) => const _Empty()),
        ],
      );
      return ProviderContainer(
        overrides: [
          platformCapabilitiesProvider.overrideWithValue(caps),
          incomingCallRouterReaderProvider.overrideWithValue(() => router),
        ],
      );
    }

    test('mobile 能力位下可解析协调器', () {
      final container = makeContainer(CapabilityProfile.mobile);
      addTearDown(container.dispose);
      expect(
        container.read(incomingCallCoordinatorProvider),
        isA<IncomingCallCoordinator>(),
      );
    });

    test('web 能力位下可解析协调器', () {
      final container = makeContainer(CapabilityProfile.web);
      addTearDown(container.dispose);
      expect(
        container.read(incomingCallCoordinatorProvider),
        isA<IncomingCallCoordinator>(),
      );
    });

    test('ohos（无 RTC）能力位下可解析协调器（来电通道 unsupported）', () {
      final container = makeContainer(CapabilityProfile.ohos);
      addTearDown(container.dispose);
      final caps = container.read(platformCapabilitiesProvider);
      expect(resolveIncomingCallChannel(caps), IncomingCallChannel.unsupported);
      expect(
        container.read(incomingCallCoordinatorProvider),
        isA<IncomingCallCoordinator>(),
      );
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // pushDelivery 能力门控（R-XP1/R-XP5/R-XP9）：同一批行为契约由 profile 驱动。
  // mobile：登录后推送 endpoint 注册路径可达；web/ohos：结构化跳过注册与
  // 登出反注册，且全程无原生通道调用。
  // ──────────────────────────────────────────────────────────────────
  group('IncomingCallCoordinator — pushDelivery 能力门控', () {
    ProviderContainer makePushGatedContainer(
      PlatformCapabilities caps, {
      required PushEndpointGateway gateway,
      required DevicePushEndpointWriter writer,
    }) {
      final router = GoRouter(
        routes: [
          GoRoute(path: '/', builder: (context, state) => const _Empty()),
        ],
      );
      return ProviderContainer(
        overrides: [
          platformCapabilitiesProvider.overrideWithValue(caps),
          incomingCallRouterReaderProvider.overrideWithValue(() => router),
          callKitServiceProvider.overrideWithValue(_RecordingCallKitService()),
          pushEndpointGatewayProvider.overrideWithValue(gateway),
          devicePushEndpointWriterProvider.overrideWithValue(writer),
          notificationDeliveryJobProcessCommandWriterProvider.overrideWithValue(
            _RecordingPresentationAcknowledger(),
          ),
        ],
      );
    }

    PushEndpointMutation pendingUpsertMutation() => PushEndpointMutation(
      mutationId: 'mutation-upsert',
      kind: PushEndpointMutationKind.upsert,
      endpoint: DevicePushEndpoint(
        kind: PushEndpointKind.fcm,
        token: 'token-upsert',
      ),
      occurredAt: DateTime.utc(2026, 8, 12),
    );

    test('mobile：登录 start 后本地待同步 mutation 到达远端 writer 并 ack', () async {
      final gateway = _CountingPushEndpointGateway()
        ..pending.add(pendingUpsertMutation());
      final writer = _RecordingDevicePushEndpointWriter();
      final container = makePushGatedContainer(
        CapabilityProfile.mobile,
        gateway: gateway,
        writer: writer,
      );
      addTearDown(container.dispose);

      container.read(incomingCallCoordinatorProvider).start('user-current');
      await pumpEventQueue();

      expect(gateway.readPendingCalls, greaterThan(0));
      expect(writer.upserts.single.token, 'token-upsert');
      expect(gateway.acknowledged, <String>['mutation-upsert']);
    });

    for (final entry in <String, PlatformCapabilities>{
      'web': CapabilityProfile.web,
      'ohos': CapabilityProfile.ohos,
    }.entries) {
      test('${entry.key}：start/stop 全程结构化跳过注册且无原生通道调用', () async {
        final nativeCalls = <String>[];
        const nativeChannel = MethodChannel('quwoquan/rtc/incoming_call');
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
            .setMockMethodCallHandler(nativeChannel, (call) async {
              nativeCalls.add(call.method);
              return null;
            });
        addTearDown(() {
          TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
              .setMockMethodCallHandler(nativeChannel, null);
        });

        final gateway = _CountingPushEndpointGateway()
          ..pending.add(pendingUpsertMutation());
        final writer = _RecordingDevicePushEndpointWriter();
        final container = makePushGatedContainer(
          entry.value,
          gateway: gateway,
          writer: writer,
        );
        addTearDown(container.dispose);
        final coordinator = container.read(incomingCallCoordinatorProvider);

        coordinator.start('user-current');
        await pumpEventQueue();
        coordinator.stop();
        await pumpEventQueue();

        expect(gateway.readPendingCalls, 0);
        expect(gateway.queueRemovalCalls, 0);
        expect(writer.upserts, isEmpty);
        expect(writer.removals, isEmpty);
        expect(
          nativeCalls,
          isEmpty,
          reason: '能力关闭平台不得触达原生推送/来电通道（R-XP4/R-XP5）',
        );
      });
    }
  });

  // ──────────────────────────────────────────────────────────────────
  // 登录态唯一启停（与 shell 同源的纯函数决策）。
  // ──────────────────────────────────────────────────────────────────
  group('resolveIncomingCallSync — 启停幂等', () {
    test('登录 start / 登出 stop / 切换先停后启 / 同用户幂等', () {
      expect(
        resolveIncomingCallSync(boundUserId: '', nextUserId: 'u1').shouldStart,
        isTrue,
      );
      expect(
        resolveIncomingCallSync(boundUserId: 'u1', nextUserId: '').shouldStop,
        isTrue,
      );
      final swap = resolveIncomingCallSync(boundUserId: 'u1', nextUserId: 'u2');
      expect(swap.shouldStop && swap.shouldStart, isTrue);
      final same = resolveIncomingCallSync(boundUserId: 'u1', nextUserId: 'u1');
      expect(same.shouldStop || same.shouldStart, isFalse);
    });
  });

  test('迟到原生 Push 仅允许 initiated/ringing 状态继续展示', () {
    expect(isIncomingPresentationActiveStatus(CallStatus.initiated), isTrue);
    expect(isIncomingPresentationActiveStatus(CallStatus.ringing), isTrue);
    expect(isIncomingPresentationActiveStatus(CallStatus.connecting), isFalse);
    expect(isIncomingPresentationActiveStatus(CallStatus.inCall), isFalse);
    expect(isIncomingPresentationActiveStatus(CallStatus.ended), isFalse);
  });

  test('已结束通话的迟到原生 Push 会关闭 CallKit 且不发送展示 ACK', () async {
    final router = GoRouter(
      routes: [GoRoute(path: '/', builder: (context, state) => const _Empty())],
    );
    const callId = '33333333-3333-4333-8333-333333333333';
    final nativeBridge = _PendingNativeBridge(
      IncomingCallEnvelope(
        callId: callId,
        deliveryKey: 'delivery-late-ended',
        targetPersonaId: 'user-current',
        callType: 'audio',
        callerName: 'Caller',
        sourceLabel: 'conversation',
        trustRelation: 'known',
        expiresAt: DateTime.now().toUtc().add(const Duration(minutes: 1)),
      ),
    );
    final acknowledger = _RecordingPresentationAcknowledger();
    final container = ProviderContainer(
      overrides: [
        platformCapabilitiesProvider.overrideWithValue(
          CapabilityProfile.mobile,
        ),
        incomingCallRouterReaderProvider.overrideWithValue(() => router),
        incomingCallNativeBridgeProvider.overrideWithValue(nativeBridge),
        callKitServiceProvider.overrideWithValue(_RecordingCallKitService()),
        rtcCallQueryProvider.overrideWith(
          (ref, surface) =>
              const _FixedCallQuery(callId: callId, status: CallStatus.ended),
        ),
        pushEndpointGatewayProvider.overrideWithValue(
          _EmptyPushEndpointGateway(),
        ),
        notificationDeliveryJobProcessCommandWriterProvider.overrideWithValue(
          acknowledger,
        ),
      ],
    );
    addTearDown(container.dispose);

    container.read(incomingCallCoordinatorProvider).start('user-current');
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);

    expect(nativeBridge.endedCallIds, <String>[callId]);
    expect(acknowledger.receipts, isEmpty);
  });

  test('终态信号幂等关闭 CallKit，并压制乱序迟到 ringing', () async {
    final router = GoRouter(
      routes: [GoRoute(path: '/', builder: (context, state) => const _Empty())],
    );
    final callKit = _RecordingCallKitService();
    final container = ProviderContainer(
      overrides: [
        platformCapabilitiesProvider.overrideWithValue(
          CapabilityProfile.mobile,
        ),
        incomingCallRouterReaderProvider.overrideWithValue(() => router),
        callKitServiceProvider.overrideWithValue(callKit),
        pushEndpointGatewayProvider.overrideWithValue(
          _EmptyPushEndpointGateway(),
        ),
        userSettingsQueryReaderProvider.overrideWithValue(
          const _CallSettingsReader(),
        ),
        notificationDeliveryJobProcessCommandWriterProvider.overrideWithValue(
          _RecordingPresentationAcknowledger(),
        ),
      ],
    );
    addTearDown(container.dispose);
    final coordinator = container.read(incomingCallCoordinatorProvider);
    coordinator.start('user-current');
    final signals = container.read(rtcSignalEventBusProvider);

    signals.emitCanonicalFixture(<String, dynamic>{
      'type': 'call.ringing',
      'callId': '11111111-1111-4111-8111-111111111111',
      'actorId': 'user-caller',
      'payload': <String, dynamic>{
        'callId': '11111111-1111-4111-8111-111111111111',
        'eventId': 'event-ringing-1',
        'targetPersonaId': 'user-current',
        'callType': 'audio',
        'callerName': 'Caller',
        'sourceLabel': 'contacts',
        'trustRelation': 'known',
        'expiresAt': DateTime.now()
            .toUtc()
            .add(const Duration(minutes: 1))
            .toIso8601String(),
        'deliveryKey': 'delivery-1',
      },
    });
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);
    expect(callKit.showIncomingCount, 1);

    signals.emitCanonicalFixture(<String, dynamic>{
      'type': 'call.ended',
      'callId': '22222222-2222-4222-8222-222222222222',
      'payload': <String, dynamic>{
        'callId': '22222222-2222-4222-8222-222222222222',
        'endReason': 'cancelled',
      },
    });
    await Future<void>.delayed(Duration.zero);
    expect(callKit.endedCallIds, <String>[
      '22222222-2222-4222-8222-222222222222',
    ]);

    signals.emitCanonicalFixture(<String, dynamic>{
      'type': 'call.ringing',
      'callId': '22222222-2222-4222-8222-222222222222',
      'actorId': 'user-caller',
      'payload': <String, dynamic>{
        'callId': '22222222-2222-4222-8222-222222222222',
        'eventId': 'event-ringing-late',
        'targetPersonaId': 'user-current',
        'callType': 'audio',
        'callerName': 'Caller',
        'sourceLabel': 'contacts',
        'trustRelation': 'known',
        'expiresAt': DateTime.now()
            .toUtc()
            .add(const Duration(minutes: 1))
            .toIso8601String(),
        'deliveryKey': 'delivery-late',
      },
    });
    await Future<void>.delayed(Duration.zero);
    expect(callKit.showIncomingCount, 1);

    signals.emitCanonicalFixture(<String, dynamic>{
      'type': 'call.ended',
      'callId': '11111111-1111-4111-8111-111111111111',
      'payload': <String, dynamic>{
        'callId': '11111111-1111-4111-8111-111111111111',
        'endReason': 'cancelled',
      },
    });
    await Future<void>.delayed(Duration.zero);
    expect(callKit.endedCallIds, <String>[
      '22222222-2222-4222-8222-222222222222',
      '11111111-1111-4111-8111-111111111111',
    ]);
  });
}

class _Empty extends StatelessWidget {
  const _Empty();
  @override
  Widget build(BuildContext context) => const SizedBox.shrink();
}

final class _RecordingCallKitService extends CallKitService {
  int showIncomingCount = 0;
  final endedCallIds = <String>[];

  @override
  void startListening() {}

  @override
  void stopListening() {}

  @override
  Future<IncomingCallPresentationResult> showIncomingCall({
    required IncomingCallEnvelope envelope,
    String? ringtoneId,
  }) async {
    showIncomingCount += 1;
    return IncomingCallPresentationResult(
      presented: true,
      fullScreenAllowed: true,
    );
  }

  @override
  Future<void> endCall(String callId) async {
    endedCallIds.add(callId);
  }
}

final class _RecordingPresentationAcknowledger
    implements NotificationDeliveryJobProcessCommandWriter {
  final receipts = <IncomingCallPresentationReceipt>[];

  @override
  Future<void> acknowledge(IncomingCallPresentationReceipt receipt) async {
    receipts.add(receipt);
  }
}

final class _CountingPushEndpointGateway implements PushEndpointGateway {
  final pending = <PushEndpointMutation>[];
  final acknowledged = <String>[];
  int readPendingCalls = 0;
  int queueRemovalCalls = 0;

  @override
  Future<void> recordUpsert(DevicePushEndpoint endpoint) async {}

  @override
  Future<List<PushEndpointMutation>> readPendingMutations() async {
    readPendingCalls += 1;
    return List<PushEndpointMutation>.of(pending);
  }

  @override
  Future<void> acknowledgeMutation(String mutationId) async {
    acknowledged.add(mutationId);
    pending.removeWhere((mutation) => mutation.mutationId == mutationId);
  }

  @override
  Future<void> queueActiveEndpointRemovals() async {
    queueRemovalCalls += 1;
  }

  @override
  Future<void> purgeForTerminalAccountClosure() async {}
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

final class _EmptyPushEndpointGateway implements PushEndpointGateway {
  @override
  Future<void> acknowledgeMutation(String mutationId) async {}

  @override
  Future<void> queueActiveEndpointRemovals() async {}

  @override
  Future<void> purgeForTerminalAccountClosure() async {}

  @override
  Future<List<PushEndpointMutation>> readPendingMutations() async =>
      const <PushEndpointMutation>[];

  @override
  Future<void> recordUpsert(DevicePushEndpoint endpoint) async {}
}

final class _CallSettingsReader implements UserSettingsQueryReader {
  const _CallSettingsReader();

  @override
  Future<CallSettingsView> getCallSettings() async {
    return CallSettingsView(
      userId: 'user-current',
      allowCallerRingtoneOverride: false,
      enableCallVibration: true,
      enableGroupCallRing: true,
      version: 1,
      updatedAt: DateTime.utc(2026, 7, 20),
    );
  }

  @override
  Future<AppearanceSettingsView> getAppearanceSettings() =>
      throw UnimplementedError();

  @override
  Future<NotificationSettingsView> getNotificationSettings() =>
      throw UnimplementedError();

  @override
  Future<PrivacySettingsView> getPrivacySettings() =>
      throw UnimplementedError();
}

final class _FixedCallQuery implements CallQuery {
  const _FixedCallQuery({required this.callId, required this.status});

  final String callId;
  final CallStatus status;

  @override
  Future<CallSession> getCall(RtcGetCallQuery query) async {
    final timestamp = DateTime.utc(2026, 7, 20);
    return buildCallSessionContract(
      id: callId,
      callType: CallType.audio,
      status: status,
      initiatorId: 'user-caller',
      roomId: 'room-$callId',
      createdAt: timestamp,
      updatedAt: timestamp,
    );
  }

  @override
  Future<RtcCallHistoryPage> listCalls(RtcListCallsQuery query) =>
      throw UnimplementedError();
}

final class _PendingNativeBridge implements IncomingCallNativeBridge {
  _PendingNativeBridge(this.envelope);

  final IncomingCallEnvelope envelope;
  final endedCallIds = <String>[];

  @override
  Future<List<IncomingCallNativeAction>> consumePendingActions() async =>
      const <IncomingCallNativeAction>[];

  @override
  Future<void> endNativeCall(String callId) async {
    endedCallIds.add(callId);
  }

  @override
  Future<IncomingCallNativeCapability> readCapability() async =>
      const IncomingCallNativeCapability(
        nativeUiAvailable: true,
        fullScreenPresentationAllowed: true,
        backgroundPushConfigured: true,
      );

  @override
  Future<List<IncomingCallEnvelope>> readPendingEnvelopes() async =>
      <IncomingCallEnvelope>[envelope];

  @override
  Future<void> setFlutterReady(bool ready) async {}
}

extension on RtcSignalEventBus {
  void emitCanonicalFixture(Map<String, dynamic> event) {
    final payload = Map<String, Object?>.from(
      event['payload'] as Map<String, dynamic>,
    );
    emit(
      RealtimeEventEnvelope.fromWire(<String, Object?>{
        'type': event['type'],
        if (payload['eventId'] != null) 'eventId': payload['eventId'],
        'occurredAt': '2026-08-04T10:00:00Z',
        'payload': payload,
      }),
    );
  }
}
