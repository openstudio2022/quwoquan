import 'package:quwoquan_app/cloud/runtime/generated/search/search_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef SearchQueryInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// search-service canonical generated operation 的 production Remote 适配器。
final class RemoteCanonicalSearchQuery implements CanonicalSearchQueryFacet {
  const RemoteCanonicalSearchQuery({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final SearchQueryInvocationContextFactory invocationContext;

  @override
  Future<CanonicalSearchResult> search(
    CanonicalSearchQuery query, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) {
    final base = invocationContext(SearchRequestPageIds.searchQuery);
    return client.searchQuerySearchQuery(
      query,
      context: CloudOperationInvocationContext(
        surfaceId: base.surfaceId,
        clientPageId: base.clientPageId,
        actor: base.actor,
        routeId: base.routeId,
        referralSource: base.referralSource,
        feedRequestId: base.feedRequestId,
        shareId: base.shareId,
        modelId: base.modelId,
        experimentBucket: base.experimentBucket,
        idempotencyKey: base.idempotencyKey,
        deadlineAt: deadlineAt ?? base.deadlineAt,
        cancellation: cancellation ?? base.cancellation,
      ),
    );
  }
}
