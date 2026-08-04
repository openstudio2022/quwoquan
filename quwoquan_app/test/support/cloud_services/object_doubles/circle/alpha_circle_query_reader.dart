import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../object_scenario_seed_reader.dart';
import 'alpha_post_placement_writer.dart';

/// Alpha/test only Circle query adapter.
///
/// It replays immutable alpha fixtures into pure contracts. It deliberately
/// has no dependency on App DTOs, Remote adapters, or retired repositories.
final class AlphaCircleQueryReader
    implements CircleQueryReader, CircleDiscoveryFeedQueryReader {
  AlphaCircleQueryReader({
    ObjectScenarioSeedReader? fixtures,
    AlphaCirclePostPlacementStore? placements,
  }) : _fixtures = fixtures ?? objectScenarioSeedReader,
       _placements = placements ?? AlphaCirclePostPlacementStore();

  final ObjectScenarioSeedReader _fixtures;
  final AlphaCirclePostPlacementStore _placements;

  @override
  Future<CirclePageSlice> list(CircleListQuery query) async {
    final items = _circles.where((circle) {
      return _matchesOptional(circle.category, query.category) &&
          _matchesOptional(circle.domainId, query.domainId);
    });
    return _pageCircles(items, cursor: query.cursor, limit: query.limit);
  }

  @override
  Future<CircleSearchResultView> search(CircleSearchQuery query) async {
    final normalized = query.query.trim().toLowerCase();
    final items = _circles.where((circle) {
      final matchesText =
          normalized.isEmpty ||
          circle.name.toLowerCase().contains(normalized) ||
          (circle.description?.toLowerCase().contains(normalized) ?? false) ||
          (circle.tags ?? const <String>[]).any(
            (tag) => tag.toLowerCase().contains(normalized),
          );
      return matchesText &&
          _matchesOptional(circle.category, query.categoryId) &&
          _matchesOptional(circle.subCategory, query.subCategory);
    });
    final page = _pageCircles(items, cursor: query.cursor, limit: query.limit);
    return CircleSearchResultView(
      items: page.items
          .map(
            (circle) => CircleSearchItemView(
              circleId: circle.id,
              name: circle.name,
              description: circle.description,
              coverUrl: circle.coverUrl,
              categoryId: circle.category,
              subCategory: circle.subCategory,
              domainId: circle.domainId,
              kind: circle.kind,
              displaySubjectType: circle.displaySubjectType,
              memberCount: circle.memberCount,
              postCount: circle.postCount,
              highlightText: normalized.isEmpty ? null : circle.name,
              matchedField: normalized.isEmpty ? null : 'name',
            ),
          )
          .toList(growable: false),
      facetBuckets: const <CircleFacetBucketView>[],
      cursor: page.cursor,
    );
  }

  @override
  Future<Circle> get(CircleDetailQuery query) async {
    final circle = _circleById(query.circleId);
    if (circle == null) {
      throw StateError('alpha circle fixture is missing: ${query.circleId}');
    }
    return circle;
  }

  @override
  Future<CircleFeedPageSlice> feed(CircleFeedQuery query) async {
    final items = _feedItemsForCircle(query.circleId, type: query.type);
    return _pageFeed(items, cursor: query.cursor, limit: query.limit);
  }

  @override
  Future<CircleStatsWire> stats(CircleStatsQuery query) async {
    final raw = _statsByCircleId[query.circleId];
    if (raw == null) {
      throw StateError(
        'alpha circle stats fixture is missing: ${query.circleId}',
      );
    }
    return CircleStatsWire(
      circleId: _text(raw['circleId']),
      memberCount: _integer(raw['memberCount']),
      postCount: _integer(raw['postCount']),
      discussionCount: _integer(raw['discussionCount']),
      weeklyActiveCount: _integer(raw['weeklyActiveCount']),
      likeCount: _integer(raw['likeCount']),
      storageUsedBytes: _integer(raw['storageUsedBytes']),
      storageQuotaBytes: _integer(raw['storageQuotaBytes']),
    );
  }

  @override
  Future<CircleImpactSummary> impact(CircleImpactQuery query) async {
    final raw = _impactsByCircleId[query.circleId];
    if (raw == null) {
      return CircleImpactSummary(
        circleId: query.circleId,
        total: 0,
        items: const <CircleImpactItem>[],
      );
    }
    return decodeCircleImpactSummary(raw);
  }

  @override
  Future<CircleDiscoveryFeedPageSlice> listDiscoveryFeed(
    CircleDiscoveryFeedQuery query,
  ) async {
    final circles = (await list(
      CircleListQuery(
        category: query.category,
        cursor: query.cursor,
        limit: query.limit,
        sort: query.sort,
      ),
    )).items;
    final items = <CircleFeedItemView>[];
    for (final circle in circles) {
      if (items.length >= query.limit) break;
      items.addAll(
        _feedItemsForCircle(circle.id).take(query.limit - items.length),
      );
    }
    return CircleDiscoveryFeedPageSlice(
      circles: circles,
      items: items,
      cursor: circles.length == query.limit ? circles.last.id : null,
    );
  }

  List<Circle> get _circles {
    final raw = _list(
      _fixtures.requireSeedSet('circle', 'circle_core')['circles'],
    );
    return raw.map(_circleProjection).toList(growable: false);
  }

  Map<String, Map<Object?, Object?>> get _statsByCircleId {
    final raw = _list(
      _fixtures.requireSeedSet('circle', 'circle_profile_core')['stats'],
    );
    return <String, Map<Object?, Object?>>{
      for (final item in raw) _text(item['circleId']): item,
    };
  }

  Map<String, Object?> get _impactsByCircleId {
    final raw = _object(
      _fixtures.requireSeedSet('circle', 'circle_profile_core')['impacts'],
    );
    return raw.map((key, value) => MapEntry(key.toString(), value));
  }

  Map<String, Map<Object?, Object?>> get _postsById {
    final raw = _list(
      _fixtures.requireSeedSet('content', 'content_discovery_core')['posts'],
    );
    return <String, Map<Object?, Object?>>{
      for (final item in raw) _text(item['postId']): item,
    };
  }

  List<CircleFeedItemView> _feedItemsForCircle(
    String circleId, {
    String? type,
  }) {
    final placements = _list(
      _fixtures.requireSeedSet('circle', 'circle_profile_core')['placements'],
    );
    final normalizedType = type?.trim();
    return placements
        .where(
          (placement) =>
              _text(placement['circleId']) == circleId &&
              _text(placement['status']) == 'active',
        )
        .map((placement) {
          final postId = _text(placement['postId']);
          final post = _postsById[postId];
          if (post == null) return null;
          final contentType = _textOr(post['contentType'], 'image');
          if (normalizedType != null &&
              normalizedType.isNotEmpty &&
              contentType != normalizedType) {
            return null;
          }
          final placementId = 'alpha-placement-$circleId-$postId';
          final presentation = _placements.presentation(placementId);
          if (presentation.removed) return null;
          return _feedItem(
            circleId: circleId,
            placementId: placementId,
            raw: post,
            pinned: presentation.pinned,
            featured: presentation.featured,
          );
        })
        .whereType<CircleFeedItemView>()
        .toList(growable: false);
  }

  CirclePageSlice _pageCircles(
    Iterable<Circle> values, {
    required String? cursor,
    required int limit,
  }) {
    final all = values.toList(growable: false);
    final start = _cursorIndex(all.map((item) => item.id), cursor);
    final items = all.skip(start).take(limit).toList(growable: false);
    return CirclePageSlice(
      items: items,
      cursor: start + items.length < all.length && items.isNotEmpty
          ? items.last.id
          : null,
    );
  }

  CircleFeedPageSlice _pageFeed(
    List<CircleFeedItemView> values, {
    required String? cursor,
    required int limit,
  }) {
    final start = _cursorIndex(values.map((item) => item.placementId), cursor);
    final items = values.skip(start).take(limit).toList(growable: false);
    return CircleFeedPageSlice(
      items: items,
      cursor: start + items.length < values.length && items.isNotEmpty
          ? items.last.placementId
          : null,
    );
  }

  Circle? _circleById(String circleId) {
    for (final circle in _circles) {
      if (circle.id == circleId) return circle;
    }
    return null;
  }
}

