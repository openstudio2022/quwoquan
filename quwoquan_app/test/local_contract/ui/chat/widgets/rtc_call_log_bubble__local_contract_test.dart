import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_card_attribute_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_card_dto.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/rtc_call_log_bubble.dart';

void main() {
  test('CallEnded card derives video duration summary', () {
    final presentation = RtcCallLogPresentation.fromCard(_card());

    expect(presentation.isVideo, isTrue);
    expect(
      presentation.summary,
      '${CallText.callSummaryDurationPrefix}01:05',
    );
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
}

ChatMessageCardDto _card({
  int durationMs = 65000,
  String endReason = 'normal',
}) => ChatMessageCardDto(
  kind: 'rtc_call_log',
  title: '',
  attributes: <ChatMessageCardAttributeDto>[
    ChatMessageCardAttributeDto(name: 'callId', value: 'call-1'),
    ChatMessageCardAttributeDto(name: 'callType', value: 'video'),
    ChatMessageCardAttributeDto(name: 'endReason', value: endReason),
    ChatMessageCardAttributeDto(name: 'durationMs', value: '$durationMs'),
  ],
);
