import 'package:quwoquan_app/assistant/contracts/orchestrator_state_contract.dart';
import 'package:quwoquan_app/assistant/contracts/task_graph_contract.dart';

class TaskScheduler {
  const TaskScheduler();

  ConversationOrchestratorState schedule(TaskGraph taskGraph) {
    final completed = <String>[];
    final ready = <String>[];
    final pending = <String>[];

    for (final task in taskGraph.tasks) {
      switch (task.status) {
        case TaskStatus.completed:
          completed.add(task.taskId);
        case TaskStatus.failed:
          pending.add(task.taskId);
        case TaskStatus.inProgress:
          ready.add(task.taskId);
        case TaskStatus.pending:
          ready.add(task.taskId);
      }
    }

    final currentBatch = ready.isNotEmpty ? ready : const <String>[];
    final pendingBatches = pending.isEmpty
        ? const <List<String>>[]
        : <List<String>>[pending];

    return ConversationOrchestratorState(
      completedTaskIds: completed,
      currentBatchTaskIds: currentBatch,
      pendingTaskBatches: pendingBatches,
      interactionDirective: currentBatch.isEmpty && pendingBatches.isEmpty
          ? const InteractionDirective(
              kind: InteractionDirectiveKind.finalAnswer,
            )
          : const InteractionDirective(),
    );
  }
}
