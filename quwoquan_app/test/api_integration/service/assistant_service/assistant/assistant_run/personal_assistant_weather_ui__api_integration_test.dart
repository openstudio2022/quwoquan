// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-004
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';

import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_run_remote_api_harness.dart';

const _question = String.fromEnvironment(
  'ASSISTANT_WEATHER_UI_QUESTION',
  defaultValue: '深圳天气',
);

void main() {
  test('personal assistant beta Remote weather API integration', () async {
    final harness = await AssistantRunRemoteApiHarness.fromEnvironment(
      allowedEnvironments: const {CloudEnvironment.beta},
    );
    addTearDown(harness.close);

    final result = await harness.execute(_question);
    expect(result.run.status, 'completed');
    expect(result.snapshot.failure, isNull);
    expect(result.answer, contains('天气助手'));
    expect(result.answer, isNot(contains('fallback_general_search')));
    expect(result.answer, isNot(contains('All Regions Argentina')));
    expect(result.selectedSkillIds, contains('weather'));
    expect(
      result.events.any((event) {
        final process = event.payload['process'];
        return process is Map &&
            process['stage'] == 'classifying' &&
            process['skillId'] == 'weather';
      }),
      isTrue,
      reason: '应在 beta stream 中选择 weather skill',
    );
    expect(
      result.snapshot.processes.map((process) => process.summary).join('\n'),
      isNot(contains('nextAction')),
    );
    expect(result.eventTypes, contains('completed'));
  });
}
