import 'package:quwoquan_app/service/search_service/search/search_request_fact/application/search_hot_query_reader.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../runtime/fixtures/object_scenario_seed_reader.dart';
/// local_contract 热词读模型：只消费 search-service canonical 场景。
final class SearchHotQueryTypedDouble implements SearchHotQueryReader {
  SearchHotQueryTypedDouble() : _items = _loadItems();

  final List<SearchTermHeatItem> _items;

  @override
  Future<SearchTermHeatSlice> listHotQueries(ListHotQueriesQuery query) async {
    return SearchTermHeatSlice(
      items: _items.take(query.limit).toList(growable: false),
    );
  }

  static List<SearchTermHeatItem> _loadItems() {
    final decoded = objectScenarioSeedReader.document('search');
    final seedSets = decoded['seedSets'] as Map<String, dynamic>? ?? const {};
    final core = seedSets['search_hot_queries_core'] as Map<String, dynamic>?;
    final rawItems = core?['hot_queries'] as List?;
    if (rawItems == null) {
      throw StateError(
        'search fixture is missing search_hot_queries_core.hot_queries',
      );
    }
    final items = rawItems
        .map((item) {
          final map = item as Map<String, dynamic>;
          final query = map['query']?.toString().trim() ?? '';
          final relevance = map['relevance'];
          if (query.isEmpty || relevance is! num) {
            throw const FormatException('invalid search hot query fixture');
          }
          return SearchTermHeatItem(
            query: query,
            relevance: relevance.toDouble(),
          );
        })
        .toList(growable: false);
    items.sort((left, right) => right.relevance.compareTo(left.relevance));
    return items;
  }
}
