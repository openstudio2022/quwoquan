import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_tab_page.dart';
import 'package:quwoquan_app/ui/assistant/providers/personal_assistant_stream_controller.dart';

import 'assistant_scenario_fixtures.dart';

void main() {
  const runtimeEnv = String.fromEnvironment(
    'APP_RUNTIME_ENV',
    defaultValue: 'alpha',
  );
  if (runtimeEnv == 'alpha') {
    TestWidgetsFlutterBinding.ensureInitialized();
  } else {
    IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  }
  _mockPathProviderForEnvironmentTest();

  testWidgets('私人助理 alpha/beta/gamma 环境自动验证', (tester) async {
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
        child: const MaterialApp(home: AssistantTabPage()),
      ),
    );
    await _pumpFrames(tester);
    _expectScreenClass(tester);

    expect(find.text('找小趣'), findsOneWidget);
    expect(find.text('找私助'), findsOneWidget);

    await tester.tap(find.text('找私助'));
    await _pumpFrames(tester);
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
      case 'gamma':
        for (final scenario in scenarios) {
          await tester.tap(find.text('找私助'));
          await _pumpFrames(tester, count: 2);
          await _sendAndExpect(
            tester,
            scenario: scenario,
            runtimeEnv: runtimeEnv,
          );
        }
      default:
        fail('APP_RUNTIME_ENV=$runtimeEnv 不属于本测试覆盖范围');
    }

    await tester.tap(find.text('找小趣'));
    await _pumpFrames(tester, count: 8);
    expect(find.byKey(TestKeys.assistantDialogPage), findsOneWidget);
  });
}

void _mockPathProviderForEnvironmentTest() {
  const channel = MethodChannel('plugins.flutter.io/path_provider');
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
      .setMockMethodCallHandler(channel, (call) async {
        final directory = Directory.systemTemp.createTempSync(
          'quwoquan-assistant-env-test-',
        );
        addTearDown(() {
          if (directory.existsSync()) {
            directory.deleteSync(recursive: true);
          }
        });
        switch (call.method) {
          case 'getApplicationDocumentsDirectory':
          case 'getApplicationSupportDirectory':
          case 'getTemporaryDirectory':
            return directory.path;
          default:
            return null;
        }
      });
}

AppDataSourceMode _modeFromWidgetTree(WidgetTester tester) {
  final context = tester.element(find.byType(AssistantTabPage));
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
  Future<void> sendOnce() async {
    await tester.ensureVisible(find.byKey(TestKeys.assistantChatInputField));
    await tester.pump(const Duration(milliseconds: 100));
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
    await _tapSend(tester, scenario.question);
    await _pumpUntilStreamSettled(tester);
  }

  await sendOnce();

  final context = tester.element(find.byType(AssistantTabPage));
  var streamState = ProviderScope.containerOf(
    context,
  ).read(personalAssistantStreamControllerProvider);
  if ((runtimeEnv == 'beta' || runtimeEnv == 'gamma') &&
      streamState.errorMessage.isNotEmpty) {
    // Hosted emulators may hit a transient gateway timeout on first attempt.
    await sendOnce();
    streamState = ProviderScope.containerOf(
      context,
    ).read(personalAssistantStreamControllerProvider);
  }
  expect(streamState.running, isFalse);
  expect(streamState.errorMessage, isEmpty);
  expect(streamState.answer, isNot(contains('ASSISTANT.MIDDLEWARE')));
  expect(streamState.answer, isNot(contains('tool_unavailable')));
  if (runtimeEnv == 'beta' || runtimeEnv == 'gamma') {
    expect(streamState.answer, isNot(scenario.alphaMockStream.finalAnswer));
    expect(streamState.answer, isNot(contains('alpha mock')));
    expect(streamState.answerGateOpen, isTrue);
    expect(streamState.processSummary.searchCount, greaterThan(0));
    expect(streamState.processSummary.acceptedCount, greaterThan(0));
    expect(streamState.processSummary.processingSummary, isNotEmpty);
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
  if (runtimeEnv == 'beta' || runtimeEnv == 'gamma') {
    _assertCloudPersonalAssistantNarrativeQuality(streamState);
  }
}

/// Beta/Gamma：禁止回归模板叙事泄漏，并要求模型交互事件下发（端上 debug 控制台可读）。
void _assertCloudPersonalAssistantNarrativeQuality(
  PersonalAssistantStreamState state,
) {
  final narrative = [
    state.processSummary.understandingSummary,
    state.processSummary.retrievalDesignNarrative,
    state.processSummary.processingSummary,
    state.answer,
  ].join('\n');
  expect(narrative, isNot(contains('\uFFFD')));
  expect(narrative, isNot(contains('我会先确认你的核心问题')));
  expect(narrative, isNot(contains('我会围绕')));
  expect(narrative, isNot(contains('nextAction')));
  expect(narrative, isNot(contains('reliable=')));
  expect(
    state.events.any((e) => e.eventType == 'assistant.model.interaction'),
    isTrue,
    reason: '期望存在 assistant.model.interaction，对应云侧模型请求/响应镜像事件',
  );
}

Future<void> _tapSend(WidgetTester tester, String question) async {
  for (var i = 0; i < 40; i++) {
    await tester.pump(const Duration(milliseconds: 100));
    await tester.ensureVisible(find.byKey(TestKeys.assistantChatInputField));
    final keyed = find.byKey(TestKeys.assistantSendButton);
    if (keyed.evaluate().isNotEmpty) {
      await tester.tap(keyed, warnIfMissed: false);
      return;
    }
    final textButtons = find.text('发送');
    if (textButtons.evaluate().isNotEmpty) {
      await tester.tap(textButtons.last, warnIfMissed: false);
      return;
    }
  }
  final context = tester.element(find.byType(AssistantTabPage));
  await ProviderScope.containerOf(
    context,
  ).read(personalAssistantStreamControllerProvider.notifier).send(question);
}

Future<void> _pumpUntilStreamSettled(WidgetTester tester) async {
  const runtimeEnv = String.fromEnvironment(
    'APP_RUNTIME_ENV',
    defaultValue: 'alpha',
  );
  // Hosted beta/gamma pipelines can be slower when emulators share network and
  // deterministic tool calls fan out; keep enough budget before declaring fail.
  final maxTicks = runtimeEnv == 'beta' || runtimeEnv == 'gamma' ? 1500 : 240;
  for (var i = 0; i < maxTicks; i++) {
    await tester.pump(const Duration(milliseconds: 100));
    final context = tester.element(find.byType(AssistantTabPage));
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
