import 'package:quwoquan_app/service/assistant_service/assistant/assistant_entry_view/application/assistant_entry_query.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/page_context/application/public/assistant_open_context.dart';
import 'package:quwoquan_app/runtime/transport/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef AssistantEntryInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      String? idempotencyKey,
      bool networkSurface,
    });

/// AssistantEntryView generated-client query adapter。
final class AssistantEntryGeneratedAdapter implements AssistantEntryViewQuery {
  const AssistantEntryGeneratedAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final AssistantEntryInvocationContextFactory invocationContext;

  @override
  Future<AssistantEntryResponse> getAssistantEntry({
    required AssistantOpenContext context,
  }) {
    return client.assistantAssistantEntryViewGetAssistantEntry(
      AssistantEntryQuery(
        pageType: assistantPageTypeForSource(context.source).wireName,
        objectId: (context.entityId ?? '').trim().isEmpty
            ? null
            : context.entityId!.trim(),
      ),
      context: invocationContext(
        AssistantRequestPageIds.getAssistantEntry,
        networkSurface: false,
      ),
    );
  }
}
