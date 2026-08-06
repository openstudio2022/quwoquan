import 'package:quwoquan_app/service/search_service/search/recent_search_state/application/public/recent_search_entry_view.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_query_contract.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show RecentSearchEntryWire;

RecentSearchEntryView recentSearchEntryFromWire(RecentSearchEntryWire wire) {
  final query = wire.query.trim();
  final scope = SearchScope.fromWire(wire.scope);
  final facetTrim = wire.facet?.trim();
  return RecentSearchEntryView(
    entryId: wire.entryId.trim().isNotEmpty
        ? wire.entryId.trim()
        : RecentSearchEntryView.buildEntryId(
            query: query,
            scope: scope,
            facet: facetTrim,
          ),
    query: query,
    scope: scope,
    facet: facetTrim?.isEmpty == true ? null : facetTrim,
    updatedAt: wire.updatedAt,
  );
}
