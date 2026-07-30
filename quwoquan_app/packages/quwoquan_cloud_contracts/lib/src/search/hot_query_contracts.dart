import '../operation_request_payload.dart';
part '../generated/requests/search/hot_query_contracts.requests.g.dart';



final class HotQuery {
  const HotQuery({required this.query, required this.relevance});

  final String query;
  final double relevance;
}

final class HotQuerySlice {
  const HotQuerySlice({required this.items});

  final List<HotQuery> items;
}

abstract interface class SearchHotQueryReader {
  Future<HotQuerySlice> listHotQueries(ListHotQueriesQuery query);
}



HotQuerySlice decodeHotQuerySlice(Object? value) {
  final Object? rawItems = switch (value) {
    Map() => value['items'],
    List() => value,
    _ => null,
  };
  if (rawItems is! List) {
    throw const FormatException('HotQuerySlice.items must be a list');
  }
  return HotQuerySlice(
    items: rawItems.map(_decodeHotQuery).toList(growable: false),
  );
}

HotQuery _decodeHotQuery(Object? value) {
  if (value is! Map) {
    throw const FormatException('HotQuery must be an object');
  }
  final query = value['query']?.toString().trim() ?? '';
  final relevance = value['relevance'];
  if (query.isEmpty || relevance is! num) {
    throw const FormatException(
      'HotQuery requires a non-empty query and numeric relevance',
    );
  }
  return HotQuery(query: query, relevance: relevance.toDouble());
}
