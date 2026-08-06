// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-004
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/personal_assistant_stream_controller.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/presentation/assistant_message_bubble.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/presentation/personal_assistant_session_page.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/models/visit_models.dart';
import 'package:quwoquan_app/runtime/services/visit_recorder_service.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_cloud_contracts/assistant_runtime_enums.dart';

import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_facets_typed_double.dart';
import '../../../../../support/runtime/cloud_boundary_test_scope.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('personal assistant alpha fixture weather UI returns stream', (
    tester,
  ) async {
    const expectedFormFactor = String.fromEnvironment(
      'ASSISTANT_EXPECT_FORM_FACTOR',
      defaultValue: 'any',
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...sealedCloudBoundaryOverrides(),
          ...assistantFacetOverrides(InMemoryAssistantFacets()),
          visitRecorderServiceProvider.overrideWithValue(
            _NoopVisitRecorderService(),
          ),
        ],
        child: const MaterialApp(home: PersonalAssistantSessionPage()),
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
    final context = tester.element(find.byType(PersonalAssistantSessionPage));
    final state = ProviderScope.containerOf(
      context,
    ).read(personalAssistantStreamControllerProvider);
    expect(state.errorMessage, isEmpty);
    expect(state.answer, contains('找私助 mock stream 已接通'));
    expect(
      state.events.map((event) => event.eventType.wireName),
      containsAll(<String>[
        'run_started',
        'process_replace',
        'process_append',
        'answer_delta',
        'completed',
      ]),
    );
    expect(
      state.processSummary.lines.join('\n'),
      isNot(contains('nextAction')),
    );
    expect(state.transcript.length, greaterThanOrEqualTo(2));
    expect(state.transcript.first.runtimeType.toString(), contains('User'));
    expect(state.transcript.last.runtimeType.toString(), contains('Assistant'));
  });
}

final class _NoopVisitRecorderService extends VisitRecorderService {
  @override
  Future<void> recordVisit(VisitTarget target) async {}
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
    final context = tester.element(find.byType(PersonalAssistantSessionPage));
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
