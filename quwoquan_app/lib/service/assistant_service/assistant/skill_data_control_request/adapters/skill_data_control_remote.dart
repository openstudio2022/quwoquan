import 'package:quwoquan_app/service/assistant_service/assistant/skill_data_control_request/application/skill_data_control_facet.dart';
import 'package:quwoquan_app/runtime/transport/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef AssistantSkillDataControlInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      String? idempotencyKey,
    });

/// SkillDataControlRequest 的 production generated-client command/query adapter。
final class RemoteAssistantSkillDataControlAdapter
    implements
        SkillDataControlProcessCommandWriter,
        SkillDataControlProcessQuery {
  const RemoteAssistantSkillDataControlAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final AssistantSkillDataControlInvocationContextFactory invocationContext;

  @override
  Future<SkillDataControlMutationReceipt> createSkillDataControlRequest({
    required String skillId,
    required List<SkillDataControlAction> requestedActions,
    required String clientRequestId,
  }) {
    return client.assistantSkillDataControlRequestCreateSkillDataControlRequest(
      CreateSkillDataControlRequestCommand(
        skillId: skillId,
        requestedActions: requestedActions,
      ),
      context: invocationContext(
        AssistantRequestPageIds.createSkillDataControlRequest,
        idempotencyKey: clientRequestId,
      ),
    );
  }

  @override
  Future<SkillDataControlMutationReceipt> confirmSkillDataControlRequest({
    required String requestId,
    required int expectedRevision,
    required bool confirmed,
    required String clientRequestId,
  }) {
    return client
        .assistantSkillDataControlRequestConfirmSkillDataControlRequest(
          ConfirmSkillDataControlRequestCommand(
            requestId: requestId,
            expectedRevision: expectedRevision,
            confirmed: confirmed,
          ),
          context: invocationContext(
            AssistantRequestPageIds.confirmSkillDataControlRequest,
            idempotencyKey: clientRequestId,
          ),
        );
  }

  @override
  Future<SkillDataControlRequest> getSkillDataControlRequest({
    required String requestId,
  }) {
    return client.assistantSkillDataControlRequestGetSkillDataControlRequest(
      GetSkillDataControlRequestQuery(requestId: requestId),
      context: invocationContext(
        AssistantRequestPageIds.getSkillDataControlRequest,
      ),
    );
  }
}
