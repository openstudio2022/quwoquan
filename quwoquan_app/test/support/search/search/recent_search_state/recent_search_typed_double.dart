import 'dart:convert' show utf8;

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/search/search/recent_search_state/application/recent_search_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
/// RecentSearchState 对象级替身：与服务端对象模型保持同一语义键和有界顺序。
///
/// 只在测试树内注入的内存 adapter；production 依赖图不可达。
final class RecentSearchTypedDouble
    implements RecentSearchQuery, RecentSearchCommandWriter {
  RecentSearchTypedDouble({DateTime Function()? clock})
    : _clock = clock ?? (() => DateTime.now().toUtc());

  static const int _maxEntries = 12;

  final DateTime Function() _clock;
  final List<RecentSearchEntryWire> _entries = <RecentSearchEntryWire>[];

  @override
  Future<RecentSearchEntrySlice> listRecentSearches(
    ListRecentSearchesQuery query,
  ) async {
    final scope = query.scope;
    return RecentSearchEntrySlice(
      items: _entries
          .where((entry) => scope == null || entry.scope == scope)
          .toList(growable: false),
    );
  }

  @override
  Future<RecentSearchEntryWire> upsertRecentSearch(
    UpsertRecentSearchCommand command,
  ) async {
    final entryId = _deriveEntryId(command);
    final existingIndex = _entries.indexWhere(
      (entry) => entry.entryId == entryId,
    );
    if (existingIndex == 0) {
      return _entries.first;
    }
    if (existingIndex > 0) {
      _entries.removeAt(existingIndex);
    }
    final entry = RecentSearchEntryWire(
      entryId: entryId,
      query: command.query,
      scope: command.scope,
      facet: command.facet,
      updatedAt: _clock(),
    );
    _entries.insert(0, entry);
    if (_entries.length > _maxEntries) {
      _entries.removeRange(_maxEntries, _entries.length);
    }
    return entry;
  }

  @override
  Future<void> deleteRecentSearch(DeleteRecentSearchCommand command) async {
    _entries.removeWhere((entry) => entry.entryId == command.entryId);
  }

  @override
  Future<void> clearRecentSearches(ClearRecentSearchesCommand command) async {
    final scope = command.scope;
    if (scope == null) {
      _entries.clear();
      return;
    }
    _entries.removeWhere((entry) => entry.scope == scope);
  }

  String _deriveEntryId(UpsertRecentSearchCommand command) {
    final scope = command.scope.trim().toLowerCase();
    final facet = command.facet?.trim() ?? '';
    final query = command.query.trim().toLowerCase();
    final digest = sha256.convert(
      utf8.encode('$scope\u0000$facet\u0000$query'),
    );
    final shortDigest = digest.bytes
        .take(8)
        .map((byte) => byte.toRadixString(16).padLeft(2, '0'))
        .join();
    return 'recent_$shortDigest';
  }
}
