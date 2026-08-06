// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/spec.md#sit-001
import 'package:flutter_test/flutter_test.dart';

import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_run_api_scenario_pack.dart';
import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_run_remote_api_harness.dart';

const _scenarioId = String.fromEnvironment('ASSISTANT_SCENARIO_ID');

void main() {
  test('assistant beta/gamma generated-client environment smoke', () async {
    final harness = await AssistantRunRemoteApiHarness.fromEnvironment();
    addTearDown(harness.close);
    final scenarioPack = AssistantRunApiScenarioPack.fromEnvironment();
    final allScenarios = scenarioPack.scenariosFor(harness.environment.name);
    final scenarios = _scenarioId.trim().isEmpty
        ? allScenarios
        : allScenarios
              .where((scenario) => scenario.id == _scenarioId)
              .toList(growable: false);
    expect(scenarios, isNotEmpty);

    for (final scenario in scenarios) {
      final result = await harness.execute(scenario.question);
      expect(result.run.status, 'completed', reason: scenario.id);
      expect(result.snapshot.failure, isNull, reason: scenario.id);
      expect(result.answer, isNotEmpty, reason: scenario.id);
      expect(result.eventTypes, contains('run_started'), reason: scenario.id);
      expect(result.eventTypes, contains('completed'), reason: scenario.id);
      expect(
        scenario.expectedAnswerFragments.any(result.answer.contains),
        isTrue,
        reason:
            '${scenario.id} did not match '
            '${scenario.expectedAnswerFragments}',
      );
      for (final expectedType in scenario.expectedEventTypes) {
        expect(result.eventTypes, contains(expectedType), reason: scenario.id);
      }
      expect(result.answer, isNot(contains('ASSISTANT.MIDDLEWARE')));
      expect(result.answer, isNot(contains('tool_unavailable')));
      expect(result.answer, isNot(contains('nextAction')));
      for (final event in result.events) {
        expect(event.payload.containsKey('debugTrace'), isFalse);
        expect(event.payload.containsKey('reasoning'), isFalse);
        expect(event.payload.containsKey('toolUse'), isFalse);
        expect(event.payload.containsKey('toolInput'), isFalse);
      }
    }

    final telemetryEvents = await harness.telemetry.waitForEvents(
      minimumCount: 1,
    );
    expect(telemetryEvents, isNotEmpty);
    expect(telemetryEvents.every((event) => event.succeeded), isTrue);
  });
}
