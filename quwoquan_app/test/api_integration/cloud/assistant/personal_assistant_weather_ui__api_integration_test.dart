import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/assistant/pages/personal_assistant_conversation_page.dart';
import 'package:quwoquan_app/ui/assistant/providers/personal_assistant_stream_controller.dart';
import 'package:quwoquan_app/ui/assistant/widgets/message/assistant_message_bubble.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('personal assistant UI weather query returns streamed answer', (
    tester,
  ) async {
    const runtimeEnv = String.fromEnvironment(
      'APP_RUNTIME_ENV',
      defaultValue: 'alpha',
    );
    const dataSource = String.fromEnvironment(
      'APP_DATA_SOURCE',
      defaultValue: 'mock',
    );
    const expectedFormFactor = String.fromEnvironment(
      'ASSISTANT_EXPECT_FORM_FACTOR',
      defaultValue: 'any',
    );
    await tester.pumpWidget(
      const ProviderScope(
        child: MaterialApp(home: PersonalAssistantConversationPage()),
      ),
    );
    await _pumpFrames(tester);
    _expectFormFactor(tester, expectedFormFactor);

    const question = String.fromEnvironment(
      'ASSISTANT_WEATHER_UI_QUESTION',
      defaultValue: '深圳天气',
    );
    await tester.enterText(
      find.byKey(TestKeys.assistantChatInputField),
      question,
    );
    tester.testTextInput.updateEditingValue(
      const TextEditingValue(
        text: question,
        selection: TextSelection.collapsed(offset: question.length),
      ),
    );
    await _pumpUntilSendButtonVisible(tester);
    await tester.tap(find.byKey(TestKeys.assistantSendButton));
    await _pumpUntilStreamSettled(tester);

    expect(find.byType(AssistantMessageBubble), findsWidgets);
    final context = tester.element(find.byType(PersonalAssistantConversationPage));
    final state = ProviderScope.containerOf(
      context,
    ).read(personalAssistantStreamControllerProvider);
    expect(state.errorMessage, isEmpty);
    if (runtimeEnv == 'beta' && dataSource == 'remote') {
      expect(state.answer, contains('天气助手'));
      expect(state.answer, isNot(contains('fallback_general_search')));
      expect(state.answer, isNot(contains('All Regions Argentina')));
      expect(
        state.events.any((event) {
          final payload = event.payload;
          return payload['skillId'] == 'weather' &&
              payload.containsKey('promptPolicy');
        }),
        isTrue,
        reason: '应在 beta stream 中选择 weather skill',
      );
    } else {
      expect(state.answer, contains('找私助 mock stream 已接通'));
      expect(
        state.events.map((event) => event.eventType),
        containsAll(<String>[
          'turn_started',
          'tool_use_requested',
          'tool_result_received',
          'final_answer',
        ]),
      );
    }
    expect(
      state.processSummary.lines.join('\n'),
      isNot(contains('nextAction')),
    );
    expect(state.transcript.length, greaterThanOrEqualTo(2));
    expect(state.transcript.first.runtimeType.toString(), contains('User'));
    expect(state.transcript.last.runtimeType.toString(), contains('Assistant'));
  });
}

void _expectFormFactor(WidgetTester tester, String expected) {
  final logicalSize = tester.view.physicalSize / tester.view.devicePixelRatio;
  expect(logicalSize.longestSide, greaterThanOrEqualTo(500));
  expect(logicalSize.shortestSide, greaterThanOrEqualTo(300));
  if (expected == 'tablet') {
    expect(logicalSize.longestSide, greaterThanOrEqualTo(700));
    expect(logicalSize.shortestSide, greaterThanOrEqualTo(500));
  }
  if (expected == 'phone') {
    expect(logicalSize.shortestSide, lessThan(500));
  }
}

Future<void> _pumpUntilSendButtonVisible(WidgetTester tester) async {
  for (var i = 0; i < 20; i++) {
    await tester.pump(const Duration(milliseconds: 100));
    if (find.byKey(TestKeys.assistantSendButton).evaluate().isNotEmpty) {
      return;
    }
  }
  expect(find.byKey(TestKeys.assistantSendButton), findsOneWidget);
}

Future<void> _pumpUntilStreamSettled(WidgetTester tester) async {
  for (var i = 0; i < 240; i++) {
    await tester.pump(const Duration(milliseconds: 100));
    final context = tester.element(
      find.byType(PersonalAssistantConversationPage),
    );
    final state = ProviderScope.containerOf(
      context,
    ).read(personalAssistantStreamControllerProvider);
    if (!state.running && state.answer.isNotEmpty) {
      return;
    }
  }
  await tester.pump(const Duration(milliseconds: 100));
}

Future<void> _pumpFrames(WidgetTester tester, {int count = 12}) async {
  for (var i = 0; i < count; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}
