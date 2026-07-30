import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// AssistantSkillCatalog 的 production generated-client query adapter。
final class RemoteAssistantSkillCatalogAdapter {
  const RemoteAssistantSkillCatalogAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final CloudOperationInvocationContext Function(String clientPageId)
  invocationContext;

  Future<AssistantSkillCatalogListProjection> listSkills({required int limit}) {
    return client.assistantSkillCatalogListSkills(
      ListSkillsQuery(limit: limit),
      context: invocationContext(AssistantRequestPageIds.listSkills),
    );
  }
}
