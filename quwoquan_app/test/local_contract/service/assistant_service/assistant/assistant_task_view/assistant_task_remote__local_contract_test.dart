// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-001
// readiness_case: assistant_task_view_list_assistant_tasks_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/transport/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_task_view/adapters/assistant_task_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'ListAssistantTasks uses exact filters and typed nonempty tasks',
    () async {
      final executor = _AssistantTaskExecutor();
      bool? observedNetworkSurface;
      final remote = AssistantTaskGeneratedAdapter(
        client: GeneratedCloudOperationClient(executor),
        invocationContext:
            (
              clientPageId, {
              String? idempotencyKey,
              bool networkSurface = false,
            }) {
              expect(idempotencyKey, isNull);
              observedNetworkSurface = networkSurface;
              return CloudOperationInvocationContext(
                surfaceId: 'assistant.tasks',
                clientPageId: clientPageId,
                actor: const CloudOperationActorContext(
                  accountId: 'account-1',
                  personaId: 'persona-1',
                ),
              );
            },
      );

      final tasks = await remote.listAssistantTasks(
        limit: 20,
        status: '  active  ',
      );

      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.assistantAssistantTaskViewListAssistantTasks,
      );
      expect(executor.operation?.method, 'GET');
      expect(executor.operation?.pathTemplate, '/assistant/tasks');
      expect(
        executor.context?.clientPageId,
        AssistantRequestPageIds.listAssistantTasks,
      );
      expect(executor.payload?.pathParameters, isEmpty);
      expect(executor.payload?.queryParameters, <String, String>{
        'limit': '20',
        'status': 'active',
      });
      expect(executor.payload?.body, isNull);
      expect(observedNetworkSurface, isFalse);
      expect(tasks, hasLength(1));
      expect(tasks.single.taskId, 'task-1');
      expect(tasks.single.status, 'active');
      expect(tasks.single.sourceSkillId, 'travel_companion');
    },
  );
}

final class _AssistantTaskExecutor implements CloudOperationExecutor {
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
  CloudOperationRequestPayload? payload;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    this.operation = operation;
    this.context = context;
    payload = requestEncoder();
    return responseDecoder(<String, Object?>{
      'items': <Object?>[
        <String, Object?>{
          'taskId': 'task-1',
          'title': '整理行程',
          'description': '核对明日交通',
          'status': 'active',
          'dueAt': '2026-08-09T08:00:00Z',
          'priority': 'high',
          'sourceSkillId': 'travel_companion',
          'updatedAt': '2026-08-08T10:00:00Z',
        },
        <String, Object?>{
          'taskId': '',
          'title': '无效任务',
          'status': 'active',
          'updatedAt': '2026-08-08T10:00:00Z',
        },
      ],
    });
  }
}
