import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// SearchRequestFact 派生的热词读面（ListHotQueries）。
abstract interface class SearchHotQueryReader {
  Future<SearchTermHeatSlice> listHotQueries(ListHotQueriesQuery query);
}
