import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef AssistantLearningFactInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      required String idempotencyKey,
    });

/// AssistantLearningFact 的 production generated-client append adapter。
final class RemoteAssistantLearningFactAppendAdapter
    implements AssistantLearningFactAppendFacet {
  const RemoteAssistantLearningFactAppendAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final AssistantLearningFactInvocationContextFactory invocationContext;

  @override
  Future<AssistantLearningFactAppendReceipt> appendUserFact({
    required AssistantLearningFactAppendCommand request,
  }) async {
    final eventId = request.eventId.trim();
    if (eventId.isEmpty) {
      throw ArgumentError.value(
        request.eventId,
        'request.eventId',
        'AppendAssistantLearningFact requires a stable event identity',
      );
    }
    return client.assistantAssistantLearningFactAppendAssistantLearningFact(
      request,
      context: invocationContext(
        AssistantRequestPageIds.appendAssistantLearningFact,
        idempotencyKey: eventId,
      ),
    );
  }
}
