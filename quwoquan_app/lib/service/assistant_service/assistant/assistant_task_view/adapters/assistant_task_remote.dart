import 'package:quwoquan_app/service/assistant_service/assistant/assistant_task_view/application/assistant_task_query.dart';
import 'package:quwoquan_app/runtime/transport/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef AssistantTaskInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      String? idempotencyKey,
      bool networkSurface,
    });

/// AssistantTaskView generated-client query adapter。
final class AssistantTaskGeneratedAdapter implements AssistantTaskQuery {
  const AssistantTaskGeneratedAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final AssistantTaskInvocationContextFactory invocationContext;

  @override
  Future<List<AssistantTaskItemView>> listAssistantTasks({
    int limit = kAssistantTaskListDefaultLimit,
    String? status,
  }) async {
    final normalizedStatus = status?.trim();
    final slice = await client.assistantAssistantTaskViewListAssistantTasks(
      ListAssistantTasksQuery(
        limit: limit,
        status: normalizedStatus == null || normalizedStatus.isEmpty
            ? null
            : normalizedStatus,
      ),
      context: invocationContext(
        AssistantRequestPageIds.listAssistantTasks,
        networkSurface: false,
      ),
    );
    return slice.items
        .where((row) => row.taskId.isNotEmpty)
        .take(limit)
        .toList(growable: false);
  }
}
