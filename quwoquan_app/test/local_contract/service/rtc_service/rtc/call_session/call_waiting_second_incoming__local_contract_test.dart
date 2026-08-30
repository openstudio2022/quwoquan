// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-008
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-008.t1
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-008.t2
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-008.t3
//
// 通话中来电（call waiting）安全行为契约：
// 存在活跃通话时收到新 `call.ringing`，不得篡夺活跃 CallSession 状态机、
// 不得导航覆盖通话页；降级为第二来电轻提示并照常 ACK 呈现事实。
// 空闲时行为不变（seed 首帧 + 进入来电页）。
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/platform/platform_capabilities.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart';
import 'package:quwoquan_app/runtime/platform/push_endpoint_gateway.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/notification_service/notification_delivery/notification_delivery_job/application/public/incoming_call_presentation_acknowledger.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_session_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/incoming_call_coordinator.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/rtc_signal_events.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/second_incoming_call_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/rtc_service/rtc/call_session/rtc_contract_test_builders.dart';

const String _activeCallId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const String _secondCallId = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';

CallSession _activeSession() => buildCallSessionContract(
  id: _activeCallId,
  callType: CallType.audio,
  status: CallStatus.inCall,
  initiatorId: 'user-current',
  roomId: 'room-active',
  maxParticipants: 2,
  participantCount: 2,
  isScreenSharing: false,
  createdAt: DateTime.utc(2026, 8, 1),
  updatedAt: DateTime.utc(2026, 8, 1),
);

Map<String, dynamic> _ringingFixture(String callId) => <String, dynamic>{
  'type': 'call.ringing',
  'callId': callId,
  'actorId': 'user-second-caller',
  'payload': <String, dynamic>{
    'callId': callId,
    'eventId': 'event-$callId',
    'targetPersonaId': 'user-current',
    'callType': 'audio',
    'callerName': 'Second Caller',
    'sourceLabel': 'contacts',
    'trustRelation': 'known',
    'expiresAt': DateTime.now()
        .toUtc()
        .add(const Duration(minutes: 1))
        .toIso8601String(),
    'deliveryKey': 'delivery-$callId',
  },
};

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const incomingPageKey = Key('probe-incoming-call-page');

  (ProviderContainer, GoRouter, _RecordingAcknowledger) createHarness() {
    final router = GoRouter(
      routes: [
        GoRoute(path: '/', builder: (context, state) => const SizedBox()),
        GoRoute(
          path: AppRoutePaths.rtcIncomingPathTemplate.replaceFirst(
            '{callId}',
            ':callId',
          ),
          builder: (context, state) => const SizedBox(key: incomingPageKey),
        ),
      ],
    );
    final acknowledger = _RecordingAcknowledger();
    final container = ProviderContainer(
      overrides: [
        // inAppOnly 通道（web profile）：无 CallKit，站内呈现路径最短。
        platformCapabilitiesProvider.overrideWithValue(CapabilityProfile.web),
        incomingCallRouterReaderProvider.overrideWithValue(() => router),
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
    return (container, router, acknowledger);
  }

  Future<void> attachRouter(
    WidgetTester tester,
    ProviderContainer container,
    GoRouter router,
  ) async {
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pump();
  }

  testWidgets('通话中收到新来电：不篡夺活跃通话、不覆盖导航、轻提示并 ACK', (tester) async {
    final (container, router, acknowledger) = createHarness();
    await attachRouter(tester, container, router);
    container.read(incomingCallCoordinatorProvider).start('user-current');
    container
        .read(callSessionProvider.notifier)
        .loadFromSession(_activeSession());

    container
        .read(rtcSignalEventBusProvider)
        .emitCanonicalFixture(_ringingFixture(_secondCallId));
    await tester.pump();
    await tester.pump();

    final session = container.read(callSessionProvider);
    expect(
      session.session?.id,
      _activeCallId,
      reason: '活跃 CallSession 不得被第二来电篡夺',
    );
    expect(session.status, CallStatus.inCall);
    expect(find.byKey(incomingPageKey), findsNothing, reason: '不得导航到全屏来电页覆盖通话');
    expect(
      container.read(secondIncomingCallProvider)?.callId,
      _secondCallId,
      reason: '第二来电必须以轻提示状态暴露给通话页',
    );
    expect(acknowledger.receipts, hasLength(1), reason: '轻提示也是真实呈现，必须 ACK 记账');
  });

  testWidgets('空闲时来电行为不变：seed 首帧并进入来电页', (tester) async {
    final (container, router, acknowledger) = createHarness();
    await attachRouter(tester, container, router);
    container.read(incomingCallCoordinatorProvider).start('user-current');

    container
        .read(rtcSignalEventBusProvider)
        .emitCanonicalFixture(_ringingFixture(_secondCallId));
    await tester.pumpAndSettle();

    final session = container.read(callSessionProvider);
    expect(session.session?.id, _secondCallId);
    expect(session.status, CallStatus.ringing);
    expect(find.byKey(incomingPageKey), findsOneWidget, reason: '空闲时必须进入全屏来电页');
    expect(container.read(secondIncomingCallProvider), isNull);
    expect(acknowledger.receipts, hasLength(1));
  });

  testWidgets('同一通话的重复 ringing 不触发第二来电提示', (tester) async {
    final (container, router, _) = createHarness();
    await attachRouter(tester, container, router);
    container.read(incomingCallCoordinatorProvider).start('user-current');
    container
        .read(callSessionProvider.notifier)
        .loadFromSession(_activeSession());

    container
        .read(rtcSignalEventBusProvider)
        .emitCanonicalFixture(_ringingFixture(_activeCallId));
    await tester.pump();
    await tester.pump();

    expect(
      container.read(secondIncomingCallProvider),
      isNull,
      reason: '同一 callId 的迟到 ringing 不是第二来电',
    );
  });
}

final class _RecordingAcknowledger
    implements NotificationDeliveryJobProcessCommandWriter {
  final List<String> receipts = <String>[];

  @override
  Future<void> acknowledge(IncomingCallPresentationReceipt receipt) async {
    receipts.add(receipt.deliveryKey);
  }
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
