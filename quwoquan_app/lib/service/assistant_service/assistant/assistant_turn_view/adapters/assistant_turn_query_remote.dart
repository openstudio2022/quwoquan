import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/assistant_turn_query.dart';
import 'package:quwoquan_app/runtime/transport/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef AssistantTurnInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      String? idempotencyKey,
      bool networkSurface,
    });

/// AssistantTurnView generated-client query adapter。
final class AssistantTurnQueryGeneratedAdapter implements AssistantTurnQuery {
  const AssistantTurnQueryGeneratedAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final AssistantTurnInvocationContextFactory invocationContext;

  @override
  Future<AssistantTurnListView> listSessionTurns({
    required String sessionId,
    int limit = kAssistantTurnListDefaultLimit,
    String cursor = '',
  }) {
    return client.assistantAssistantTurnViewListSessionTurns(
      AssistantTurnListQuery(
        sessionId: sessionId,
        limit: limit,
        cursor: cursor.trim().isEmpty ? null : cursor.trim(),
      ),
      context: invocationContext(
        AssistantRequestPageIds.listSessionTurns,
        networkSurface: false,
      ),
    );
  }
}
