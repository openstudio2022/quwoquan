import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:quwoquan_app/assistant/transcript/persisted_timeline/persisted_timeline_turn_codec.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import '../common/assistant/assistant_eval_scenario_fixtures.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_tab_page.dart';
import 'package:quwoquan_app/ui/assistant/providers/personal_assistant_stream_controller.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('21 skill alpha/beta comparison evidence collector', (
    tester,
  ) async {
    _installPathProviderMock();
    final scenarioPack = loadAssistantEvalScenarioPack();
    final runtimeEnv = CloudRuntimeConfig.appRuntimeEnv;
    final scenarios = scenarioPack.assistantTurnScenariosFor(runtimeEnv);
    expect(scenarios, hasLength(21));
    expect(scenarioPack.qualityStandards, hasLength(21));

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          if (runtimeEnv == 'alpha')
            assistantRepositoryProvider.overrideWithValue(
              ScenarioEvalMockAssistantRepository(pack: scenarioPack),
            ),
        ],
        child: const MaterialApp(home: AssistantTabPage()),
      ),
    );
    await _pumpFrames(tester);
    _expectScreenClass(tester);

    await tester.tap(find.text('找私助'));
    await _pumpFrames(tester);
    expect(find.byKey(TestKeys.assistantChatInputField), findsOneWidget);

    final container = ProviderScope.containerOf(
      tester.element(find.byType(AssistantTabPage)),
    );
    final mode = container.read(appDataSourceModeProvider);

    for (final scenario in scenarios) {
      final started = DateTime.now();
      await container
          .read(personalAssistantStreamControllerProvider.notifier)
          .send(scenario.question);
      await _pumpUntilStreamSettled(tester);

      final context = tester.element(find.byType(AssistantTabPage));
      final state = ProviderScope.containerOf(
        context,
      ).read(personalAssistantStreamControllerProvider);
      final durationMs = DateTime.now().difference(started).inMilliseconds;
      final eventTypes = state.events
          .map((event) => event.eventType)
          .toList(growable: false);
      final selectedSkillIds = <String>{
        for (final event in state.events)
          if (_looksLikeSkillSelection(event.payload))
            (event.payload['skillId'] ?? '').toString(),
      }..remove('');
      final toolNames = <String>{
        for (final event in state.events) _toolNameForEvent(event.payload),
      }..remove('');
      final transcript = state.transcript
          .map(PersistedTimelineTurnCodec.encode)
          .toList(growable: false);
      final expectedAnswerFragments = runtimeEnv == 'alpha'
          ? scenario.expectedAnswerFragments
          : (scenario.remoteExpectations.answerFragments.isNotEmpty
                ? scenario.remoteExpectations.answerFragments
                : scenario.expectedAnswerFragments);
      final expectedEventTypes = runtimeEnv == 'alpha'
          ? scenario.expectedEvents
          : (scenario.remoteExpectations.eventTypes.isNotEmpty
                ? scenario.remoteExpectations.eventTypes
                : scenario.expectedEvents);
      final qualityStandard =
          scenarioPack.qualityStandards[scenario.qualityStandardRef];
      expect(qualityStandard, isNotNull, reason: scenario.id);
      final minimumQualityScore = qualityStandard?.minimumTotalScore ?? 0;
      _expectRunMeetsScenarioContract(
        scenario: scenario,
        answer: state.answer,
        errorMessage: state.errorMessage,
        running: state.running,
        eventTypes: eventTypes,
        toolNames: toolNames,
        expectedAnswerFragments: expectedAnswerFragments,
        expectedEventTypes: expectedEventTypes,
      );
      final totalScore = _scoreVerticalQaRun(
        answer: state.answer,
        processSummary: state.processSummary,
        eventTypes: eventTypes,
        toolNames: toolNames,
        expectedAnswerFragments: expectedAnswerFragments,
        expectedToolNames: scenario.expectedToolNames,
      );
      expect(
        totalScore,
        greaterThanOrEqualTo(minimumQualityScore),
        reason:
            '${scenario.id} score=$totalScore standard=$minimumQualityScore',
      );

      _printEvalResult(<String, dynamic>{
        'env': runtimeEnv,
        'repositoryMode': mode.name,
        'scenarioId': scenario.id,
        'skillId': scenario.skillId,
        'domainId': scenario.domainId,
        'question': scenario.question,
        'answer': state.answer,
        'answerLength': state.answer.length,
        'errorMessage': state.errorMessage,
        'running': state.running,
        'durationMs': durationMs,
        'eventTypes': eventTypes,
        'eventCount': state.events.length,
        'selectedSkillIds': selectedSkillIds.toList(growable: false),
        'toolNames': toolNames.toList(growable: false),
        'qualityStandardRef': scenario.qualityStandardRef,
        'qualityScore': totalScore,
        'minimumQualityScore': minimumQualityScore,
        'processSummary': <String, dynamic>{
          'searchCount': state.processSummary.searchCount,
          'processedCount': state.processSummary.processedCount,
          'acceptedCount': state.processSummary.acceptedCount,
          'finalAnswerReady': state.processSummary.finalAnswerReady,
        },
        'transcript': transcript,
        'turnId': state.turnId,
        'conversationId': state.conversationId,
      });
    }
  });
}

