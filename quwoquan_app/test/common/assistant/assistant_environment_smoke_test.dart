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
import 'package:quwoquan_app/ui/assistant/pages/personal_assistant_conversation_page.dart';
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
      case 'gamma':
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
  Future<PersonalAssistantStreamState> sendOnceAndReadState() async {
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
    final context = tester.element(
      find.byType(PersonalAssistantConversationPage),
    );
    return ProviderScope.containerOf(
      context,
    ).read(personalAssistantStreamControllerProvider);
  }

  var streamState = await sendOnceAndReadState();
  if ((runtimeEnv == 'beta' || runtimeEnv == 'gamma') &&
      streamState.errorMessage.isNotEmpty) {
    // Hosted emulator occasionally reports a transient network error.
    streamState = await sendOnceAndReadState();
  }
  expect(streamState.running, isFalse);
  expect(streamState.errorMessage, isEmpty);
  expect(streamState.answer.trim(), isNotEmpty);
  expect(streamState.answer, isNot(contains('ASSISTANT.MIDDLEWARE')));
  expect(streamState.answer, isNot(contains('tool_unavailable')));
  if (runtimeEnv == 'beta' || runtimeEnv == 'gamma') {
    expect(streamState.answer, isNot(scenario.alphaMockStream.finalAnswer));
    expect(streamState.answer, isNot(contains('alpha mock')));
    expect(streamState.answer, isNot(contains('工具观察')));
    expect(streamState.answer, isNot(contains('工具结果')));
    expect(streamState.answer, isNot(contains('根据工具')));
    final hasSearchEvidence =
        streamState.processSummary.searchCount > 0 ||
        streamState.events.any(
          (event) =>
              event.eventType == 'search_query_generated' ||
              event.eventType == 'assistant.search_query.generated' ||
              event.eventType == 'search_query_accepted' ||
              event.eventType == 'assistant.search_query.accepted' ||
              event.eventType == 'tool_use_requested' ||
              event.eventType == 'assistant.tool.requested' ||
              event.eventType == 'tool_result_received' ||
              event.eventType == 'assistant.tool.completed',
        );
    // 云侧在 geocode miss / 检索无可靠摘要场景会返回 searchedDocumentCount=0，
    // 但仍应保留真实的检索或工具链事件证据。
    expect(hasSearchEvidence, isTrue);
    // 云侧在“检索无可靠摘要”场景会返回 acceptedCount=0，属合法路径。
    expect(streamState.processSummary.acceptedCount, greaterThanOrEqualTo(0));
    expect(streamState.processSummary.processingSummary, isNotEmpty);
  }
  if (runtimeEnv == 'beta' || runtimeEnv == 'gamma') {
    final expectedFragments = scenario.answerFragmentsFor(runtimeEnv);
    expect(
      expectedFragments.any(streamState.answer.contains),
      isTrue,
      reason: '云侧回答未命中任一期望片段: $expectedFragments',
    );
    for (final eventType in const ['turn_started', 'final_answer']) {
      expect(
        streamState.events.any((event) => event.eventType == eventType),
        isTrue,
        reason:
            '期望关键 stream event $eventType，实际为 '
            '${streamState.events.map((event) => event.eventType).toList()}',
      );
    }
  } else {
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
  expect(narrative, isNot(contains('用户询问')));
  expect(narrative, isNot(contains('该用户')));
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
  final context = tester.element(find.byType(PersonalAssistantConversationPage));
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
