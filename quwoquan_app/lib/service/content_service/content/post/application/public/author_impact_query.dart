import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Content/Post 对象对外公开的作者影响力查询面。
///
/// 主页等 participant 只通过该纯 application port 读取影响摘要与证据；
/// 具体 generated Remote adapter 只在 runtime/di 组合。
abstract interface class AuthorImpactQuery {
  Future<AuthorImpactSummary> getAuthorImpact(String personaId);

  Future<AuthorImpactEvidencePage> listAuthorImpactEvidence({
    required String personaId,
    required String impactId,
    String evidenceSnapshotId = '',
    String cursor = '',
    int limit = ListAuthorImpactEvidenceQuery.defaultLimit,
  });
}
