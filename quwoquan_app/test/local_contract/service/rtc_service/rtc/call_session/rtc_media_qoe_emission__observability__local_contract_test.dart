import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/rtc_media_qoe_tracker.dart';
import 'package:quwoquan_app/runtime/errors/generated/rtc/rtc_errors.g.dart';

void main() {
  test('同一媒体尝试只生成一个低基数终态', () {
    var now = DateTime.utc(2026, 7, 20, 7);
    final tracker = RtcMediaQoeTracker(now: () => now);

    tracker.beginAttempt('call-qoe-1');
    now = now.add(const Duration(milliseconds: 1250));
    tracker.markMediaConnected();
    tracker.markReconnectStarted();
    tracker.updateNetworkQuality(RtcMediaNetworkQuality.good);

    final terminal = tracker.finish(
      callId: 'call-qoe-1',
      callType: 'video',
      participantCount: 2,
      abandonedBeforeAcceptance: false,
    );

    expect(terminal, isNotNull);
    expect(terminal!.result, RtcMediaQoeResult.completed);
    expect(terminal.connectTimeMs, 1250);
    expect(terminal.mediaConnected, isTrue);
    expect(terminal.reconnectCount, 1);
    expect(terminal.networkQuality, RtcMediaNetworkQuality.good);
    expect(terminal.disconnectReason, isNull);
    expect(
      tracker.finish(
        callId: 'call-qoe-1',
        callType: 'video',
        participantCount: 2,
        abandonedBeforeAcceptance: false,
      ),
      isNull,
    );
  });

  test('未接通放弃不进入接通率分母，异常断连进入 connection_lost', () {
    final abandoned = RtcMediaQoeTracker()..beginAttempt('call-abandoned');
    final abandonedTerminal = abandoned.finish(
      callId: 'call-abandoned',
      callType: 'audio',
      participantCount: 2,
      abandonedBeforeAcceptance: true,
    );
    expect(abandonedTerminal!.result, RtcMediaQoeResult.abandoned);
    expect(abandonedTerminal.mediaConnected, isFalse);
    expect(abandonedTerminal.failReasonCode, isNull);

    final locallyConnectedButUnanswered = RtcMediaQoeTracker()
      ..beginAttempt('call-unanswered')
      ..markMediaConnected();
    final unansweredTerminal = locallyConnectedButUnanswered.finish(
      callId: 'call-unanswered',
      callType: 'audio',
      participantCount: 2,
      abandonedBeforeAcceptance: true,
    );
    expect(unansweredTerminal!.result, RtcMediaQoeResult.abandoned);
    expect(unansweredTerminal.mediaConnected, isTrue);

    final interrupted = RtcMediaQoeTracker()
      ..beginAttempt('call-interrupted')
      ..markMediaConnected()
      ..markDisconnect(RtcMediaDisconnectReason.unexpectedDisconnect);
    final interruptedTerminal = interrupted.finish(
      callId: 'call-interrupted',
      callType: 'video',
      participantCount: 2,
      abandonedBeforeAcceptance: false,
    );
    expect(interruptedTerminal!.result, RtcMediaQoeResult.connectionLost);
    expect(
      interruptedTerminal.disconnectReason,
      RtcMediaDisconnectReason.unexpectedDisconnect,
    );

    final failed = RtcMediaQoeTracker()
      ..beginAttempt('call-failed')
      ..markDisconnect(RtcMediaDisconnectReason.connectFailed);
    final failedTerminal = failed.finish(
      callId: 'call-failed',
      callType: 'audio',
      participantCount: 2,
      abandonedBeforeAcceptance: false,
      failReasonCode: RtcErrorCode.mediaTransportUnavailable.code,
    );
    expect(failedTerminal!.result, RtcMediaQoeResult.connectFailed);
    expect(
      failedTerminal.failReasonCode,
      RtcErrorCode.mediaTransportUnavailable.code,
    );
  });

  test('旧 callId 终态不能污染新通话', () {
    final tracker = RtcMediaQoeTracker()
      ..beginAttempt('call-old')
      ..beginAttempt('call-new');

    expect(
      tracker.finish(
        callId: 'call-old',
        callType: 'audio',
        participantCount: 2,
        abandonedBeforeAcceptance: false,
      ),
      isNull,
    );
    expect(
      tracker.finish(
        callId: 'call-new',
        callType: 'audio',
        participantCount: 2,
        abandonedBeforeAcceptance: false,
      ),
      isNotNull,
    );
  });

  test('同一通话的连接重试成功后只上报最终成功事实', () {
    final tracker = RtcMediaQoeTracker()
      ..beginAttempt('call-retry')
      ..markDisconnect(RtcMediaDisconnectReason.connectFailed)
      ..beginAttempt('call-retry')
      ..markMediaConnected();

    final terminal = tracker.finish(
      callId: 'call-retry',
      callType: 'video',
      participantCount: 2,
      abandonedBeforeAcceptance: false,
    );

    expect(terminal!.result, RtcMediaQoeResult.completed);
    expect(terminal.mediaConnected, isTrue);
    expect(terminal.disconnectReason, isNull);
    expect(terminal.failReasonCode, isNull);
  });

  test('重连恢复清除临时断连原因但保留重连次数', () {
    final tracker = RtcMediaQoeTracker()
      ..beginAttempt('call-reconnect')
      ..markMediaConnected()
      ..markReconnectStarted()
      ..markDisconnect(RtcMediaDisconnectReason.unexpectedDisconnect)
      ..markReconnectRecovered();

    final terminal = tracker.finish(
      callId: 'call-reconnect',
      callType: 'audio',
      participantCount: 2,
      abandonedBeforeAcceptance: false,
    );

    expect(terminal!.result, RtcMediaQoeResult.completed);
    expect(terminal.reconnectCount, 1);
    expect(terminal.disconnectReason, isNull);
  });
}
