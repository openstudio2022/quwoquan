import 'package:quwoquan_app/cloud/runtime/generated/search/search_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'recent_search_remote.dart' show SearchInvocationContextFactory;

/// search term-heat 的 production Remote reader。
///
/// path/auth/deadline/decoder 由 generated client/executor 承担。
final class RemoteSearchHotQueryReader implements SearchHotQueryReader {
  const RemoteSearchHotQueryReader({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final SearchInvocationContextFactory invocationContext;

  @override
  Future<HotQuerySlice> listHotQueries(ListHotQueriesQuery query) {
    return client.searchQueryListHotQueries(
      query,
      context: invocationContext(SearchRequestPageIds.listHotQueries),
    );
  }
}
