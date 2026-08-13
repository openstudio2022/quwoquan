// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-002.t3
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/rtc_call_log_bubble.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

void main() {
  test('CallEnded card derives video duration summary', () {
    final presentation = RtcCallLogPresentation.fromCard(_card());

    expect(presentation.isVideo, isTrue);
    expect(presentation.summary, '${CallText.callSummaryDurationPrefix}01:05');
  });

  testWidgets('call log bubble renders semantic CTA and invokes redial', (
    tester,
  ) async {
    var redialCount = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: RtcCallLogBubble(card: _card(), onRedial: () => redialCount++),
        ),
      ),
    );

    expect(find.text(CallText.callVideo), findsOneWidget);
    expect(find.text(CallText.callRedial), findsOneWidget);
    await tester.tap(find.text(CallText.callRedial));
    expect(redialCount, 1);
  });

  test('zero duration maps no_answer to no-answer summary', () {
    final presentation = RtcCallLogPresentation.fromCard(
      _card(durationMs: 0, endReason: 'no_answer'),
    );
    expect(presentation.summary, CallText.callSummaryNoAnswer);
  });

  test('missing enum attributes and retired EndReason aliases fail closed', () {
    expect(() => RtcCallLogPresentation.fromCard(null), throwsFormatException);
    for (final retired in <String>[
      'completed',
      'busy',
      'initiator_hangup',
      'network_error',
      'unknown',
    ]) {
      expect(
        () => RtcCallLogPresentation.fromCard(_card(endReason: retired)),
        throwsFormatException,
      );
    }
  });
}

MessageCard _card({int durationMs = 65000, String endReason = 'normal'}) =>
    MessageCard(
      kind: MessageCardKind.rtcCallLog,
      title: '',
      attributes: <MessageCardAttribute>[
        MessageCardAttribute(name: 'callId', value: 'call-1'),
        MessageCardAttribute(name: 'callType', value: 'video'),
        MessageCardAttribute(name: 'endReason', value: endReason),
        MessageCardAttribute(name: 'durationMs', value: '$durationMs'),
      ],
    );
