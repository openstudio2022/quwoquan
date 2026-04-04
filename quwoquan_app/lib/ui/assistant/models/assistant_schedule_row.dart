import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';

/// 助手 Tab 待办列表行（替代 `Map<String, dynamic>` schedule row）。
class AssistantScheduleRow {
  const AssistantScheduleRow({
    required this.title,
    required this.desc,
  });

  final String title;
  final String desc;

  factory AssistantScheduleRow.fromTask(AssistantUserTaskView task) {
    return AssistantScheduleRow(
      title: task.title,
      desc: task.description ?? '',
    );
  }
}