Circle _circleProjection(Map<Object?, Object?> raw) {
  return Circle(
    id: _text(raw['id']),
    name: _text(raw['name']),
    description: _optionalText(raw['description']),
    coverUrl: _optionalText(raw['coverUrl']),
    iconUrl: _optionalText(raw['avatarUrl']),
    ownerId: _text(raw['ownerId']),
    ownerDisplayNameSnapshot: _optionalText(raw['ownerDisplayNameSnapshot']),
    category: _optionalText(raw['categoryId']),
    subCategory: _optionalText(raw['subCategory']),
    tags: _stringList(raw['tags']),
    memberCount: _integer(raw['memberCount']),
    postCount: _integer(raw['postCount']),
    weeklyActiveCount: _integer(raw['weeklyActiveCount']),
    version: _integer(raw['version']) == 0 ? 1 : _integer(raw['version']),
    status: CircleStatus.fromWire(raw['status'] ?? 'active', 'Circle.status'),
    visibility: CircleVisibility.fromWire(
      raw['visibility'] ?? 'public',
      'Circle.visibility',
    ),
    joinPolicy: CircleJoinPolicy.fromWire(
      raw['joinPolicy'] ?? 'open',
      'Circle.joinPolicy',
    ),
    // `circleType` 是 flagship/niche 等场景展示原型，不是 canonical CircleKind；
    // 只有 canonical `kind` 可以进入强类型边界。
    kind: CircleKind.fromWire(raw['kind'] ?? 'interest', 'Circle.kind'),
    displaySubjectType: CircleDisplaySubjectType.fromWire(
      raw['displaySubjectType'] ?? 'circle',
      'Circle.displaySubjectType',
    ),
    followEnabled: _boolean(raw['followEnabled'], fallback: true),
    defaultPublicGroupId: _optionalText(raw['defaultPublicGroupId']),
    autoSyncChat: _boolean(raw['autoSyncChat'], fallback: true),
    storageUsedBytes: _integer(raw['storageUsedBytes']),
    storageQuotaBytes: _integer(raw['storageQuotaBytes']),
    domainId: _optionalText(raw['domainId']),
    linkedHomepageId: _optionalText(raw['linkedHomepageId']),
    linkedHomepageType: _optionalText(raw['linkedHomepageType']) == null
        ? null
        : HomepageType.fromWire(
            raw['linkedHomepageType'],
            'Circle.linkedHomepageType',
          ),
    linkedHomepageTitle: _optionalText(raw['linkedHomepageTitle']),
    createdAt: _date(raw['createdAt']) ?? _epoch,
    updatedAt: _date(raw['updatedAt']) ?? _epoch,
  );
}

