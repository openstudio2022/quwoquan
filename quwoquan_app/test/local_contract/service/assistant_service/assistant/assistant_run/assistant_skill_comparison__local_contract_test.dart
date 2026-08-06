// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/trajectory-replay-evaluation-gate/spec.md#gwt-002
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/personal_assistant_stream_controller.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/runtime_enums.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/presentation/personal_assistant_session_page.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/persisted_timeline_turn_codec.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/models/visit_models.dart';
import 'package:quwoquan_app/runtime/services/visit_recorder_service.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';

import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_facets_typed_double.dart';
import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_eval_scenario_fixtures.dart';
import '../../../../../support/runtime/cloud_boundary_test_scope.dart';

const _assistantScenarioFixtureJsonBase64 = String.fromEnvironment(
  'ASSISTANT_SCENARIO_FIXTURE_JSON_B64',
);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('21 skill alpha fixture comparison evidence collector', (
    tester,
  ) async {
    _installPathProviderMock();
    final scenarioPack = _loadLocalAssistantEvalScenarioPack();
    final scenarios = scenarioPack.assistantTurnScenariosFor('alpha');
    expect(scenarios, hasLength(21));
    expect(scenarioPack.qualityStandards, hasLength(20));

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...sealedCloudBoundaryOverrides(),
          ...assistantFacetOverrides(
            ScenarioEvalMockAssistantRepository(pack: scenarioPack),
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

    expect(find.byKey(TestKeys.assistantChatInputField), findsOneWidget);

    final container = ProviderScope.containerOf(
      tester.element(find.byType(PersonalAssistantSessionPage)),
    );

    for (final scenario in scenarios) {
      final started = DateTime.now();
      await container
          .read(personalAssistantStreamControllerProvider.notifier)
          .send(scenario.question);
      await _pumpUntilStreamSettled(tester);

      final context = tester.element(find.byType(PersonalAssistantSessionPage));
      final state = ProviderScope.containerOf(
        context,
      ).read(personalAssistantStreamControllerProvider);
      final durationMs = DateTime.now().difference(started).inMilliseconds;
      final eventTypes = state.events
          .map((event) => event.eventType.wireName)
          .toList(growable: false);
      final selectedSkillIds = <String>{
        for (final event in state.events)
          if (_looksLikeSkillSelection(event.payload))
            _processString(event.payload, 'skillId'),
      }..remove('');
      final toolNames = <String>{
        for (final event in state.events) _toolNameForEvent(event.payload),
      }..remove('');
      final transcript = state.transcript
          .map(PersistedTimelineTurnCodec.encode)
          .toList(growable: false);
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
        expectedAnswerFragments: scenario.expectedAnswerFragments,
        expectedEventTypes: scenario.expectedEvents,
      );
      final totalScore = _scoreVerticalQaRun(
        answer: state.answer,
        processSummary: state.processSummary,
        eventTypes: eventTypes,
        toolNames: toolNames,
        expectedAnswerFragments: scenario.expectedAnswerFragments,
        expectedToolNames: scenario.expectedToolNames,
      );
      expect(
        totalScore,
        greaterThanOrEqualTo(minimumQualityScore),
        reason:
            '${scenario.id} score=$totalScore standard=$minimumQualityScore',
      );

      _printEvalResult(<String, dynamic>{
        'env': 'alpha',
        'composition': 'fixture_override',
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
        'runId': state.runId,
        'sessionId': state.sessionId,
      });
    }
  });
}

final class _NoopVisitRecorderService extends VisitRecorderService {
  @override
  Future<void> recordVisit(VisitTarget target) async {}
}

AssistantEvalScenarioPack _loadLocalAssistantEvalScenarioPack() {
  if (_assistantScenarioFixtureJsonBase64.trim().isNotEmpty) {
    return loadAssistantEvalScenarioPack();
  }
  const fixturePath =
      'quwoquan_service/services/assistant-service/tests/support/'
      'contract_fixtures/scenarios/assistant_skill_eval_scenarios.json';
  final candidates = <File>[
    File('../$fixturePath'),
    File(fixturePath),
    File('../../$fixturePath'),
  ];
  for (final candidate in candidates) {
    if (candidate.existsSync()) {
      return AssistantEvalScenarioPack.fromJson(
        jsonDecode(candidate.readAsStringSync()) as Map<String, dynamic>,
      );
    }
  }
  throw StateError(
    'assistant skill eval fixture 缺失: $fixturePath, '
    'cwd=${Directory.current.path}',
  );
}

void _installPathProviderMock() {
  final root = Directory.systemTemp.createTempSync('assistant_skill_eval_');
  addTearDown(() {
    if (root.existsSync()) {
      root.deleteSync(recursive: true);
    }
  });
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
  if (eventTypes.contains('completed')) {
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
  final raw = payload['process'];
  if (raw is Map) {
    return (raw['toolName'] ?? '').toString();
  }
  return '';
}

bool _looksLikeSkillSelection(Map<String, dynamic> payload) {
  final raw = payload['process'];
  return raw is Map &&
      raw['stage'] == 'classifying' &&
      raw.containsKey('skillId') &&
      raw.containsKey('domainId');
}

String _processString(Map<String, dynamic> payload, String key) {
  final raw = payload['process'];
  return raw is Map ? (raw[key] ?? '').toString() : '';
}

void _printEvalResult(Map<String, dynamic> result) {
  // ignore: avoid_print
  print('ASSISTANT_SKILL_EVAL_RESULT_JSON:${jsonEncode(result)}');
}
