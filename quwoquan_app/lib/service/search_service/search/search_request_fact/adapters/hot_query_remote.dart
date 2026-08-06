import 'package:quwoquan_app/runtime/transport/generated/search/search_request_page_ids.g.dart';
import 'package:quwoquan_app/service/search_service/search/search_request_fact/application/search_hot_query_reader.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
/// 热词读面对象的 invocation context 工厂。
typedef SearchHotQueryInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// search term-heat 的 production Remote reader。
///
/// path/auth/deadline/decoder 由 generated client/executor 承担。
final class RemoteSearchHotQueryReader implements SearchHotQueryReader {
  const RemoteSearchHotQueryReader({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final SearchHotQueryInvocationContextFactory invocationContext;

  @override
  Future<SearchTermHeatSlice> listHotQueries(ListHotQueriesQuery query) {
    return client.searchSearchRequestFactListHotQueries(
      query,
      context: invocationContext(SearchRequestPageIds.listHotQueries),
    );
  }
}
