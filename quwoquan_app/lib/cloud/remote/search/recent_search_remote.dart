import 'package:quwoquan_app/cloud/runtime/generated/search/search_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef SearchInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// RecentSearchState 的 production Remote adapter。
///
/// path、auth、deadline、retry、Idempotency-Key 与 decoder 由 generated
/// client/executor 承担；entryId 由服务端从语义键派生，本层不生成任何标识。
final class RemoteRecentSearchAdapter
    implements RecentSearchQuery, RecentSearchCommandWriter {
  const RemoteRecentSearchAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final SearchInvocationContextFactory invocationContext;

  @override
  Future<RecentSearchEntrySlice> listRecentSearches(
    ListRecentSearchesQuery query,
  ) {
    return client.searchRecentSearchStateListRecentSearches(
      query,
      context: invocationContext(SearchRequestPageIds.listRecentSearches),
    );
  }

  @override
  Future<RecentSearchEntry> upsertRecentSearch(
    UpsertRecentSearchCommand command,
  ) {
    return client.searchRecentSearchStateUpsertRecentSearch(
      command,
      context: invocationContext(SearchRequestPageIds.upsertRecentSearch),
    );
  }

  @override
  Future<void> deleteRecentSearch(DeleteRecentSearchCommand command) {
    return client.searchRecentSearchStateDeleteRecentSearch(
      command,
      context: invocationContext(SearchRequestPageIds.deleteRecentSearch),
    );
  }

  @override
  Future<void> clearRecentSearches(ClearRecentSearchesCommand command) {
    return client.searchRecentSearchStateClearRecentSearches(
      command,
      context: invocationContext(SearchRequestPageIds.clearRecentSearches),
    );
  }
}
