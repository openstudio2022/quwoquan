// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-006.t2
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-007
//
// 通话核心动作无障碍语义契约：
// 接听/拒接/挂断/静音/摄像头/翻转/共享/邀请/扬声器与 PiP 回流必须以
// button 语义节点暴露稳定 label，读屏用户可寻址并激活；不得只有裸
// GestureDetector + 视觉文本。
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/active_call_service.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_session_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/domain/call_state.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/call_controls_bar.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/incoming_call_page.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/pip_call_overlay.dart';

import '../../../../../support/service/rtc_service/rtc/call_session/call_session_typed_double.dart';
import '../../../../../support/service/rtc_service/rtc/call_session/rtc_contract_test_builders.dart';

class _VideoCallSessionNotifier extends CallSessionNotifier {
  @override
  CallSessionState build() {
    return CallSessionState(
      status: CallStatus.inCall,
      callType: CallType.video,
      isCameraOn: true,
      session: buildCallSessionContract(
        id: 'call-a11y',
        callType: CallType.video,
        status: CallStatus.inCall,
        initiatorId: 'user_a',
        roomId: 'room-a11y',
        maxParticipants: 8,
        participantCount: 2,
        isScreenSharing: false,
        createdAt: DateTime.utc(2026, 8, 1),
        updatedAt: DateTime.utc(2026, 8, 1),
      ),
    );
  }
}

void main() {
  testWidgets('通话控制条全部核心动作可经语义标签寻址', (tester) async {
    final handle = tester.ensureSemantics();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          callSessionProvider.overrideWith(_VideoCallSessionNotifier.new),
        ],
        child: MaterialApp(
          builder: (context, child) => MediaQuery(
            data: const MediaQueryData(size: Size(1200, 800)),
            child: child!,
          ),
          home: Scaffold(
            body: SizedBox(
              width: 1200,
              height: 200,
              child: CallControlsBar(
                callType: CallType.video,
                onHangup: () {},
                onInvite: () {},
                autoHide: false,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    for (final label in <String>[
      CallText.callMute,
      CallText.callCameraOff,
      CallText.callFlipCamera,
      CallText.callShareScreen,
      CallText.callInvite,
      CallText.callHangup,
    ]) {
      expect(
        find.bySemanticsLabel(label),
        findsOneWidget,
        reason: '控制动作「$label」必须可经语义标签寻址',
      );
    }
    handle.dispose();
  });

  testWidgets('来电页接听与拒接可经语义标签寻址', (tester) async {
    final handle = tester.ensureSemantics();
    final callSessions = CallSessionTypedDouble();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          rtcCallQueryProvider.overrideWith((ref, surface) => callSessions),
        ],
        child: const CupertinoApp(
          home: IncomingCallPage(
            callId: '11111111-1111-4111-8111-111111111111',
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.bySemanticsLabel(CallText.callAccept), findsOneWidget);
    expect(find.bySemanticsLabel(CallText.callReject), findsOneWidget);

    // 清理来电页首帧动画。
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 2));
    handle.dispose();
  });

  testWidgets('PiP 浮窗以通话中语义节点暴露回流入口', (tester) async {
    final handle = tester.ensureSemantics();
    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          home: Scaffold(
            body: Consumer(
              builder: (context, ref, _) {
                return Stack(
                  children: [
                    PipCallOverlay(onReturnToCall: () {}, onHangup: () {}),
                    Center(
                      child: CupertinoButton(
                        onPressed: () {
                          final notifier = ref.read(
                            activeCallProvider.notifier,
                          );
                          notifier.startCall(
                            callId: 'call-a11y-pip',
                            callType: 'audio',
                          );
                          notifier.enterPipMode();
                        },
                        child: const Text('activate'),
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('activate'));
    await tester.pump();

    expect(find.bySemanticsLabel(CallText.callOngoing), findsOneWidget);

    handle.dispose();
  });
}
