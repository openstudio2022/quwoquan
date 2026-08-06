import 'package:quwoquan_app/service/assistant_service/assistant/assistant_task_view/application/assistant_task_query.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class AssistantPrototypeTaskRow {
  const AssistantPrototypeTaskRow({
    required this.taskKey,
    required this.title,
    this.time,
    required this.status,
    this.category,
  });

  final String taskKey;
  final String title;
  final String? time;
  final String status;
  final String? category;
}

class InMemoryAssistantTaskQuery implements AssistantTaskQuery {
  static const List<AssistantPrototypeTaskRow> _tasks =
      <AssistantPrototypeTaskRow>[
        AssistantPrototypeTaskRow(
          taskKey: '1',
          title: '完成《城市节奏》摄影集',
          time: '14:00',
          status: 'pending',
          category: '计划',
        ),
        AssistantPrototypeTaskRow(
          taskKey: '2',
          title: '回复圈子里的讨论',
          time: '16:30',
          status: 'completed',
          category: '待办',
        ),
        AssistantPrototypeTaskRow(
          taskKey: '3',
          title: '晚间灵感整理',
          time: '21:00',
          status: 'pending',
          category: '待办',
        ),
      ];

  @override
  Future<List<AssistantTaskItemView>> listAssistantTasks({
    int limit = kAssistantTaskListDefaultLimit,
    String? status,
  }) async {
    Iterable<AssistantPrototypeTaskRow> rows = _tasks;
    if (status != null && status.trim().isNotEmpty) {
      rows = _tasks.where((row) => row.status == status.trim());
    }
    return rows
        .map((row) {
          final time = row.time ?? '';
          final category = row.category ?? '';
          final description = <String>[
            if (time.isNotEmpty) time,
            if (category.isNotEmpty) category,
          ].join(' · ');
          return AssistantTaskItemView(
            taskId: row.taskKey,
            title: row.title,
            description: description.isEmpty ? null : description,
            status: row.status,
            updatedAt: DateTime.now().toUtc().toIso8601String(),
          );
        })
        .take(limit)
        .toList(growable: false);
  }
}
