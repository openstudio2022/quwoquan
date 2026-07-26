import '../operation_request_payload.dart';

/// 搜索默认页热词查询。数据来自 search-service term-heat 读模型，
/// 客户端不维护第二套业务词表。
final class ListHotQueriesQuery {
  ListHotQueriesQuery({this.limit = 10}) {
    if (limit <= 0 || limit > 20) {
      throw ArgumentError.value(limit, 'limit', 'must be between 1 and 20');
    }
  }

  final int limit;
}

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

CloudOperationRequestPayload encodeListHotQueriesQuery(
  ListHotQueriesQuery query,
) => CloudOperationRequestPayload(
  queryParameters: <String, String>{'limit': '${query.limit}'},
);

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
