import 'dart:convert' show utf8;

import 'package:crypto/crypto.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../object_scenario_seed_reader.dart';

/// local_contract 热词读模型：只消费 search-service canonical 场景。
final class AlphaHotQueryReader implements SearchHotQueryReader {
  AlphaHotQueryReader() : _items = _loadItems();

  final List<HotQuery> _items;

  @override
  Future<HotQuerySlice> listHotQueries(ListHotQueriesQuery query) async {
    return HotQuerySlice(
      items: _items.take(query.limit).toList(growable: false),
    );
  }

  static List<HotQuery> _loadItems() {
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
          return HotQuery(query: query, relevance: relevance.toDouble());
        })
        .toList(growable: false);
    items.sort((left, right) => right.relevance.compareTo(left.relevance));
    return items;
  }
}

/// Alpha RecentSearchState：与服务端对象模型保持同一语义键和有界顺序。
///
/// 这是 alpha/test composition 注入的内存 adapter；production 依赖图不可达。
final class AlphaRecentSearchFacet
    implements RecentSearchQuery, RecentSearchCommandWriter {
  AlphaRecentSearchFacet({DateTime Function()? clock})
    : _clock = clock ?? (() => DateTime.now().toUtc());

  static const int _maxEntries = 12;

  final DateTime Function() _clock;
  final List<RecentSearchEntry> _entries = <RecentSearchEntry>[];

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
  Future<RecentSearchEntry> upsertRecentSearch(
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
    final entry = RecentSearchEntry(
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

/// Alpha SearchFeedbackFact append adapter。
///
/// 服务端以 (searchRequestId,eventType,objectId) 去重；alpha 使用同一语义键，
/// 保证重放不会产生第二条事实。
final class AlphaSearchFeedbackWriter implements SearchFeedbackCommandWriter {
  final Map<String, ReportSearchFeedbackCommand> _records =
      <String, ReportSearchFeedbackCommand>{};

  List<ReportSearchFeedbackCommand> get recorded =>
      _records.values.toList(growable: false);

  @override
  Future<SearchFeedbackAck> reportSearchFeedback(
    ReportSearchFeedbackCommand command,
  ) async {
    final key =
        '${command.searchRequestId}\u0000${command.eventType.wireValue}\u0000'
        '${command.objectId ?? ''}';
    _records.putIfAbsent(key, () => command);
    return const SearchFeedbackAck(accepted: true);
  }
}

/// Alpha canonical Search 适配器：仅消费 metadata fixture bundle，不调用 content
/// repository，也不在端侧合成 related terms。
final class AlphaCanonicalSearchFacet implements CanonicalSearchQueryFacet {
  @override
  Future<CanonicalSearchResult> search(
    CanonicalSearchQuery query, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    cancellation?.throwIfCancelled();
    final normalized = query.query.trim().toLowerCase();
    final posts = _contentPosts();
    final allowedTargets = query.objectTypes.toSet();
    final hits = <CanonicalSearchHit>[];
    for (final post in posts) {
      final contentType = _text(post['contentType'], fallback: 'image');
      final target = switch (contentType) {
        'article' => 'article',
        'video' => 'video',
        _ => 'photo',
      };
      if (allowedTargets.isNotEmpty && !allowedTargets.contains(target)) {
        continue;
      }
      final title = _text(post['title']);
      final summary = _text(post['summary']);
      final body = _text(post['body']);
      final author = _text(post['authorDisplayName']);
      final matched = <String>[
        title,
        summary,
        body,
        author,
      ].any((value) => value.toLowerCase().contains(normalized));
      if (!matched) {
        continue;
      }
      final postID = _text(post['postId']);
      if (postID.isEmpty) {
        continue;
      }
      final content = CanonicalSearchContentHit(
        postId: postID,
        contentType: contentType,
        contentIdentity: _optionalText(post['contentIdentity']),
        title: title.isEmpty ? postID : title,
        summary: _optionalText(post['summary']),
        coverUrl: _optionalText(post['coverUrl']),
        authorId: _optionalText(post['authorId']),
        authorDisplayName: _optionalText(post['authorDisplayName']),
        authorAvatarUrl: _optionalText(post['authorAvatarUrl']),
        categoryId: _optionalText(post['categoryId']),
        subCategory: _optionalText(post['subCategory']),
        likeCount: _integer(post['likeCount']),
        highlightText: title,
        matchedField: title.toLowerCase().contains(normalized)
            ? 'title'
            : 'body',
        publishedAt: _dateTime(post['publishedAt']),
      );
      hits.add(
        CanonicalSearchHit(
          target: target,
          objectId: postID,
          title: content.title ?? postID,
          snippet: content.summary,
          rankPosition: hits.length + 1,
          content: content,
        ),
      );
      if (hits.length >= query.limit) {
        break;
      }
    }
    final digest = sha256.convert(
      utf8.encode('${query.mode.wireValue}:$normalized'),
    );
    return CanonicalSearchResult(
      hits: hits,
      requestId: 'alpha_${digest.toString().substring(0, 16)}',
      rankingVersion: 'alpha-fixture',
    );
  }

  static List<Map<String, Object?>> _contentPosts() {
    final decoded = objectScenarioSeedReader.document('content');
    final seedSets = decoded['seedSets'];
    if (seedSets is! Map) {
      return const <Map<String, Object?>>[];
    }
    final discovery = seedSets['content_discovery_core'];
    if (discovery is! Map || discovery['posts'] is! List) {
      return const <Map<String, Object?>>[];
    }
    return (discovery['posts'] as List)
        .whereType<Map>()
        .map(
          (post) => post.map(
            (key, value) => MapEntry(key.toString(), value as Object?),
          ),
        )
        .toList(growable: false);
  }
}

String _text(Object? value, {String fallback = ''}) {
  final text = value?.toString().trim() ?? '';
  return text.isEmpty ? fallback : text;
}

String? _optionalText(Object? value) {
  final text = _text(value);
  return text.isEmpty ? null : text;
}

int _integer(Object? value) {
  if (value is num) {
    return value.toInt();
  }
  return int.tryParse(value?.toString() ?? '') ?? 0;
}

DateTime? _dateTime(Object? value) {
  final text = _text(value);
  return text.isEmpty ? null : DateTime.tryParse(text)?.toUtc();
}
