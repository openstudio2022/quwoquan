import 'package:quwoquan_app/runtime/transport/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_catalog/application/skill_catalog_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// AssistantSkillCatalog 的 production generated-client query adapter。
final class RemoteAssistantSkillCatalogAdapter
    implements AssistantSkillCatalogFacet {
  const RemoteAssistantSkillCatalogAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final CloudOperationInvocationContext Function(String clientPageId)
  invocationContext;

  @override
  Future<List<AssistantSkillCatalogItemView>> listSkillCatalog({
    int limit = kAssistantSkillCatalogDefaultLimit,
  }) async {
    final result = await client.assistantSkillCatalogListSkills(
      ListSkillsQuery(limit: limit),
      context: invocationContext(AssistantRequestPageIds.listSkills),
    );
    return result.items;
  }

  @override
  Future<AssistantSkillCatalogItemDetailView> getSkillCatalogItem({
    required String skillId,
  }) {
    return client.assistantSkillCatalogGetSkillCatalogItem(
      GetSkillCatalogItemQuery(skillId: skillId),
      context: invocationContext(AssistantRequestPageIds.getSkillCatalogItem),
    );
  }
}
