// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/run-stream-protocol/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_run_api_scenario_pack.dart';
import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_run_remote_api_harness.dart';

const _scenarioId = String.fromEnvironment('ASSISTANT_SCENARIO_ID');

void main() {
  test('assistant beta Remote scenario stream contract', () async {
    final harness = await AssistantRunRemoteApiHarness.fromEnvironment(
      allowedEnvironments: const {CloudEnvironment.beta},
    );
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
      for (final fragment in scenario.expectedAnswerFragments) {
        expect(result.answer, contains(fragment), reason: scenario.id);
      }
      for (final eventType in scenario.expectedEventTypes) {
        expect(result.eventTypes, contains(eventType), reason: scenario.id);
      }
      final sequences = result.events.map((event) => event.seq).toList();
      expect(sequences, orderedEquals(sequences.toSet().toList()..sort()));
      expect(result.events.first.eventType.wireName, 'run_started');
      expect(result.events.last.eventType.wireName, 'completed');
    }
  });
}
