import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

abstract interface class RecentSearchQuery {
  Future<RecentSearchEntrySlice> listRecentSearches(
    ListRecentSearchesQuery query,
  );
}

abstract interface class RecentSearchCommandWriter {
  Future<RecentSearchEntryWire> upsertRecentSearch(
    UpsertRecentSearchCommand command,
  );

  Future<void> deleteRecentSearch(DeleteRecentSearchCommand command);

  Future<void> clearRecentSearches(ClearRecentSearchesCommand command);
}
