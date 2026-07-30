import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_stage_banner.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

void main() {
  // ──────────────────────────────────────────────────────────────────
  // S5 过程态派生：resolveCallStage 单一真相源，覆盖连接中/振铃/单人等待/
  // 通话中/重连/弱网/未接/已离开/已结束全过程态。
  // ──────────────────────────────────────────────────────────────────
  group('resolveCallStage — 过程态派生', () {
    test('initiated/connecting → 连接中', () {
      expect(
        resolveCallStage(status: CallStatus.initiated, connectedPeerCount: 0),
        CallStage.connecting,
      );
      expect(
        resolveCallStage(status: CallStatus.connecting, connectedPeerCount: 0),
        CallStage.connecting,
      );
    });

    test('ringing → 振铃', () {
      expect(
        resolveCallStage(status: CallStatus.ringing, connectedPeerCount: 0),
        CallStage.ringing,
      );
    });

    test('inCall 且无对端 → 单人等待', () {
      expect(
        resolveCallStage(status: CallStatus.inCall, connectedPeerCount: 0),
        CallStage.waitingPeer,
      );
    });

    test('inCall 有对端 → 通话中', () {
      expect(
        resolveCallStage(status: CallStatus.inCall, connectedPeerCount: 1),
        CallStage.inCall,
      );
    });

    test('inCall 重连优先于单人/弱网', () {
      expect(
        resolveCallStage(
          status: CallStatus.inCall,
          connectedPeerCount: 1,
          isReconnecting: true,
          isWeakNetwork: true,
        ),
        CallStage.reconnecting,
      );
    });

    test('inCall 有对端 + 弱网 → 弱网提示', () {
      expect(
        resolveCallStage(
          status: CallStatus.inCall,
          connectedPeerCount: 2,
          isWeakNetwork: true,
        ),
        CallStage.weakNetwork,
      );
    });

    test('ended + noAnswer/timeout/rejected → 对方未接听', () {
      for (final reason in [
        EndReason.noAnswer,
        EndReason.timeout,
        EndReason.rejected,
      ]) {
        expect(
          resolveCallStage(
            status: CallStatus.ended,
            connectedPeerCount: 0,
            endReason: reason,
          ),
          CallStage.peerNoAnswer,
          reason: reason.name,
        );
      }
    });

    test('ended + lastLeave → 对方已离开', () {
      expect(
        resolveCallStage(
          status: CallStatus.ended,
          connectedPeerCount: 0,
          endReason: EndReason.lastLeave,
        ),
        CallStage.peerLeft,
      );
    });

    test('ended + normal/null → 已结束', () {
      expect(
        resolveCallStage(
          status: CallStatus.ended,
          connectedPeerCount: 0,
          endReason: EndReason.normal,
        ),
        CallStage.ended,
      );
      expect(
        resolveCallStage(
          status: CallStatus.ended,
          connectedPeerCount: 0,
          endReason: null,
        ),
        CallStage.ended,
      );
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 过程态分类：进行中 / 终态，供页面决定控制可见性。
  // ──────────────────────────────────────────────────────────────────
  group('CallStage — 分类语义', () {
    test('进行态集合', () {
      for (final s in [
        CallStage.connecting,
        CallStage.ringing,
        CallStage.waitingPeer,
        CallStage.inCall,
        CallStage.reconnecting,
        CallStage.weakNetwork,
      ]) {
        expect(s.isOngoing, isTrue, reason: s.name);
        expect(s.isTerminal, isFalse, reason: s.name);
      }
    });

    test('终态集合', () {
      for (final s in [
        CallStage.peerNoAnswer,
        CallStage.peerLeft,
        CallStage.ended,
      ]) {
        expect(s.isTerminal, isTrue, reason: s.name);
        expect(s.isOngoing, isFalse, reason: s.name);
      }
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 横幅文案映射：统一来自 UITextConstants；通话中不显示横幅。
  // ──────────────────────────────────────────────────────────────────
  group('CallStageBanner — 文案与显隐', () {
    test('通话中不显示横幅', () {
      expect(CallStageBanner.shouldShow(CallStage.inCall), isFalse);
    });

    test('非通话中过程态均显示横幅', () {
      for (final s in CallStage.values) {
        if (s == CallStage.inCall) continue;
        expect(CallStageBanner.shouldShow(s), isTrue, reason: s.name);
      }
    });

    test('过程态文案映射到 UITextConstants', () {
      expect(
        CallStageBanner.messageFor(CallStage.connecting),
        CallText.callStageConnecting,
      );
      expect(
        CallStageBanner.messageFor(CallStage.ringing),
        CallText.callStageRinging,
      );
      expect(
        CallStageBanner.messageFor(CallStage.waitingPeer),
        CallText.callStageWaitingPeer,
      );
      expect(
        CallStageBanner.messageFor(CallStage.reconnecting),
        CallText.callStageReconnecting,
      );
      expect(
        CallStageBanner.messageFor(CallStage.weakNetwork),
        CallText.callStageWeakNetwork,
      );
      expect(
        CallStageBanner.messageFor(CallStage.peerNoAnswer),
        CallText.callStagePeerNoAnswer,
      );
      expect(
        CallStageBanner.messageFor(CallStage.peerLeft),
        CallText.callStagePeerLeft,
      );
      expect(
        CallStageBanner.messageFor(CallStage.ended),
        CallText.callStageEnded,
      );
    });

    testWidgets('结构化 failure 显示提示与恢复动作', (tester) async {
      var retryCount = 0;
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            callSessionProvider.overrideWith(_FailureCallSessionNotifier.new),
          ],
          child: MaterialApp(
            home: Scaffold(body: CallStageBanner(onRetry: () => retryCount++)),
          ),
        ),
      );

      expect(
        find.text(
          runtimeFailureDisplayMessage(_FailureCallSessionNotifier.failure),
        ),
        findsOneWidget,
      );
      expect(find.text(FoundationText.retry), findsOneWidget);
      await tester.tap(find.text(FoundationText.retry));
      expect(retryCount, 1);
    });
  });
}

final class _FailureCallSessionNotifier extends CallSessionNotifier {
  static final RuntimeFailureBase failure = RuntimeFailure.unknown(
    code: RuntimeFailureCodes.cloudSystemUnavailable,
  );

  @override
  CallSessionState build() => CallSessionState(failure: failure);
}
