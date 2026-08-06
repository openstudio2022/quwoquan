import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

const int kAssistantTaskListDefaultLimit = 32;

/// AssistantTaskView 的 owner 只读查询端口。
abstract class AssistantTaskQuery {
  Future<List<AssistantTaskItemView>> listAssistantTasks({
    int limit = kAssistantTaskListDefaultLimit,
    String? status,
  });
}
