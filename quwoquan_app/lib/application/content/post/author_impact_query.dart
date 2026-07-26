import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_evidence_page.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';

/// Content/Post 对象的作者影响力查询面。
///
/// 用户资料查询不得承载内容域事实；App 页面通过该细粒度 Facet 读取影响摘要与证据。
abstract interface class AuthorImpactQuery {
  Future<AuthorImpactSummary> getAuthorImpact(String subAccountId);

  Future<AuthorImpactEvidencePage> listAuthorImpactEvidence({
    required String subAccountId,
    required String impactId,
    String evidenceSnapshotId = '',
    String cursor = '',
    int limit = CloudApiDefaults.pageLimit,
  });
}
