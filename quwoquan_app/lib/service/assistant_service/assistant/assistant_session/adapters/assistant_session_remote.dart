import 'package:quwoquan_app/service/assistant_service/assistant/assistant_session/application/public/assistant_session_ports.dart';
import 'package:quwoquan_app/runtime/transport/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef AssistantSessionInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      String? idempotencyKey,
      bool networkSurface,
    });

/// AssistantSession generated-client adapter。
final class AssistantSessionGeneratedAdapter
    implements AssistantSessionCommandWriter, AssistantSessionQuery {
  const AssistantSessionGeneratedAdapter({
    required this.client,
    required this.invocationContext,
    this.networkSurface = false,
  });

  final GeneratedCloudOperationClient client;
  final AssistantSessionInvocationContextFactory invocationContext;
  final bool networkSurface;

  @override
  Future<AssistantSessionWire> createAssistantSession({
    String summary = '',
    required String clientRequestId,
  }) async {
    final requestId = _requireSessionRequestId(clientRequestId);
    return client.assistantAssistantSessionCreateAssistantSession(
      AssistantCreateSessionRequest(
        summary: summary.trim().isEmpty ? null : summary.trim(),
        clientRequestId: requestId,
      ),
      context: invocationContext(
        AssistantRequestPageIds.createAssistantSession,
        idempotencyKey: requestId,
        networkSurface: networkSurface,
      ),
    );
  }

  @override
  Future<AssistantSessionWire> getAssistantSession({
    required String sessionId,
  }) {
    return client.assistantAssistantSessionGetAssistantSession(
      AssistantSessionByIdQuery(sessionId: sessionId),
      context: invocationContext(
        AssistantRequestPageIds.getAssistantSession,
        networkSurface: networkSurface,
      ),
    );
  }

  @override
  Future<AssistantSessionListView> listAssistantSessions({
    int limit = kAssistantSessionListDefaultLimit,
    String cursor = '',
  }) {
    return client.assistantAssistantSessionListAssistantSessions(
      AssistantSessionListQuery(limit: limit, cursor: cursor),
      context: invocationContext(
        AssistantRequestPageIds.listAssistantSessions,
        networkSurface: networkSurface,
      ),
    );
  }
}

String _requireSessionRequestId(String value) {
  final normalized = value.trim();
  if (normalized.isEmpty) {
    throw ArgumentError.value(
      value,
      'clientRequestId',
      '${AppCloudOperationIds.assistantAssistantSessionCreateAssistantSession} requires a stable client request identity',
    );
  }
  return normalized;
}
