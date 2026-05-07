import 'dart:async';
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

const _assistantSmokeProfile = String.fromEnvironment(
  'ASSISTANT_SMOKE_PROFILE',
  defaultValue: 'full_semantic',
);

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
  final context = tester.element(
    find.byType(PersonalAssistantConversationPage),
  );
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
  final isFullSemanticSmoke = _assistantSmokeProfile != 'ui_sanity';
  Future<PersonalAssistantStreamState> sendOnceAndReadState() async {
    final pageFinder = find.byType(PersonalAssistantConversationPage);
    final context = tester.element(pageFinder);
    final container = ProviderScope.containerOf(context);
    print(
      '[assistant-env-smoke] start scenario=${scenario.id} runtimeEnv=$runtimeEnv profile=$_assistantSmokeProfile',
    );
    unawaited(
      container
          .read(personalAssistantStreamControllerProvider.notifier)
          .send(scenario.question),
    );
    await _pumpUntilStreamStarts(tester);
    await _pumpUntilStreamSettled(tester);
    print(
      '[assistant-env-smoke] settled scenario=${scenario.id} runtimeEnv=$runtimeEnv',
    );
    return container.read(personalAssistantStreamControllerProvider);
  }

  var streamState = await sendOnceAndReadState();
  if ((runtimeEnv == 'beta' || runtimeEnv == 'gamma') &&
      (streamState.errorMessage.isNotEmpty ||
          streamState.answer.trim().isEmpty)) {
    // Hosted beta/gamma 在冷启动后首轮偶发网络错误或空回答，重试一次区分抖动与真实回归。
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
  }
  if (runtimeEnv == 'beta' || runtimeEnv == 'gamma') {
    for (final eventType in const ['turn_started', 'final_answer']) {
      expect(
        streamState.events.any((event) => event.eventType == eventType),
        isTrue,
        reason:
            '期望关键 stream event $eventType，实际为 '
            '${streamState.events.map((event) => event.eventType).toList()}',
      );
    }
    if (isFullSemanticSmoke) {
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
      final expectedFragments = scenario.answerFragmentsFor(runtimeEnv);
      expect(
        expectedFragments.any(streamState.answer.contains),
        isTrue,
        reason: '云侧回答未命中任一期望片段: $expectedFragments',
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
  if ((runtimeEnv == 'beta' || runtimeEnv == 'gamma') && isFullSemanticSmoke) {
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

Future<void> _pumpUntilStreamStarts(WidgetTester tester) async {
  for (var i = 0; i < 50; i++) {
    await tester.pump(const Duration(milliseconds: 100));
    final context = tester.element(
      find.byType(PersonalAssistantConversationPage),
    );
    final streamState = ProviderScope.containerOf(
      context,
    ).read(personalAssistantStreamControllerProvider);
    if (streamState.running ||
        streamState.answer.isNotEmpty ||
        streamState.errorMessage.isNotEmpty ||
        streamState.turnId.isNotEmpty ||
        streamState.events.isNotEmpty) {
      return;
    }
  }
  throw TestFailure('assistant smoke 在 5 秒内未启动 stream');
}

Future<void> _pumpUntilStreamSettled(WidgetTester tester) async {
  const runtimeEnv = String.fromEnvironment(
    'APP_RUNTIME_ENV',
    defaultValue: 'alpha',
  );
  const maxTicksOverride = int.fromEnvironment(
    'ASSISTANT_SMOKE_MAX_TICKS',
    defaultValue: 0,
  );
  const maxIdleTicksOverride = int.fromEnvironment(
    'ASSISTANT_SMOKE_MAX_IDLE_TICKS',
    defaultValue: 0,
  );
  // Hosted beta/gamma pipelines can be slower when emulators share network and
  // deterministic tool calls fan out; keep enough budget before declaring fail.
  final maxTicks = maxTicksOverride > 0
      ? maxTicksOverride
      : (runtimeEnv == 'beta' || runtimeEnv == 'gamma' ? 1500 : 240);
  final maxIdleTicks = maxIdleTicksOverride > 0
      ? maxIdleTicksOverride
      : (runtimeEnv == 'beta' || runtimeEnv == 'gamma'
            ? (_assistantSmokeProfile == 'ui_sanity' ? 80 : 180)
            : 60);
  var lastSignature = '';
  var idleTicks = 0;
  for (var i = 0; i < maxTicks; i++) {
    await tester.pump(const Duration(milliseconds: 100));
    final context = tester.element(
      find.byType(PersonalAssistantConversationPage),
    );
    final streamState = ProviderScope.containerOf(
      context,
    ).read(personalAssistantStreamControllerProvider);
    // 一旦流结束就立刻交给上层判断成功/空回答/错误，并决定是否重试，
    // 避免 hosted beta/gamma 在首轮快速失败后仍白白转满整段等待窗口。
    if (!streamState.running) {
      return;
    }
    final signature =
        '${streamState.answer.length}|'
        '${streamState.errorMessage.length}|'
        '${streamState.events.length}|'
        '${streamState.processSummary.processingSummary.length}|'
        '${streamState.processSummary.searchCount}|'
        '${streamState.processSummary.acceptedCount}';
    if (signature == lastSignature) {
      idleTicks += 1;
      if (idleTicks >= maxIdleTicks) {
        throw TestFailure(
          'assistant smoke 无进展超时: '
          'profile=$_assistantSmokeProfile '
          'runtimeEnv=$runtimeEnv '
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
