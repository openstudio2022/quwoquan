import 'package:quwoquan_app/assistant/contracts/task_graph_contract.dart';
import 'package:quwoquan_app/assistant/contracts/understanding_result_contract.dart';
import 'package:quwoquan_app/assistant/orchestration/skill_match_policy.dart';

class IntentTaskCompiler {
  const IntentTaskCompiler({this.routingPolicy = const SkillMatchPolicy()});

  final SkillMatchPolicy routingPolicy;

  TaskGraph compile(UnderstandingResult understandingResult) {
    final tasks = <TaskNode>[];
    for (final intent in understandingResult.intents) {
      final route = routingPolicy.route(intent);
      if (!route.hasExecutableTool) {
        continue;
      }
      tasks.add(
        TaskNode(
          taskId: _taskIdFor(intent.intentId),
          intentId: intent.intentId,
          toolName: route.toolName,
          toolArgs: route.toolArgs,
        ),
      );
    }
    return TaskGraph(tasks: tasks);
  }

  String _taskIdFor(String intentId) {
    final normalized = intentId.trim();
    if (normalized.isEmpty) {
      return 'task_unknown';
    }
    if (normalized.startsWith('intent_')) {
      return 'task_${normalized.substring('intent_'.length)}';
    }
    return 'task_$normalized';
  }
}