CircleFeedItemView _feedItem({
  required String circleId,
  required String placementId,
  required Map<Object?, Object?> raw,
  required bool pinned,
  required bool featured,
}) {
  final contentType = _textOr(raw['contentType'], 'image');
  final mediaUrls = _stringList(raw['mediaUrls']);
  return CircleFeedItemView(
    circleId: circleId,
    placementId: placementId,
    postId: _text(raw['postId']),
    contentType: contentType,
    contentIdentity: _optionalText(raw['contentIdentity']),
    assistantUsePolicy: _optionalText(raw['assistantUsePolicy']),
    authorId: _optionalText(raw['authorId']),
    authorDisplayName: _optionalText(raw['authorDisplayName']),
    authorAvatarUrl: _optionalText(raw['authorAvatarUrl']),
    authorBackgroundUrl: _optionalText(raw['authorBackgroundUrl']),
    authorRoleLabel: _optionalText(raw['authorRoleLabel']),
    authorIdentityTags: _stringList(raw['authorIdentityTags']),
    authorVerified: _boolean(raw['authorVerified'], fallback: false),
    title: _optionalText(raw['title']),
    body: _optionalText(raw['body']),
    summary: _optionalText(raw['summary']),
    coverUrl: _optionalText(raw['coverUrl']),
    imageUrls: mediaUrls,
    videoUrl: _optionalText(raw['videoUrl']),
    thumbnailUrl: _optionalText(raw['thumbnailUrl']),
    width: _integerOrNull(raw['width']),
    height: _integerOrNull(raw['height']),
    durationMs: _integerOrNull(raw['durationMs']),
    likeCount: _integer(raw['likeCount']),
    commentCount: _integer(raw['commentCount']),
    shareCount: _integer(raw['shareCount']),
    createdAt: _date(raw['createdAt']),
    updatedAt: _date(raw['updatedAt']),
    publishedAt: _date(raw['publishedAt']),
    contentVertical: _optionalText(raw['contentVertical']),
    recallPath: _optionalText(raw['recallPath']),
    supplySource: _optionalText(raw['supplySource']),
    pinned: pinned,
    featured: featured,
  );
}

final DateTime _epoch = DateTime.fromMillisecondsSinceEpoch(0, isUtc: true);

List<Map<Object?, Object?>> _list(Object? value) {
  if (value is! List) return const <Map<Object?, Object?>>[];
  return value
      .whereType<Map>()
      .map((item) => Map<Object?, Object?>.from(item))
      .toList(growable: false);
}

Map<Object?, Object?> _object(Object? value) {
  if (value is! Map) return const <Object?, Object?>{};
  return Map<Object?, Object?>.from(value);
}

bool _matchesOptional(String? actual, String? expected) =>
    expected == null || expected.trim().isEmpty || actual == expected;

int _cursorIndex(Iterable<String> values, String? cursor) {
  final normalized = cursor?.trim();
  if (normalized == null || normalized.isEmpty) return 0;
  var index = 0;
  for (final value in values) {
    if (value == normalized) return index + 1;
    index += 1;
  }
  return 0;
}

String _text(Object? value) => value?.toString().trim() ?? '';

String _textOr(Object? value, String fallback) {
  final text = _text(value);
  return text.isEmpty ? fallback : text;
}

String? _optionalText(Object? value) {
  final text = _text(value);
  return text.isEmpty ? null : text;
}

int _integer(Object? value) => value is num ? value.toInt() : 0;

int? _integerOrNull(Object? value) => value is num ? value.toInt() : null;

bool _boolean(Object? value, {required bool fallback}) =>
    value is bool ? value : fallback;

DateTime? _date(Object? value) =>
    value is String ? DateTime.tryParse(value)?.toUtc() : null;

List<String> _stringList(Object? value) {
  if (value is! List) return const <String>[];
  return value.map(_optionalText).whereType<String>().toList(growable: false);
}
