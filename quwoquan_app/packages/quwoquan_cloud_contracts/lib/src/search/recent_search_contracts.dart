import '../operation_request_payload.dart';
part '../generated/requests/search/recent_search_contracts.requests.g.dart';

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

String? _optional(String? value) {
  final normalized = value?.trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}
