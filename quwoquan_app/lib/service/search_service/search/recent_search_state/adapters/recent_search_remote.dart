import 'package:quwoquan_app/runtime/transport/generated/search/search_request_page_ids.g.dart';
import 'package:quwoquan_app/service/search_service/search/recent_search_state/adapters/recent_search_entry_mapper.dart';
import 'package:quwoquan_app/service/search_service/search/recent_search_state/application/recent_search_ports.dart';
import 'package:quwoquan_app/service/search_service/search/recent_search_state/application/public/recent_search_entry_view.dart';
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
  Future<List<RecentSearchEntryView>> listRecentSearches(
    ListRecentSearchesQuery query,
  ) async {
    final slice = await client.searchRecentSearchStateListRecentSearches(
      query,
      context: invocationContext(SearchRequestPageIds.listRecentSearches),
    );
    return slice.items.map(recentSearchEntryFromWire).toList(growable: false);
  }

  @override
  Future<RecentSearchEntryView> upsertRecentSearch(
    UpsertRecentSearchCommand command,
  ) async {
    final wire = await client.searchRecentSearchStateUpsertRecentSearch(
      command,
      context: invocationContext(SearchRequestPageIds.upsertRecentSearch),
    );
    return recentSearchEntryFromWire(wire);
  }

  @override
  Future<void> deleteRecentSearch(DeleteRecentSearchCommand command) async {
    await client.searchRecentSearchStateDeleteRecentSearch(
      command,
      context: invocationContext(SearchRequestPageIds.deleteRecentSearch),
    );
  }

  @override
  Future<void> clearRecentSearches(ClearRecentSearchesCommand command) async {
    await client.searchRecentSearchStateClearRecentSearches(
      command,
      context: invocationContext(SearchRequestPageIds.clearRecentSearches),
    );
  }
}
