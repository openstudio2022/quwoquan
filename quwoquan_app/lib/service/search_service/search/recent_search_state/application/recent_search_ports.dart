import 'package:quwoquan_app/service/search_service/search/recent_search_state/application/public/recent_search_entry_view.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

abstract interface class RecentSearchQuery {
  Future<List<RecentSearchEntryView>> listRecentSearches(
    ListRecentSearchesQuery query,
  );
}

abstract interface class RecentSearchCommandWriter {
  Future<RecentSearchEntryView> upsertRecentSearch(
    UpsertRecentSearchCommand command,
  );

  Future<void> deleteRecentSearch(DeleteRecentSearchCommand command);

  Future<void> clearRecentSearches(ClearRecentSearchesCommand command);
}