void _installPathProviderMock() {
  final root = Directory.systemTemp.createTempSync('assistant_skill_eval_');
  const channel = MethodChannel('plugins.flutter.io/path_provider');
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
      .setMockMethodCallHandler(channel, (call) async {
        switch (call.method) {
          case 'getApplicationDocumentsDirectory':
          case 'getApplicationSupportDirectory':
          case 'getTemporaryDirectory':
            return root.path;
          default:
            return null;
        }
      });
}

void _expectRunMeetsScenarioContract({
  required AssistantEvalScenario scenario,
  required String answer,
  required String errorMessage,
  required bool running,
  required List<String> eventTypes,
  required Set<String> toolNames,
  required List<String> expectedAnswerFragments,
  required List<String> expectedEventTypes,
}) {
  expect(running, isFalse, reason: scenario.id);
  expect(errorMessage, isEmpty, reason: scenario.id);
  expect(answer.trim(), isNotEmpty, reason: scenario.id);
  for (final fragment in expectedAnswerFragments) {
    expect(
      answer,
      contains(fragment),
      reason: '${scenario.id} missing $fragment',
    );
  }
  for (final eventType in expectedEventTypes) {
    expect(
      eventTypes,
      contains(eventType),
      reason: '${scenario.id} missing $eventType',
    );
  }
  for (final toolName in scenario.expectedToolNames) {
    expect(
      toolNames,
      contains(toolName),
      reason: '${scenario.id} missing $toolName',
    );
  }
  for (final forbidden in _forbiddenAnswerFragments) {
    expect(
      answer,
      isNot(contains(forbidden)),
      reason: '${scenario.id} leaked $forbidden',
    );
  }
}

double _scoreVerticalQaRun({
  required String answer,
  required PersonalAssistantProcessSummary processSummary,
  required List<String> eventTypes,
  required Set<String> toolNames,
  required List<String> expectedAnswerFragments,
  required List<String> expectedToolNames,
}) {
  var score = 0.0;
  if (processSummary.processingSummary.trim().isNotEmpty &&
      processSummary.finalAnswerReady &&
      processSummary.finalAnswerSummary.trim().isNotEmpty) {
    score += 2;
  }
  if (processSummary.searchCount >= 1 &&
      processSummary.processedCount >= 1 &&
      processSummary.acceptedCount >= 1) {
    score += 2;
  }
  if (expectedAnswerFragments.every(answer.contains)) {
    score += 2;
  }
  if (answer.length >= 40 && expectedToolNames.every(toolNames.contains)) {
    score += 1.5;
  }
  if (_forbiddenAnswerFragments.every(
    (fragment) => !answer.contains(fragment),
  )) {
    score += 1.5;
  }
  if (eventTypes.contains('final_answer') ||
      eventTypes.contains('assistant.answer.final')) {
    score += 1;
  }
  return score;
}

const _forbiddenAnswerFragments = <String>[
  'contractId',
  'tool_call',
  'assistant_turn',
  '<think>',
  '</think>',
  'JSON',
  '系统提示',
];

Future<void> _pumpUntilStreamSettled(WidgetTester tester) async {
  for (var i = 0; i < 240; i++) {
    await tester.pump(const Duration(milliseconds: 100));
    final context = tester.element(find.byType(AssistantTabPage));
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
      expect(shortestSide, lessThan(700));
    case 'tablet':
      expect(longestSide, greaterThanOrEqualTo(700));
      expect(shortestSide, greaterThanOrEqualTo(500));
    case 'any':
      expect(shortestSide, greaterThan(0));
    default:
      fail('未知 VALIDATION_SCREEN_CLASS=$expected');
  }
}

String _toolNameForEvent(Map<String, dynamic> payload) {
  final raw = payload['toolUse'];
  if (raw is Map) {
    return (raw['toolName'] ?? raw['tool_name'] ?? '').toString();
  }
  return '';
}

bool _looksLikeSkillSelection(Map<String, dynamic> payload) {
  return payload.containsKey('skillId') &&
      payload.containsKey('domainId') &&
      payload.containsKey('promptPolicy');
}

void _printEvalResult(Map<String, dynamic> result) {
  // ignore: avoid_print
  print('ASSISTANT_SKILL_EVAL_RESULT_JSON:${jsonEncode(result)}');
}
