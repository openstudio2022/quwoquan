import 'package:quwoquan_app/assistant/contracts/search_plan_contract.dart';
import 'package:quwoquan_app/assistant/contracts/task_graph_contract.dart';
import 'package:quwoquan_app/assistant/orchestration/retrieval_tool_selection_policy.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';

TaskGraph taskGraphWithSearchPlans({
  required TaskGraph taskGraph,
  required List<SearchPlanItem> searchPlans,
  required String fallbackQuery,
}) {
  final normalizedSearchPlans = SearchPlanItem.normalizeList(
    SearchPlanItem.toJsonList(searchPlans),
  );
  if (normalizedSearchPlans.isEmpty) {
    return taskGraph;
  }
  if (taskGraph.tasks.isEmpty) {
    final selectedToolName = const RetrievalToolSelectionPolicy().select(
      availableToolNames: const <String>[
        AssistantToolNames.appSearch,
        AssistantToolNames.search,
        AssistantToolNames.webSearch,
      ],
      searchPlans: normalizedSearchPlans,
    );
    return TaskGraph(
      tasks: <TaskNode>[
        TaskNode(
          taskId: 'task_retrieval',
          intentId: 'intent_primary',
          toolName: selectedToolName,
          toolArgs: TaskToolArgs(<String, Object?>{
            'query': _firstQuery(normalizedSearchPlans, fallbackQuery),
            'searchPlans': SearchPlanItem.toJsonList(normalizedSearchPlans),
          }),
        ),
      ],
    );
  }

  var retrievalTaskUpdated = false;
  final updatedTasks = <TaskNode>[];
  for (final task in taskGraph.tasks) {
    if (!retrievalTaskUpdated && _isRetrievalTool(task.toolName)) {
      retrievalTaskUpdated = true;
      updatedTasks.add(
        TaskNode(
          taskId: task.taskId,
          intentId: task.intentId,
          toolName: task.toolName,
          toolArgs: TaskToolArgs(<String, Object?>{
            ...task.toolArgs.fields,
            'query': _firstQuery(normalizedSearchPlans, fallbackQuery),
            'searchPlans': SearchPlanItem.toJsonList(normalizedSearchPlans),
          }),
          status: task.status,
          output: task.output,
        ),
      );
      continue;
    }
    updatedTasks.add(task);
  }
  return TaskGraph(tasks: updatedTasks);
}

bool _isRetrievalTool(String toolName) {
  return AssistantToolNames.isRetrievalName(toolName);
}

String _firstQuery(List<SearchPlanItem> searchPlans, String fallbackQuery) {
  for (final plan in searchPlans) {
    final query = plan.query.trim();
    if (query.isNotEmpty) {
      return query;
    }
  }
  return fallbackQuery.trim();
}
