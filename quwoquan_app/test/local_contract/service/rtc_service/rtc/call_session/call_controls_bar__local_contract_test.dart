// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-007
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-004
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-003.t5
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/domain/call_state.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_session_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/call_controls_bar.dart';
import '../../../../../support/service/rtc_service/rtc/call_session/rtc_contract_test_builders.dart';

Widget _buildBar({
  CallType callType = CallType.video,
  VoidCallback? onHangup,
  VoidCallback? onInvite,
  bool interactionLocked = false,
  VoidCallback? onToggleInteractionLock,
  CallSessionNotifier Function()? callSessionNotifier,
}) {
  return ProviderScope(
    overrides: [
      callSessionProvider.overrideWith(
        callSessionNotifier ?? () => _ControlsCallSessionNotifier(callType),
      ),
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
            callType: callType,
            onHangup: onHangup,
            onInvite: onInvite,
            interactionLocked: interactionLocked,
            onToggleInteractionLock: onToggleInteractionLock,
            autoHide: false,
          ),
        ),
      ),
    ),
  );
}

void main() {
  // ──────────────────────────────────────────────────────────────────
  // 渲染契约
  // ──────────────────────────────────────────────────────────────────
  group('CallControlsBar — 渲染契约', () {
    testWidgets('video 模式渲染屏幕共享与防误触锁定入口', (tester) async {
      await tester.pumpWidget(
        _buildBar(callType: CallType.video, onToggleInteractionLock: () {}),
      );
      await tester.pump();

      expect(find.byType(CallControlsBar), findsOneWidget);

      expect(find.byIcon(CupertinoIcons.mic), findsOneWidget);
      expect(find.byIcon(CupertinoIcons.video_camera), findsOneWidget);
      expect(find.byIcon(CupertinoIcons.switch_camera), findsOneWidget);
      expect(find.text(CallText.callShareScreen), findsOneWidget);
      expect(find.text(CallText.callLockControls), findsOneWidget);
      expect(find.byIcon(CupertinoIcons.person_add), findsOneWidget);
      expect(find.byIcon(CupertinoIcons.speaker_1), findsOneWidget);
      expect(find.byIcon(CupertinoIcons.phone_down_fill), findsOneWidget);
    });

    testWidgets('voice 模式隐藏摄像头和翻转按钮', (tester) async {
      await tester.pumpWidget(_buildBar(callType: CallType.audio));
      await tester.pump();

      expect(find.byType(CallControlsBar), findsOneWidget);

      expect(find.byIcon(CupertinoIcons.switch_camera), findsNothing);

      expect(find.byIcon(CupertinoIcons.mic), findsOneWidget);
      expect(find.byIcon(CupertinoIcons.person_add), findsOneWidget);
      expect(find.byIcon(CupertinoIcons.phone_down_fill), findsOneWidget);
    });

    testWidgets('挂断按钮文本显示 "挂断"', (tester) async {
      await tester.pumpWidget(_buildBar());
      await tester.pump();

      expect(find.text(CallText.callHangup), findsOneWidget);
    });

    testWidgets('静音按钮默认显示 "静音"', (tester) async {
      await tester.pumpWidget(_buildBar());
      await tester.pump();

      expect(find.text(CallText.callMute), findsOneWidget);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 交互契约
  // ──────────────────────────────────────────────────────────────────
  group('CallControlsBar — 交互契约', () {
    testWidgets('点击挂断触发 onHangup 回调', (tester) async {
      var hangupCalled = false;
      await tester.pumpWidget(_buildBar(onHangup: () => hangupCalled = true));
      await tester.pump();

      await tester.tap(find.byIcon(CupertinoIcons.phone_down_fill));
      await tester.pump();

      expect(hangupCalled, isTrue);
    });

    testWidgets('点击邀请触发 onInvite 回调', (tester) async {
      var inviteCalled = false;
      await tester.pumpWidget(_buildBar(onInvite: () => inviteCalled = true));
      await tester.pump();

      await tester.tap(find.byIcon(CupertinoIcons.person_add));
      await tester.pump();

      expect(inviteCalled, isTrue);
    });

    testWidgets('video 模式下可见翻转按钮', (tester) async {
      await tester.pumpWidget(_buildBar(callType: CallType.video));
      await tester.pump();

      expect(find.byIcon(CupertinoIcons.switch_camera), findsOneWidget);
      expect(find.text(CallText.callFlipCamera), findsOneWidget);
    });

    testWidgets('屏幕共享入口调用 provider start/stop', (tester) async {
      final startNotifier = _ScreenShareCallSessionNotifier();
      await tester.pumpWidget(
        _buildBar(callSessionNotifier: () => startNotifier),
      );
      await tester.pump();
      await tester.tap(find.text(CallText.callShareScreen));
      await tester.pump();
      expect(startNotifier.startCount, 1);

      await tester.pumpWidget(const SizedBox.shrink());
      final stopNotifier = _ScreenShareCallSessionNotifier(localSharing: true);
      await tester.pumpWidget(
        _buildBar(callSessionNotifier: () => stopNotifier),
      );
      await tester.pump();
      await tester.tap(find.text(CallText.callStopScreenSharing));
      await tester.pump();
      expect(stopNotifier.stopCount, 1);
    });

    testWidgets('锁定时隐藏危险控制且仅保留明确解锁动作', (tester) async {
      var toggleCount = 0;
      await tester.pumpWidget(
        _buildBar(
          interactionLocked: true,
          onToggleInteractionLock: () => toggleCount++,
        ),
      );
      await tester.pump();

      expect(find.text(CallText.callUnlockControls), findsOneWidget);
      expect(find.text(CallText.callHangup), findsNothing);
      expect(find.text(CallText.callMute), findsNothing);
      expect(find.text(CallText.callInvite), findsNothing);
      expect(find.text(CallText.callShareScreen), findsNothing);

      await tester.tap(find.text(CallText.callUnlockControls));
      await tester.pump();
      expect(toggleCount, 1);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 错误态渲染
  // ──────────────────────────────────────────────────────────────────
  group('CallControlsBar — 错误态渲染', () {
    testWidgets('无 onHangup 回调时不崩溃', (tester) async {
      await tester.pumpWidget(_buildBar(onHangup: null));
      await tester.pump();

      expect(find.byType(CallControlsBar), findsOneWidget);

      await tester.tap(find.byIcon(CupertinoIcons.phone_down_fill));
      await tester.pump();
    });

    testWidgets('无 onInvite 回调时不崩溃', (tester) async {
      await tester.pumpWidget(_buildBar(onInvite: null));
      await tester.pump();

      await tester.tap(find.byIcon(CupertinoIcons.person_add));
      await tester.pump();

      expect(find.byType(CallControlsBar), findsOneWidget);
    });

    testWidgets('audio 模式不伪造未建模的通话中升级视频入口', (tester) async {
      await tester.pumpWidget(_buildBar(callType: CallType.audio));
      await tester.pump();

      expect(find.text(CallText.callEnableVideo), findsNothing);
    });
  });
}

final class _ControlsCallSessionNotifier extends CallSessionNotifier {
  _ControlsCallSessionNotifier(this.callType);

  final CallType callType;

  @override
  CallSessionState build() => CallSessionState(
    status: CallStatus.inCall,
    callType: callType,
    isCameraOn: callType.isVideo,
  );
}

final class _ScreenShareCallSessionNotifier extends CallSessionNotifier {
  _ScreenShareCallSessionNotifier({this.localSharing = false});

  final bool localSharing;
  int startCount = 0;
  int stopCount = 0;

  @override
  CallSessionState build() {
    final now = DateTime.utc(2026, 7, 20);
    return CallSessionState(
      session: buildCallSessionContract(
        id: 'call-controls',
        callType: CallType.video,
        status: CallStatus.inCall,
        initiatorId: 'user-a',
        roomId: 'rtc-room-call-controls',
        participantCount: 2,
        isScreenSharing: localSharing,
        screenShareUserId: localSharing ? 'user-a' : null,
        createdAt: now,
        updatedAt: now,
      ),
      status: CallStatus.inCall,
      callType: CallType.video,
      isCameraOn: true,
      isLocalScreenSharing: localSharing,
    );
  }

  @override
  Future<void> startScreenShare() async {
    startCount += 1;
  }

  @override
  Future<void> stopScreenShare() async {
    stopCount += 1;
  }
}
