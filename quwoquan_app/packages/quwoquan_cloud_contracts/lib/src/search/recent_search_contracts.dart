import '../operation_request_payload.dart';

/// RecentSearchState 对象级 typed 契约（search 域）。
/// entryId 由服务端从语义键（scope+facet+normalized query）派生，
/// 客户端不生成、不提交条目标识以外的版本信息。

final class ListRecentSearchesQuery {
  ListRecentSearchesQuery({String? scope}) : scope = _optional(scope);

  final String? scope;
}

final class UpsertRecentSearchCommand {
  UpsertRecentSearchCommand({
    required String query,
    required String scope,
    String? facet,
  }) : query = _required(query, 'query'),
       scope = _required(scope, 'scope'),
       facet = _optional(facet);

  final String query;
  final String scope;
  final String? facet;
}

final class DeleteRecentSearchCommand {
  DeleteRecentSearchCommand({required String entryId})
    : entryId = _required(entryId, 'entryId');

  final String entryId;
}

final class ClearRecentSearchesCommand {
  ClearRecentSearchesCommand({String? scope}) : scope = _optional(scope);

  final String? scope;
}

final class RecentSearchEntry {
  const RecentSearchEntry({
    required this.entryId,
    required this.query,
    required this.scope,
    this.facet,
    this.updatedAt,
  });

  final String entryId;
  final String query;
  final String scope;
  final String? facet;
  final DateTime? updatedAt;
}

final class RecentSearchEntrySlice {
  const RecentSearchEntrySlice({required this.items});

  final List<RecentSearchEntry> items;
}

abstract interface class RecentSearchQuery {
  Future<RecentSearchEntrySlice> listRecentSearches(
    ListRecentSearchesQuery query,
  );
}

abstract interface class RecentSearchCommandWriter {
  Future<RecentSearchEntry> upsertRecentSearch(
    UpsertRecentSearchCommand command,
  );
  Future<void> deleteRecentSearch(DeleteRecentSearchCommand command);
  Future<void> clearRecentSearches(ClearRecentSearchesCommand command);
}

CloudOperationRequestPayload encodeListRecentSearchesQuery(
  ListRecentSearchesQuery query,
) => CloudOperationRequestPayload(
  queryParameters: <String, String>{'scope': ?query.scope},
);

CloudOperationRequestPayload encodeUpsertRecentSearchCommand(
  UpsertRecentSearchCommand command,
) => CloudOperationRequestPayload(
  body: <String, Object?>{
    'query': command.query,
    'scope': command.scope,
    'facet': ?command.facet,
  },
);

CloudOperationRequestPayload encodeDeleteRecentSearchCommand(
  DeleteRecentSearchCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'entryId': command.entryId},
);

CloudOperationRequestPayload encodeClearRecentSearchesCommand(
  ClearRecentSearchesCommand command,
) => CloudOperationRequestPayload(
  queryParameters: <String, String>{'scope': ?command.scope},
);

RecentSearchEntry decodeRecentSearchEntry(Object? value) {
  if (value is! Map) {
    throw const FormatException('RecentSearchEntry must be an object');
  }
  final map = value.map((key, item) => MapEntry(key.toString(), item));
  return RecentSearchEntry(
    entryId: _string(map, 'entryId'),
    query: _string(map, 'query'),
    scope: _string(map, 'scope'),
    facet: _optional(map['facet']?.toString()),
    updatedAt: DateTime.tryParse(map['updatedAt']?.toString() ?? '')?.toUtc(),
  );
}

RecentSearchEntrySlice decodeRecentSearchEntrySlice(Object? value) {
  if (value is! Map) {
    throw const FormatException('RecentSearchEntrySlice must be an object');
  }
  final items = value['items'];
  if (items is! List) {
    throw const FormatException('RecentSearchEntrySlice.items must be a list');
  }
  return RecentSearchEntrySlice(
    items: items.map(decodeRecentSearchEntry).toList(growable: false),
  );
}

/// DELETE 路由返回 {"status":"ok"}，typed 层只关心成功语义。
void decodeRecentSearchAck(Object? value) {
  if (value is! Map) {
    throw const FormatException('recent search ack must be an object');
  }
}

String _string(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$key must be a non-empty string');
  }
  return value.trim();
}

String _required(String value, String name) {
  final normalized = value.trim();
  if (normalized.isEmpty) throw ArgumentError.value(value, name, 'required');
  return normalized;
}

String? _optional(String? value) {
  final normalized = value?.trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}
