import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/application/rtc/call_session/incoming_call_presentation_acknowledger.dart';
import 'package:quwoquan_app/cloud/rtc/incoming_call_coordinator.dart';
import 'package:quwoquan_app/cloud/rtc/rtc_signal_events.dart';
import 'package:quwoquan_app/core/platform/incoming_call_envelope.dart';
import 'package:quwoquan_app/core/platform/incoming_call_native_bridge.dart';
import 'package:quwoquan_app/core/platform/incoming_call_native_presenter.dart';
import 'package:quwoquan_app/core/platform/callkit_service.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:quwoquan_app/core/platform/platform_providers.dart';
import 'package:quwoquan_app/core/platform/push_endpoint_gateway.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
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
    expect(isIncomingPresentationActiveStatus('initiated'), isTrue);
    expect(isIncomingPresentationActiveStatus('ringing'), isTrue);
    expect(isIncomingPresentationActiveStatus('connecting'), isFalse);
    expect(isIncomingPresentationActiveStatus('in_call'), isFalse);
    expect(isIncomingPresentationActiveStatus('ended'), isFalse);
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
              const _FixedCallQuery(callId: callId, status: 'ended'),
        ),
        pushEndpointGatewayProvider.overrideWithValue(
          _EmptyPushEndpointGateway(),
        ),
        incomingCallPresentationAcknowledgerProvider.overrideWithValue(
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
        incomingCallPresentationAcknowledgerProvider.overrideWithValue(
          _RecordingPresentationAcknowledger(),
        ),
      ],
    );
    addTearDown(container.dispose);
    final coordinator = container.read(incomingCallCoordinatorProvider);
    coordinator.start('user-current');
    final signals = container.read(rtcSignalEventBusProvider);

    signals.emit(<String, dynamic>{
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

    signals.emit(<String, dynamic>{
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

    signals.emit(<String, dynamic>{
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

    signals.emit(<String, dynamic>{
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
    return const IncomingCallPresentationResult(
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
    implements IncomingCallPresentationAcknowledger {
  final receipts = <IncomingCallPresentationReceipt>[];

  @override
  Future<void> acknowledge(IncomingCallPresentationReceipt receipt) async {
    receipts.add(receipt);
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
  final String status;

  @override
  Future<CallSessionDto> getCall(RtcGetCallQuery query) async {
    final timestamp = DateTime.utc(2026, 7, 20);
    return CallSessionDto(
      callId: callId,
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
