import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/service/search_service/search/recent_search_state/application/public/recent_search_entry_view.dart';
import 'package:quwoquan_app/service/search_service/search/recent_search_state/application/public/recent_search_history_store.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_query_contract.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Persona 隔离的最近搜索表现层缓存与持久化重试回执。
///
/// 登录态始终以 search-service 为权威，本地只负责离线可见性与恢复未完成命令。
final class SearchRecentHistoryStore implements RecentSearchHistoryStore {
  SearchRecentHistoryStore({required String actorNamespace})
    : _storageKey =
          '$storageKeyPrefix${sha256.convert(utf8.encode(_requiredActorNamespace(actorNamespace)))}';

  static const String storageKeyPrefix = 'global_search_recent_entries_';
  static const String _schema = 'search_recent_history_cache';

  final String _storageKey;

  @override
  Future<RecentSearchHistorySnapshot> load() async {
    final preferences = await SharedPreferences.getInstance();
    final raw = preferences.getString(_storageKey);
    if (raw == null || raw.trim().isEmpty) {
      return const RecentSearchHistorySnapshot();
    }
    final Object? decoded = jsonDecode(raw);
    final object = _recentSearchCacheObject(decoded);
    if (object['schema'] != _schema) {
      throw const FormatException('recent search cache schema is invalid');
    }
    final rawEntries = object['entries'];
    if (rawEntries is! List) {
      throw const FormatException('recent search cache entries must be a list');
    }
    final pendingClear = object['pendingClear'];
    if (pendingClear is! bool) {
      throw const FormatException(
        'recent search cache pendingClear must be a bool',
      );
    }
    return RecentSearchHistorySnapshot(
      entries: rawEntries
          .map(_recentSearchEntryFromCacheObject)
          .toList(growable: false),
      pendingUpsertKeys: _recentSearchCacheStringSet(
        object['pendingUpsertKeys'],
        'pendingUpsertKeys',
      ),
      pendingDeleteKeys: _recentSearchCacheStringSet(
        object['pendingDeleteKeys'],
        'pendingDeleteKeys',
      ),
      pendingClear: pendingClear,
    );
  }

  @override
  Future<void> save(RecentSearchHistorySnapshot snapshot) async {
    final preferences = await SharedPreferences.getInstance();
    final encoded = jsonEncode(<String, Object?>{
      'schema': _schema,
      'entries': snapshot.entries
          .map(_recentSearchEntryCacheObject)
          .toList(growable: false),
      'pendingUpsertKeys': snapshot.pendingUpsertKeys.toList(growable: false),
      'pendingDeleteKeys': snapshot.pendingDeleteKeys.toList(growable: false),
      'pendingClear': snapshot.pendingClear,
    });
    final accepted = await preferences.setString(_storageKey, encoded);
    if (!accepted || preferences.getString(_storageKey) != encoded) {
      throw StateError('recent search cache persistence verification failed');
    }
  }

  @override
  Future<void> clear() async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.remove(_storageKey);
    if (preferences.containsKey(_storageKey)) {
      throw StateError('recent search cache cleanup verification failed');
    }
  }

  /// 账号进入不可逆 closed 终态后清理本机全部身份命名空间。
  ///
  /// 最近搜索可从各账号 Remote 权威重建；共享设备上宁可移除可重建缓存，也不能
  /// 保留无法再归属给已注销账号的本地 PII。
  static Future<void> clearAllNamespaces() async {
    final preferences = await SharedPreferences.getInstance();
    final keys = preferences
        .getKeys()
        .where((key) => key.startsWith(storageKeyPrefix))
        .toList(growable: false);
    for (final key in keys) {
      await preferences.remove(key);
    }
    final residualCount = preferences.getKeys().where((key) {
      return key.startsWith(storageKeyPrefix);
    }).length;
    if (residualCount != 0) {
      throw StateError(
        'recent search cache cleanup left $residualCount residual keys',
      );
    }
  }
}

String _requiredActorNamespace(String value) {
  final normalized = value.trim();
  if (normalized.isEmpty) {
    throw ArgumentError.value(value, 'actorNamespace', 'must not be empty');
  }
  return normalized;
}

Map<String, Object?> _recentSearchCacheObject(Object? raw) {
  if (raw is! Map) {
    throw const FormatException('recent search cache must be an object');
  }
  final object = <String, Object?>{};
  for (final entry in raw.entries) {
    if (entry.key is! String) {
      throw const FormatException('recent search cache keys must be strings');
    }
    object[entry.key as String] = entry.value;
  }
  return object;
}

Set<String> _recentSearchCacheStringSet(Object? raw, String field) {
  if (raw is! List) {
    throw FormatException('recent search cache $field must be a list');
  }
  return Set<String>.unmodifiable(
    raw.map((item) {
      if (item is! String || item.trim().isEmpty) {
        throw FormatException(
          'recent search cache $field entries must be non-empty strings',
        );
      }
      return item.trim();
    }),
  );
}

RecentSearchEntryView _recentSearchEntryFromCacheObject(Object? raw) {
  if (raw is! Map) {
    throw const FormatException('recent search cache entry must be an object');
  }
  final object = <String, Object?>{};
  for (final entry in raw.entries) {
    if (entry.key is! String) {
      throw const FormatException(
        'recent search cache entry keys must be strings',
      );
    }
    object[entry.key as String] = entry.value;
  }
  final query = object['query'] is String
      ? (object['query'] as String).trim()
      : '';
  if (query.isEmpty) {
    throw const FormatException('recent search cache query is required');
  }
  final scope = SearchScope.fromWire(
    object['scope'] is String ? object['scope'] as String : 'all',
  );
  final facet = object['facet'] is String
      ? (object['facet'] as String).trim()
      : null;
  final updatedAt = object['updatedAt'] is String
      ? DateTime.tryParse(object['updatedAt'] as String)
      : null;
  if (updatedAt == null) {
    throw const FormatException('recent search cache updatedAt is invalid');
  }
  final cachedEntryId = object['entryId'] is String
      ? (object['entryId'] as String).trim()
      : '';
  return RecentSearchEntryView(
    entryId: cachedEntryId.isNotEmpty
        ? cachedEntryId
        : RecentSearchEntryView.buildEntryId(
            query: query,
            scope: scope,
            facet: facet,
          ),
    query: query,
    scope: scope,
    facet: facet?.isEmpty == true ? null : facet,
    updatedAt: updatedAt,
  );
}

Map<String, Object?> _recentSearchEntryCacheObject(
  RecentSearchEntryView entry,
) {
  return <String, Object?>{
    'entryId': entry.entryId,
    'query': entry.query,
    'scope': entry.scope.wireValue,
    'facet': entry.facet,
    'updatedAt': entry.updatedAt.toUtc().toIso8601String(),
  };
}
