import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// App-owned Search query port. Wire requests and responses remain generated
/// exclusively from search-service contracts.
abstract interface class CanonicalSearchQueryFacet {
  Future<SearchResponseView> search(
    CanonicalSearchQuery query, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  });
}

abstract interface class SearchHotQueryReader {
  Future<SearchTermHeatSlice> listHotQueries(ListHotQueriesQuery query);
}

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

abstract interface class SearchFeedbackCommandWriter {
  Future<SearchFeedbackAck> reportSearchFeedback(
    ReportSearchFeedbackCommand command,
  );
}
