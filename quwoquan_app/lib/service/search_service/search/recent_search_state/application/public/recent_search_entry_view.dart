import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_query_contract.dart';

/// RecentSearchState 对外暴露的 App 值对象。
final class RecentSearchEntryView {
  const RecentSearchEntryView({
    required this.entryId,
    required this.query,
    required this.scope,
    this.facet,
    required this.updatedAt,
  });

  final String entryId;
  final String query;
  final SearchScope scope;
  final String? facet;
  final DateTime updatedAt;

  static String buildEntryId({
    required String query,
    required SearchScope scope,
    String? facet,
  }) {
    final normalizedQuery = query.trim().toLowerCase();
    final normalizedFacet = (facet ?? '').trim().toLowerCase();
    return Uri.encodeComponent(
      '${scope.wireValue}::$normalizedQuery::$normalizedFacet',
    );
  }
}
