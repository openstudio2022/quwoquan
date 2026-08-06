// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/run-stream-protocol/spec.md#gwt-001
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/personal_assistant_stream_controller.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/runtime_enums.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/presentation/personal_assistant_session_page.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/models/visit_models.dart';
import 'package:quwoquan_app/runtime/services/visit_recorder_service.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';

import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_facets_typed_double.dart';
import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_scenario_fixtures.dart';
import '../../../../../support/runtime/cloud_boundary_test_scope.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('私人助理 alpha fixture 模拟器自动验证', (tester) async {
    final scenarioPack = await loadAssistantScenarioPackAsync();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...sealedCloudBoundaryOverrides(),
          ...assistantFacetOverrides(
            ScenarioMockAssistantRepository(pack: scenarioPack),
          ),
          visitRecorderServiceProvider.overrideWithValue(
            _NoopVisitRecorderService(),
          ),
        ],
        child: const MaterialApp(home: PersonalAssistantSessionPage()),
      ),
    );
    await _pumpFrames(tester);
    _expectScreenClass(tester);

    expect(find.text('找私助'), findsOneWidget);
    expect(find.byKey(TestKeys.assistantChatInputField), findsOneWidget);

    const scenarioId = String.fromEnvironment('ASSISTANT_SCENARIO_ID');
    final allScenarios = scenarioPack.assistantTurnScenariosFor('alpha');
    final scenarios = scenarioId.trim().isEmpty
        ? allScenarios
        : allScenarios
              .where((scenario) => scenario.id == scenarioId)
              .toList(growable: false);
    expect(scenarios, isNotEmpty);

    for (final scenario in scenarios) {
      await _sendAndExpect(tester, scenario: scenario);
    }
  });
}

final class _NoopVisitRecorderService extends VisitRecorderService {
  @override
  Future<void> recordVisit(VisitTarget target) async {}
}

void _expectScreenClass(WidgetTester tester) {
  const expected = String.fromEnvironment(
    'VALIDATION_SCREEN_CLASS',
    defaultValue: 'any',
  );
  final logicalSize = tester.view.physicalSize / tester.view.devicePixelRatio;
  final shortestSide = logicalSize.shortestSide;
  final longestSide = logicalSize.longestSide;
  switch (expected) {
    case 'phone':
      expect(
        shortestSide,
        lessThan(700),
        reason: '手机模拟器应使用真实手机逻辑尺寸，当前为 $logicalSize',
      );
    case 'tablet':
      expect(
        longestSide,
        greaterThanOrEqualTo(700),
        reason: '平板模拟器应使用真实平板逻辑尺寸，当前为 $logicalSize',
      );
      expect(shortestSide, greaterThanOrEqualTo(500));
    case 'any':
      expect(shortestSide, greaterThan(0));
    default:
      fail('未知 VALIDATION_SCREEN_CLASS=$expected');
  }
}

Future<void> _sendAndExpect(
  WidgetTester tester, {
  required AssistantScenario scenario,
}) async {
  await tester.enterText(
    find.byKey(TestKeys.assistantChatInputField),
    scenario.question,
  );
  tester.testTextInput.updateEditingValue(
    TextEditingValue(
      text: scenario.question,
      selection: TextSelection.collapsed(offset: scenario.question.length),
    ),
  );
  await _pumpUntilSendButtonVisible(tester);
  await tester.tap(find.byKey(TestKeys.assistantSendButton));
  await _pumpUntilStreamSettled(tester);

  final context = tester.element(find.byType(PersonalAssistantSessionPage));
  final streamState = ProviderScope.containerOf(
    context,
  ).read(personalAssistantStreamControllerProvider);
  expect(streamState.running, isFalse);
  expect(streamState.errorMessage, isEmpty);
  for (final fragment in scenario.answerFragmentsFor('alpha')) {
    expect(streamState.answer, contains(fragment));
  }
  for (final eventType in scenario.eventTypesFor('alpha')) {
    expect(
      streamState.events.any((event) => event.eventType.wireName == eventType),
      isTrue,
      reason:
          '期望 stream event $eventType，实际为 '
          '${streamState.events.map((event) => event.eventType).toList()}',
    );
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
  const maxTicksOverride = int.fromEnvironment(
    'ASSISTANT_SMOKE_MAX_TICKS',
    defaultValue: 0,
  );
  const maxIdleTicksOverride = int.fromEnvironment(
    'ASSISTANT_SMOKE_MAX_IDLE_TICKS',
    defaultValue: 0,
  );
  final maxTicks = maxTicksOverride > 0 ? maxTicksOverride : 240;
  final maxIdleTicks = maxIdleTicksOverride > 0 ? maxIdleTicksOverride : 60;
  var lastSignature = '';
  var idleTicks = 0;
  for (var i = 0; i < maxTicks; i++) {
    await tester.pump(const Duration(milliseconds: 100));
    final context = tester.element(find.byType(PersonalAssistantSessionPage));
    final streamState = ProviderScope.containerOf(
      context,
    ).read(personalAssistantStreamControllerProvider);
    if (!streamState.running) {
      return;
    }
    final signature =
        '${streamState.answer.length}|'
        '${streamState.errorMessage.length}|'
        '${streamState.events.length}';
    if (signature == lastSignature) {
      idleTicks += 1;
      if (idleTicks >= maxIdleTicks) {
        throw TestFailure(
          'assistant alpha fixture simulator smoke 无进展超时: '
          'events=${streamState.events.length} '
          'answerLen=${streamState.answer.length}',
        );
      }
    } else {
      lastSignature = signature;
      idleTicks = 0;
    }
  }
  await tester.pump(const Duration(milliseconds: 100));
}

Future<void> _pumpFrames(WidgetTester tester, {int count = 12}) async {
  for (var i = 0; i < count; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}
