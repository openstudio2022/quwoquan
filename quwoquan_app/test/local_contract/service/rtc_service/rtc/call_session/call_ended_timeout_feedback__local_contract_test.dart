// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-014
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-014.t1
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-014.t2
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-014.t3
//
// 超时/未接终态反馈契约：
// 呼出页/来电页在 ended 跳离前必须给出可感知的终态反馈——呼出方
// no_answer/timeout 提示「无人接听」、rejected 提示「对方已拒绝」；
// 来电方 no_answer/timeout 提示「未接听」；正常挂断不打扰。
// 历史缺陷：跳离竞态吞掉 CallStageBanner，用户看不到终态原因。
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_session_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/rtc_signal_events.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/incoming_call_page.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/outgoing_call_page.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/platform/rtc_room_service.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/rtc_service/rtc/call_session/call_session_typed_double.dart';
import '../../../../../support/service/rtc_service/rtc/call_session/rtc_contract_test_builders.dart';

const String _callId = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';

CallSession _ringingSession() => buildCallSessionContract(
  id: _callId,
  callType: CallType.audio,
  status: CallStatus.ringing,
  initiatorId: 'user-caller',
  roomId: 'room-feedback',
  maxParticipants: 2,
  participantCount: 1,
  isScreenSharing: false,
  createdAt: DateTime.utc(2026, 8, 1),
  updatedAt: DateTime.utc(2026, 8, 1),
);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Future<(ProviderContainer, GoRouter)> pumpPage(
    WidgetTester tester, {
    required Widget page,
  }) async {
    final callSessions = CallSessionTypedDouble();
    final container = ProviderContainer(
      overrides: [
        rtcRoomServiceProvider.overrideWithValue(_NoopRtcRoomService()),
        rtcCallQueryProvider.overrideWith((ref, surface) => callSessions),
        rtcCallLifecycleCommandWriterProvider.overrideWith(
          (ref, surface) => callSessions,
        ),
        rtcCallParticipantCommandWriterProvider.overrideWith(
          (ref, surface) => callSessions,
        ),
        rtcCallMediaControlWriterProvider.overrideWith(
          (ref, surface) => callSessions,
        ),
      ],
    );
    addTearDown(container.dispose);
    final router = GoRouter(
      routes: [
        GoRoute(path: '/', builder: (context, state) => page),
        GoRoute(
          path: AppRoutePaths.chat,
          builder: (context, state) => const SizedBox(),
        ),
      ],
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pump();
    container
        .read(callSessionProvider.notifier)
        .loadFromSession(_ringingSession());
    await tester.pump();
    return (container, router);
  }

  void emitEnded(ProviderContainer container, String endReason) {
    container
        .read(rtcSignalEventBusProvider)
        .emit(
          RealtimeEventEnvelope.fromWire(<String, Object?>{
            'type': 'call.ended',
            'occurredAt': '2026-08-04T10:00:00Z',
            'payload': <String, Object?>{
              'callId': _callId,
              'endReason': endReason,
            },
          }),
        );
  }

  Future<void> settleToast(WidgetTester tester) async {
    // 让 toast 展示并走完 3 秒自动消退，清理 pending timer。
    await tester.pump();
    await tester.pump();
    await tester.pump(const Duration(seconds: 4));
    await tester.pumpAndSettle();
  }

  testWidgets('呼出方 no_answer 收尾提示「无人接听」', (tester) async {
    final (container, _) = await pumpPage(
      tester,
      page: const OutgoingCallPage(callId: _callId),
    );

    emitEnded(container, 'no_answer');
    await tester.pump();
    await tester.pump();

    expect(
      find.text(CallText.callSummaryNoAnswer),
      findsOneWidget,
      reason: '超时未接的终态必须在跳离前可感知',
    );
    await settleToast(tester);
  });

  testWidgets('呼出方 rejected 收尾提示「对方已拒绝」', (tester) async {
    final (container, _) = await pumpPage(
      tester,
      page: const OutgoingCallPage(callId: _callId),
    );

    emitEnded(container, 'rejected');
    await tester.pump();
    await tester.pump();

    expect(find.text(CallText.callSummaryRejected), findsOneWidget);
    await settleToast(tester);
  });

  testWidgets('呼出方正常收尾不打扰', (tester) async {
    final (container, _) = await pumpPage(
      tester,
      page: const OutgoingCallPage(callId: _callId),
    );

    emitEnded(container, 'cancelled');
    await tester.pump();
    await tester.pump();

    expect(find.text(CallText.callSummaryNoAnswer), findsNothing);
    expect(find.text(CallText.callSummaryRejected), findsNothing);
    await settleToast(tester);
  });

  testWidgets('来电方 no_answer 收尾提示「未接听」', (tester) async {
    final (container, _) = await pumpPage(
      tester,
      page: const IncomingCallPage(callId: _callId),
    );

    emitEnded(container, 'no_answer');
    await tester.pump();
    await tester.pump();

    expect(
      find.text(CallText.callSummaryMissed),
      findsOneWidget,
      reason: '来电超时未接必须在跳离前可感知',
    );
    await settleToast(tester);
  });
}

final class _NoopRtcRoomService extends RtcRoomService {
  @override
  Future<void> connect({
    required String accessToken,
    bool enableVideo = false,
    bool enableAudio = true,
  }) async {}

  @override
  Future<void> disconnect() async {}

  @override
  void dispose() {}
}
