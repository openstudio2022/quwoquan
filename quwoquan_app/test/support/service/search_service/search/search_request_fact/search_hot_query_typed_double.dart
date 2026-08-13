import 'package:quwoquan_app/service/search_service/search/search_request_fact/application/search_hot_query_reader.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// local_contract 热词读模型：只承载本对象所需的最小 typed example。
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
    final items = <SearchTermHeatItem>[
      const SearchTermHeatItem(query: '旅行摄影', relevance: 9.8),
      const SearchTermHeatItem(query: '城市漫步', relevance: 9.1),
      const SearchTermHeatItem(query: '周末徒步', relevance: 8.7),
      const SearchTermHeatItem(query: '咖啡地图', relevance: 8.2),
      const SearchTermHeatItem(query: '日落机位', relevance: 7.9),
      const SearchTermHeatItem(query: '博物馆展览', relevance: 7.6),
      const SearchTermHeatItem(query: '露营装备', relevance: 7.3),
      const SearchTermHeatItem(query: '城市夜景', relevance: 7.0),
      const SearchTermHeatItem(query: '古镇漫游', relevance: 6.7),
      const SearchTermHeatItem(query: '海边骑行', relevance: 6.4),
      const SearchTermHeatItem(query: '毕业旅行', relevance: 6.1),
    ];
    items.sort((left, right) => right.relevance.compareTo(left.relevance));
    return items;
  }
}
