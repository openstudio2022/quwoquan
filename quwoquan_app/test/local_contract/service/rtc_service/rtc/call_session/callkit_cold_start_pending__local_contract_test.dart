// spec_ref: specs/feature-tree/chat-conversation/realtime-call/one-to-one-call/spec.md#gwt-003
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-004
//
// CallKit 冷启动 pending envelope happy path 契约：
// App 被后台推送唤起、Flutter 侧冷启动后，协调器 start 必须消费原生侧
// 暂存的 pending 来电 envelope：校验仍在 ringing → seed 来电首帧 →
// 复用原生已展示的系统来电面（不二次弹站内页）→ ACK 呈现事实。
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/platform/callkit_service.dart';
import 'package:quwoquan_app/runtime/platform/incoming_call_envelope.dart';
import 'package:quwoquan_app/runtime/platform/incoming_call_native_bridge.dart';
import 'package:quwoquan_app/runtime/platform/incoming_call_native_presenter.dart';
import 'package:quwoquan_app/runtime/platform/platform_capabilities.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart';
import 'package:quwoquan_app/runtime/platform/push_endpoint_gateway.dart';
import 'package:quwoquan_app/service/notification_service/notification_delivery/notification_delivery_job/application/public/incoming_call_presentation_acknowledger.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_session_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/incoming_call_coordinator.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/rtc_service/rtc/call_session/rtc_contract_test_builders.dart';

const String _pendingCallId = '44444444-4444-4444-8444-444444444444';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('冷启动消费 pending envelope：seed 来电 + 复用原生面 + ACK', () async {
    final router = GoRouter(
      routes: [
        GoRoute(
          path: '/',
          builder: (context, state) => const SizedBox.shrink(),
        ),
      ],
    );
    final nativeBridge = _PendingNativeBridge(
      IncomingCallEnvelope(
        callId: _pendingCallId,
        deliveryKey: 'delivery-cold-start',
        targetPersonaId: 'user-current',
        callType: 'audio',
        callerName: 'Cold Start Caller',
        sourceLabel: 'contacts',
        trustRelation: 'known',
        expiresAt: DateTime.now().toUtc().add(const Duration(minutes: 1)),
        callerPersonaId: 'user-caller',
      ),
    );
    final callKit = _RecordingCallKitService();
    final acknowledger = _RecordingAcknowledger();
    final container = ProviderContainer(
      overrides: [
        platformCapabilitiesProvider.overrideWithValue(
          CapabilityProfile.mobile,
        ),
        incomingCallRouterReaderProvider.overrideWithValue(() => router),
        incomingCallNativeBridgeProvider.overrideWithValue(nativeBridge),
        callKitServiceProvider.overrideWithValue(callKit),
        rtcCallQueryProvider.overrideWith(
          (ref, surface) => const _FixedCallQuery(
            callId: _pendingCallId,
            status: CallStatus.ringing,
          ),
        ),
        pushEndpointGatewayProvider.overrideWithValue(
          const UnsupportedPushEndpointGateway(),
        ),
        notificationDeliveryJobProcessCommandWriterProvider.overrideWithValue(
          acknowledger,
        ),
      ],
    );
    addTearDown(container.dispose);
    addTearDown(router.dispose);

    container.read(incomingCallCoordinatorProvider).start('user-current');
    for (var i = 0; i < 6; i++) {
      await Future<void>.delayed(Duration.zero);
    }

    final session = container.read(callSessionProvider);
    expect(session.session?.id, _pendingCallId, reason: '冷启动必须回填来电会话首帧');
    expect(session.status, CallStatus.ringing);
    expect(
      callKit.showIncomingCount,
      0,
      reason: '原生面已展示，Flutter 不得二次弹系统来电面',
    );
    expect(
      nativeBridge.endedCallIds,
      isEmpty,
      reason: 'ringing 中的 pending 来电不得被误关',
    );
    expect(acknowledger.receipts, hasLength(1), reason: '呈现事实必须 ACK');
    expect(acknowledger.receipts.single.deliveryKey, 'delivery-cold-start');
  });
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

final class _RecordingCallKitService extends CallKitService {
  int showIncomingCount = 0;

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
  Future<void> endCall(String callId) async {}
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
  dynamic noSuchMethod(Invocation invocation) =>
      super.noSuchMethod(invocation);
}

final class _RecordingAcknowledger
    implements NotificationDeliveryJobProcessCommandWriter {
  final receipts = <IncomingCallPresentationReceipt>[];

  @override
  Future<void> acknowledge(IncomingCallPresentationReceipt receipt) async {
    receipts.add(receipt);
  }
}
