import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/orchestrator_state_contract.dart';
import 'package:quwoquan_app/assistant/contracts/task_graph_contract.dart';
import 'package:quwoquan_app/assistant/orchestration/task_scheduler.dart';

void main() {
  group('TaskScheduler', () {
    const scheduler = TaskScheduler();

    test('schedules pending and in-progress tasks as current batch', () {
      final state = scheduler.schedule(
        const TaskGraph(
          tasks: <TaskNode>[
            TaskNode(
              taskId: 'task_search',
              intentId: 'intent_search',
              status: TaskStatus.pending,
            ),
            TaskNode(
              taskId: 'task_open',
              intentId: 'intent_open',
              status: TaskStatus.inProgress,
            ),
          ],
        ),
      );

      expect(state.completedTaskIds, isEmpty);
      expect(state.currentBatchTaskIds, <String>['task_search', 'task_open']);
      expect(state.pendingTaskBatches, isEmpty);
      expect(state.interactionDirective.kind, InteractionDirectiveKind.idle);
    });

    test('keeps completed tasks separate from current batch', () {
      final state = scheduler.schedule(
        const TaskGraph(
          tasks: <TaskNode>[
            TaskNode(
              taskId: 'task_done',
              intentId: 'intent_done',
              status: TaskStatus.completed,
            ),
            TaskNode(
              taskId: 'task_next',
              intentId: 'intent_next',
              status: TaskStatus.pending,
            ),
          ],
        ),
      );

      expect(state.completedTaskIds, <String>['task_done']);
      expect(state.currentBatchTaskIds, <String>['task_next']);
    });

    test('empty graph is ready for final answer interaction', () {
      final state = scheduler.schedule(const TaskGraph());

      expect(state.currentBatchTaskIds, isEmpty);
      expect(state.pendingTaskBatches, isEmpty);
      expect(
        state.interactionDirective.kind,
        InteractionDirectiveKind.finalAnswer,
      );
    });
  });
}
