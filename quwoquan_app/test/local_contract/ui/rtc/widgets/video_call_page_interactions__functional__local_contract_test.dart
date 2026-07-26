import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/rtc/models/call_participant.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';
import 'package:quwoquan_app/ui/rtc/pages/video_call_page.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_participants_provider.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_timer_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  testWidgets('视频页锁定隐藏危险控制并提供明确解锁', (tester) async {
    await tester.pumpWidget(_buildVideoPage());
    await tester.pump();

    expect(find.text(UITextConstants.callLockControls), findsOneWidget);
    expect(find.text(UITextConstants.callHangup), findsOneWidget);

    await tester.tap(find.text(UITextConstants.callLockControls));
    await tester.pump();

    expect(find.text(UITextConstants.callUnlockControls), findsOneWidget);
    expect(find.text(UITextConstants.callHangup), findsNothing);
    expect(find.text(UITextConstants.callInvite), findsNothing);

    await tester.tap(find.text(UITextConstants.callUnlockControls));
    await tester.pump();
    expect(find.text(UITextConstants.callHangup), findsOneWidget);
  });

  testWidgets('视频页显示共享状态、停止动作与超过六人的 +N', (tester) async {
    late _VideoPageSessionNotifier notifier;
    await tester.pumpWidget(
      _buildVideoPage(
        localScreenSharing: true,
        onSessionNotifierCreated: (value) => notifier = value,
      ),
    );
    await tester.pump();

    expect(find.text(UITextConstants.callScreenSharing), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('video-call-screen-share-surface')),
      findsOneWidget,
    );
    expect(
      find.text(UITextConstants.callScreenShareConnecting),
      findsOneWidget,
    );
    expect(find.text(UITextConstants.callStopScreenSharing), findsWidgets);
    expect(
      find.text(UITextConstants.callAdditionalParticipants(2)),
      findsOneWidget,
    );

    await tester.tap(
      find.byKey(const ValueKey('video-call-stop-screen-share')),
    );
    await tester.pump();
    expect(notifier.stopScreenShareCount, 1);
  });
}

Widget _buildVideoPage({
  bool localScreenSharing = false,
  ValueChanged<_VideoPageSessionNotifier>? onSessionNotifierCreated,
}) {
  return ProviderScope(
    overrides: [
      callSessionProvider.overrideWith(() {
        final notifier = _VideoPageSessionNotifier(
          localScreenSharing: localScreenSharing,
        );
        onSessionNotifierCreated?.call(notifier);
        return notifier;
      }),
      callParticipantsProvider.overrideWith(_VideoPageParticipantsNotifier.new),
      callTimerProvider.overrideWith(_RunningCallTimerNotifier.new),
    ],
    child: MaterialApp(
      builder: (context, child) => MediaQuery(
        data: const MediaQueryData(size: Size(1200, 900)),
        child: child!,
      ),
      home: const VideoCallPage(callId: 'call-video-page'),
    ),
  );
}

final class _VideoPageSessionNotifier extends CallSessionNotifier {
  _VideoPageSessionNotifier({required this.localScreenSharing});

  final bool localScreenSharing;
  int stopScreenShareCount = 0;

  @override
  CallSessionState build() {
    final now = DateTime.utc(2026, 7, 20);
    return CallSessionState(
      session: CallSessionDto(
        callId: 'call-video-page',
        callType: 'video',
        status: 'in_call',
        initiatorId: 'user-0',
        roomId: 'rtc-room-call-video-page',
        participantCount: 8,
        isScreenSharing: localScreenSharing,
        screenShareUserId: localScreenSharing ? 'user-0' : null,
        createdAt: now,
        updatedAt: now,
      ),
      status: CallStatus.inCall,
      callType: CallType.video,
      isCameraOn: true,
      isLocalScreenSharing: localScreenSharing,
    );
  }

  @override
  Future<void> stopScreenShare() async {
    stopScreenShareCount += 1;
  }
}

final class _VideoPageParticipantsNotifier extends CallParticipantsNotifier {
  @override
  CallParticipantsState build() {
    return CallParticipantsState(
      participants: List<CallParticipant>.generate(
        8,
        (index) => CallParticipant(
          userId: 'user-$index',
          displayName: 'User $index',
          status: ParticipantStatus.connected,
          isCameraOn: false,
          isLocal: index == 0,
        ),
      ),
      activeSpeakerId: 'user-1',
    );
  }
}

final class _RunningCallTimerNotifier extends CallTimerNotifier {
  @override
  CallTimerState build() => const CallTimerState(isRunning: true);
}
