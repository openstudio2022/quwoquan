import 'package:quwoquan_app/application/content/post/author_impact_query.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Content/Post 作者影响力的 production Remote adapter。
///
/// 传输、路径、鉴权、重试和 decoder 由 generated operation client 处理；本适配器
/// 只在 pure-Dart projection 与 App runtime DTO 之间做强类型映射。
typedef AuthorImpactInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

final class RemoteAuthorImpactQuery implements AuthorImpactQuery {
  const RemoteAuthorImpactQuery({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final AuthorImpactInvocationContextFactory invocationContext;

  @override
  Future<AuthorImpactSummary> getAuthorImpact(String personaId) async {
    return client.contentPostGetAuthorImpact(
      GetAuthorImpactQuery(personaId: personaId),
      context: invocationContext(ContentRequestPageIds.getAuthorImpact),
    );
  }

  @override
  Future<AuthorImpactEvidencePage> listAuthorImpactEvidence({
    required String personaId,
    required String impactId,
    String evidenceSnapshotId = '',
    String cursor = '',
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return client.contentPostListAuthorImpactEvidence(
      ListAuthorImpactEvidenceQuery(
        personaId: personaId,
        impactId: impactId,
        evidenceSnapshotId: evidenceSnapshotId,
        cursor: cursor,
        limit: limit,
      ),
      context: invocationContext(
        ContentRequestPageIds.listAuthorImpactEvidence,
      ),
    );
  }
}
