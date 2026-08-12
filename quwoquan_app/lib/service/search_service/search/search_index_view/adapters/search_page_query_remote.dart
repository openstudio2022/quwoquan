import 'package:quwoquan_app/runtime/transport/generated/search/search_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/graphql_read/generated/search_page.g.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/search_page_query_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_contracts/generated/gateway_contracts.dart';

typedef SearchPageQueryInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// `SearchPage` signed persisted GraphQL 的 production Remote 适配器。
final class RemoteSearchPageQuery implements SearchPageQueryFacet {
  const RemoteSearchPageQuery({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedSearchPageGraphQLClient client;
  final SearchPageQueryInvocationContextFactory invocationContext;

  @override
  Future<SearchPageSlice> searchPage(
    SearchPageInput input, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) {
    final base = invocationContext(SearchRequestPageIds.search);
    return client.searchPage(
      input,
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
