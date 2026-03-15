import 'package:quwoquan_app/assistant/contracts/react_observation.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_policies.dart';
import 'package:quwoquan_app/assistant/internal_legacy/engine/react_state.dart';
import 'package:quwoquan_app/assistant/internal_legacy/tools/tool_schema.dart';

class ReactPlanner {
  const ReactPlanner();

  List<ReactPlanStep> buildPlan({
    required String userGoal,
    required List<AssistantToolCall> suggestedToolCalls,
  }) {
    if (suggestedToolCalls.isNotEmpty) {
      return suggestedToolCalls
          .asMap()
          .entries
          .map(
            (entry) => ReactPlanStep(
              id: 'step_${entry.key + 1}',
              description: '执行工具 ${entry.value.name}',
              toolName: entry.value.name,
              arguments: entry.value.arguments,
              toolCallId: entry.value.id,
            ),
          )
          .toList(growable: false);
    }
    return <ReactPlanStep>[
      ReactPlanStep(
        id: 'step_1',
        description: '直接回答目标问题',
        toolName: '',
        arguments: <String, dynamic>{'goal': userGoal},
      ),
    ];
  }
}

class ReactReflector {
  const ReactReflector();

  bool shouldReplan({
    required ReactRunState state,
    required bool lastStepSuccess,
    required Map<String, dynamic> lastObservation,
    ReactPolicy policy = ReactPolicy.defaults,
  }) {
    if (state.shouldStopByBudget || state.shouldStopByIteration) return false;
    if (!lastStepSuccess) return true;
    final observation = ReactObservation.fromObservationMap(lastObservation);
    if (policy.replanStatuses.contains(observation.status)) {
      return true;
    }
    if (observation.retryable &&
        policy.replanRetryableErrorClasses.contains(observation.errorClass)) {
      return true;
    }
    if ((observation.coverage > 0 &&
            observation.coverage < policy.replanCoverageMin) ||
        (observation.confidence > 0 &&
            observation.confidence < policy.replanConfidenceMin) ||
        (observation.freshnessHours > policy.replanFreshnessHoursMax)) {
      return true;
    }
    return false;
  }
}

