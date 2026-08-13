library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/presentation/assistant_message_bubble.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/assistant_transcript_timeline_row.dart';

import 'patrol_test_support.dart';

Future<void> runAssistantProviderJourney(
  PatrolIntegrationTester $, {
  required String prompt,
  required String expectedAnswerFragment,
  String expectedCitationHost = '',
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
    final matchingAnswer = answers
        .where(
          (row) => _answerText(
            row,
          ).toLowerCase().contains(expectedAnswerFragment.toLowerCase()),
        )
        .where(
          (row) =>
              expectedCitationHost.isEmpty ||
              _hasCitationHost(row, expectedCitationHost),
        );
    if (answers.length > answerCountBefore && matchingAnswer.isNotEmpty) {
      return;
    }
  }
  fail(
    'assistant Provider journey did not produce a completed answer containing '
    '$expectedAnswerFragment with citation host $expectedCitationHost',
  );
}

bool _hasCitationHost(
  AssistantAnswerTranscriptRow row,
  String expectedCitationHost,
) {
  final host = expectedCitationHost.trim().toLowerCase();
  if (host.isEmpty) return true;
  return row.uiReferences.any(
    (citation) => <String>[
      citation.title,
      citation.source,
      citation.snippet,
      citation.externalUrl,
    ].any((value) => value.toLowerCase().contains(host)),
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
  final displayMarkdown = row.persisted.displayMarkdown.trim();
  return displayMarkdown.isNotEmpty ? displayMarkdown : row.content.trim();
}
