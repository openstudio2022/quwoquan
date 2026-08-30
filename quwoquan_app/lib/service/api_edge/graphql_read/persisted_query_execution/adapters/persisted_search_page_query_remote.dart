import 'package:quwoquan_app/runtime/transport/generated/search/search_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/graphql_read/generated/search_page.g.dart';
import 'package:quwoquan_app/service/api_edge/graphql_read/persisted_query_execution/application/public/persisted_search_page_query.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_contracts/generated/gateway_contracts.dart';

typedef PersistedQueryInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// `SearchPage` signed persisted GraphQL 的 gateway-owned Remote adapter。
final class RemotePersistedSearchPageQuery implements PersistedSearchPageQuery {
  const RemotePersistedSearchPageQuery({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedSearchPageGraphQLClient client;
  final PersistedQueryInvocationContextFactory invocationContext;

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
