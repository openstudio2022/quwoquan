import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Content/Post 对象的作者影响力查询面。
///
/// 用户资料查询不得承载内容域事实；App 页面通过该细粒度 Facet 读取影响摘要与证据。
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
