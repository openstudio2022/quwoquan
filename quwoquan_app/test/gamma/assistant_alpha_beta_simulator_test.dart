import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import '../common/assistant/assistant_scenario_fixtures.dart';
import 'package:quwoquan_app/ui/assistant/pages/personal_assistant_conversation_page.dart';
import 'package:quwoquan_app/ui/assistant/providers/personal_assistant_stream_controller.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('私人助理 alpha/beta 模拟器自动验证', (tester) async {
    final scenarioPack = await loadAssistantScenarioPackAsync();
    final runtimeEnv = CloudRuntimeConfig.appRuntimeEnv;
    final repositoryMode = expectedRepositoryModeForCurrentRuntimeEnv(
      scenarioPack,
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          if (runtimeEnv == 'alpha')
            assistantRepositoryProvider.overrideWithValue(
              ScenarioMockAssistantRepository(pack: scenarioPack),
            ),
        ],
        child: const MaterialApp(home: PersonalAssistantConversationPage()),
      ),
    );
    await _pumpFrames(tester);
    _expectScreenClass(tester);

    expect(find.text('找私助'), findsOneWidget);
    expect(find.byKey(TestKeys.assistantChatInputField), findsOneWidget);

    expect(_modeFromWidgetTree(tester), repositoryMode);
    const scenarioId = String.fromEnvironment('ASSISTANT_SCENARIO_ID');
    final allScenarios = scenarioPack.assistantTurnScenariosFor(runtimeEnv);
    final scenarios = scenarioId.trim().isEmpty
        ? allScenarios
        : allScenarios
              .where((scenario) => scenario.id == scenarioId)
              .toList(growable: false);
    expect(scenarios, isNotEmpty);

    switch (runtimeEnv) {
      case 'alpha':
      case 'beta':
        for (final scenario in scenarios) {
          await _sendAndExpect(
            tester,
            scenario: scenario,
            runtimeEnv: runtimeEnv,
          );
        }
      default:
        fail('APP_RUNTIME_ENV=$runtimeEnv 不属于本测试覆盖范围');
    }
  });
}

AppDataSourceMode _modeFromWidgetTree(WidgetTester tester) {
  final context = tester.element(find.byType(PersonalAssistantConversationPage));
  return ProviderScope.containerOf(context).read(appDataSourceModeProvider);
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
  required String runtimeEnv,
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

  final context = tester.element(find.byType(PersonalAssistantConversationPage));
  final streamState = ProviderScope.containerOf(
    context,
  ).read(personalAssistantStreamControllerProvider);
  expect(streamState.running, isFalse);
  expect(streamState.errorMessage, isEmpty);
  if (runtimeEnv == 'beta') {
    expect(streamState.answer, isNot(scenario.alphaMockStream.finalAnswer));
    expect(streamState.answer, isNot(contains('alpha mock')));
  }
  for (final fragment in scenario.answerFragmentsFor(runtimeEnv)) {
    expect(streamState.answer, contains(fragment));
  }
  for (final eventType in scenario.eventTypesFor(runtimeEnv)) {
    expect(
      streamState.events.any((event) => event.eventType == eventType),
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
  for (var i = 0; i < 240; i++) {
    await tester.pump(const Duration(milliseconds: 100));
    final context = tester.element(
      find.byType(PersonalAssistantConversationPage),
    );
    final streamState = ProviderScope.containerOf(
      context,
    ).read(personalAssistantStreamControllerProvider);
    if (!streamState.running && streamState.answer.isNotEmpty) {
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
