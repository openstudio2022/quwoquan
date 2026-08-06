// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/trajectory-replay-evaluation-gate/spec.md#gwt-002
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';

import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_run_api_scenario_pack.dart';
import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_run_remote_api_harness.dart';

void main() {
  test('21 skill beta generated-client comparison evidence', () async {
    final harness = await AssistantRunRemoteApiHarness.fromEnvironment(
      allowedEnvironments: const {CloudEnvironment.beta},
    );
    addTearDown(harness.close);
    final scenarioPack = AssistantRunApiScenarioPack.fromEnvironment();
    final scenarios = scenarioPack.scenariosFor(harness.environment.name);
    expect(scenarios, hasLength(21));
    expect(scenarioPack.qualityStandards, hasLength(20));

    for (final scenario in scenarios) {
      final started = DateTime.now();
      final result = await harness.execute(scenario.question);
      final durationMs = DateTime.now().difference(started).inMilliseconds;
      final standard =
          scenarioPack.qualityStandards[scenario.qualityStandardRef];
      expect(standard, isNotNull, reason: scenario.id);
      _expectScenarioContract(scenario, result);
      final score = _scoreRun(scenario, result);
      expect(
        score,
        greaterThanOrEqualTo(standard!.minimumTotalScore),
        reason:
            '${scenario.id} score=$score '
            'standard=${standard.minimumTotalScore}',
      );
      for (final forbidden in standard.mustAvoid) {
        expect(result.answer, isNot(equals(forbidden)), reason: scenario.id);
      }

      _printEvalResult(<String, Object?>{
        'env': harness.environment.name,
        'composition': 'production_remote_generated_client',
        'scenarioId': scenario.id,
        'skillId': scenario.skillId,
        'domainId': scenario.domainId,
        'answerLength': result.answer.length,
        'durationMs': durationMs,
        'eventTypes': result.eventTypes,
        'selectedSkillIds': result.selectedSkillIds.toList(growable: false),
        'toolNames': result.toolNames.toList(growable: false),
        'qualityStandardRef': scenario.qualityStandardRef,
        'qualityScore': score,
        'minimumQualityScore': standard.minimumTotalScore,
        'runId': result.run.runId,
        'sessionId': result.sessionId,
      });
    }
  });
}

void _expectScenarioContract(
  AssistantRunApiScenario scenario,
  AssistantRemoteRunResult result,
) {
  expect(result.run.status, 'completed', reason: scenario.id);
  expect(result.snapshot.failure, isNull, reason: scenario.id);
  expect(result.answer, isNotEmpty, reason: scenario.id);
  for (final fragment in scenario.expectedAnswerFragments) {
    expect(result.answer, contains(fragment), reason: scenario.id);
  }
  for (final eventType in scenario.expectedEventTypes) {
    expect(result.eventTypes, contains(eventType), reason: scenario.id);
  }
  for (final toolName in scenario.expectedToolNames) {
    expect(result.toolNames, contains(toolName), reason: scenario.id);
  }
  for (final forbidden in _forbiddenAnswerFragments) {
    expect(result.answer, isNot(contains(forbidden)), reason: scenario.id);
  }
}

double _scoreRun(
  AssistantRunApiScenario scenario,
  AssistantRemoteRunResult result,
) {
  var score = 0.0;
  if (result.snapshot.processes.any(
        (process) => process.summary.trim().isNotEmpty,
      ) &&
      result.answer.isNotEmpty) {
    score += 2;
  }
  if (result.searchedDocumentCount >= 1 && result.acceptedDocumentCount >= 1) {
    score += 2;
  }
  if (scenario.expectedAnswerFragments.every(result.answer.contains)) {
    score += 2;
  }
  if (result.answer.length >= 40 &&
      scenario.expectedToolNames.every(result.toolNames.contains)) {
    score += 1.5;
  }
  if (_forbiddenAnswerFragments.every(
    (fragment) => !result.answer.contains(fragment),
  )) {
    score += 1.5;
  }
  if (result.eventTypes.contains('completed')) {
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

void _printEvalResult(Map<String, Object?> result) {
  // ignore: avoid_print
  print('ASSISTANT_SKILL_EVAL_RESULT_JSON:${jsonEncode(result)}');
}
