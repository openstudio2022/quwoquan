import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

const int kAssistantSkillCatalogDefaultLimit = 64;

/// 当前 active SkillPackageRelease 的用户目录投影。
abstract class AssistantSkillCatalogFacet {
  Future<List<AssistantSkillCatalogItemView>> listSkillCatalog({
    int limit = kAssistantSkillCatalogDefaultLimit,
  });

  Future<AssistantSkillCatalogItemDetailView> getSkillCatalogItem({
    required String skillId,
  });
}
