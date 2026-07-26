library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/assistant/transcript/row/assistant_transcript_timeline_row.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/assistant/widgets/message/assistant_message_bubble.dart';

Future<void> runAssistantProviderJourney(
  PatrolIntegrationTester $, {
  required String prompt,
  required String expectedAnswerFragment,
}) async {
  await launchPatrolAppOnce($);
  await patrolGoTo($, AppRoutePaths.assistant);

  final input = find.byKey(TestKeys.assistantChatInputField);
  await $(input).waitUntilVisible(timeout: const Duration(seconds: 30));
  final answerCountBefore = _completedAnswers().length;
  await $(input).enterText(prompt);
  await $(find.byKey(TestKeys.assistantSendButton)).tap();

  final deadline = DateTime.now().add(const Duration(seconds: 120));
  while (DateTime.now().isBefore(deadline)) {
    await $.pump(const Duration(milliseconds: 500));
    final answers = _completedAnswers();
    if (answers.length > answerCountBefore &&
        answers.any(
          (row) => _answerText(
            row,
          ).toLowerCase().contains(expectedAnswerFragment.toLowerCase()),
        )) {
      return;
    }
  }
  fail(
    'assistant Provider journey did not produce a completed answer containing '
    '$expectedAnswerFragment',
  );
}

List<AssistantAnswerTranscriptRow> _completedAnswers() {
  return find
      .byType(AssistantMessageBubble)
      .evaluate()
      .map((element) => element.widget)
      .whereType<AssistantMessageBubble>()
      .map((bubble) => bubble.transcriptRow)
      .whereType<AssistantAnswerTranscriptRow>()
      .where((row) => !row.streaming && _answerText(row).trim().isNotEmpty)
      .toList(growable: false);
}

String _answerText(AssistantAnswerTranscriptRow row) {
  final finalAnswer = row.streamFinalAnswer.trim();
  return finalAnswer.isNotEmpty ? finalAnswer : row.content.trim();
}
