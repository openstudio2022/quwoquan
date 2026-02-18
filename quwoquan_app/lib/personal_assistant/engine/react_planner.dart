import 'package:quwoquan_app/personal_assistant/engine/react_state.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

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
    required String lastMessage,
  }) {
    if (!lastStepSuccess) return true;
    if (lastMessage.trim().isEmpty) return true;
    if (state.shouldStopByBudget || state.shouldStopByIteration) return false;
    final lowered = lastMessage.toLowerCase();
    if (lowered.contains('missing') ||
        lowered.contains('not found') ||
        lowered.contains('fallback') ||
        lowered.contains('失败') ||
        lowered.contains('未获得可用摘要') ||
        lowered.contains('信息不足') ||
        lowered.contains('检索未找到足够信息') ||
        lowered.contains('需要进一步检索')) {
      return true;
    }
    return false;
  }
}

