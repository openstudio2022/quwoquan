import 'dart:async';

import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class CircleDiscoveryFeedQueryTestDouble
    implements CircleDiscoveryFeedQueryReader {
  CircleDiscoveryFeedQueryTestDouble(this._resolve);

  final FutureOr<CircleDiscoveryFeedPageSlice> Function(
    CircleDiscoveryFeedQuery query,
  )
  _resolve;

  final List<CircleDiscoveryFeedQuery> receivedQueries =
      <CircleDiscoveryFeedQuery>[];

  @override
  Future<CircleDiscoveryFeedPageSlice> listDiscoveryFeed(
    CircleDiscoveryFeedQuery query,
  ) async {
    receivedQueries.add(query);
    return _resolve(query);
  }
}

final class CircleFeedQueryTestDouble implements CircleFeedQueryReader {
  CircleFeedQueryTestDouble(this._resolve);

  final FutureOr<CircleFeedPageSlice> Function(CircleFeedQuery query) _resolve;

  final List<CircleFeedQuery> receivedQueries = <CircleFeedQuery>[];

  @override
  Future<CircleFeedPageSlice> feed(CircleFeedQuery query) async {
    receivedQueries.add(query);
    return _resolve(query);
  }
}

class CircleQueryReaderTestDouble implements CircleQueryReader {
  CircleQueryReaderTestDouble({
    FutureOr<CirclePageSlice> Function(CircleListQuery query)? list,
    FutureOr<CircleSearchResultView> Function(CircleSearchQuery query)? search,
    FutureOr<Circle> Function(CircleDetailQuery query)? get,
    FutureOr<CircleFeedPageSlice> Function(CircleFeedQuery query)? feed,
    FutureOr<CircleStatsWire> Function(CircleStatsQuery query)? stats,
    FutureOr<CircleImpactSummary> Function(CircleImpactQuery query)? impact,
  }) : _handlers = _CircleQueryHandlers(
         list: list,
         search: search,
         get: get,
         feed: feed,
         stats: stats,
         impact: impact,
       );

  final _CircleQueryHandlers _handlers;

  @override
  Future<CirclePageSlice> list(CircleListQuery query) async =>
      _handlers.list?.call(query) ?? CirclePageSlice(items: <Circle>[]);

  @override
  Future<CircleSearchResultView> search(CircleSearchQuery query) async =>
      _handlers.search?.call(query) ??
      const CircleSearchResultView(
        items: <CircleSearchItemView>[],
        facetBuckets: <CircleFacetBucketView>[],
      );

  @override
  Future<Circle> get(CircleDetailQuery query) async =>
      _handlers.get?.call(query) ??
      buildCircleTestDoubleFixture(query.circleId);

  @override
  Future<CircleFeedPageSlice> feed(CircleFeedQuery query) async =>
      _handlers.feed?.call(query) ??
      CircleFeedPageSlice(items: <CircleFeedItemView>[]);

  @override
  Future<CircleStatsWire> stats(CircleStatsQuery query) async =>
      _handlers.stats?.call(query) ??
      CircleStatsWire(
        circleId: query.circleId,
        memberCount: 0,
        postCount: 0,
        discussionCount: 0,
        weeklyActiveCount: 0,
        likeCount: 0,
        storageUsedBytes: 0,
        storageQuotaBytes: 0,
      );

  @override
  Future<CircleImpactSummary> impact(CircleImpactQuery query) async =>
      _handlers.impact?.call(query) ??
      CircleImpactSummary(
        circleId: query.circleId,
        total: 0,
        items: const <CircleImpactItem>[],
      );
}

/// 构造满足 canonical `Circle` 契约所有必填字段的最小实例。
///
/// 只用于 local_contract 测试树；字段默认值取契约的中性态，测试需要特定形态时
/// 应传 `overrides` 或给 `CircleQueryReaderTestDouble` 注入 `get` handler。
Circle buildCircleTestDoubleFixture(
  String circleId, {
  String name = '测试圈子',
  String ownerId = 'fixture_user_owner',
  String? category,
  String? subCategory,
  String? domainId,
  CircleKind kind = CircleKind.interest,
  CircleDisplaySubjectType displaySubjectType = CircleDisplaySubjectType.circle,
  CircleStatus status = CircleStatus.active,
  CircleVisibility visibility = CircleVisibility.public,
  CircleJoinPolicy joinPolicy = CircleJoinPolicy.open,
  int memberCount = 0,
  int postCount = 0,
  int weeklyActiveCount = 0,
  bool followEnabled = true,
  bool autoSyncChat = true,
  List<CircleSectionConfig>? sectionConfig,
}) {
  return Circle(
    id: circleId,
    name: name,
    ownerId: ownerId,
    category: category,
    subCategory: subCategory,
    domainId: domainId,
    memberCount: memberCount,
    postCount: postCount,
    weeklyActiveCount: weeklyActiveCount,
    version: 1,
    status: status,
    visibility: visibility,
    joinPolicy: joinPolicy,
    kind: kind,
    displaySubjectType: displaySubjectType,
    followEnabled: followEnabled,
    autoSyncChat: autoSyncChat,
    sectionConfig: sectionConfig,
    storageUsedBytes: 0,
    storageQuotaBytes: 0,
    createdAt: _testDoubleEpoch,
    updatedAt: _testDoubleEpoch,
  );
}

final DateTime _testDoubleEpoch = DateTime.fromMillisecondsSinceEpoch(
  0,
  isUtc: true,
);

final class _CircleQueryHandlers {
  const _CircleQueryHandlers({
    this.list,
    this.search,
    this.get,
    this.feed,
    this.stats,
    this.impact,
  });

  final FutureOr<CirclePageSlice> Function(CircleListQuery query)? list;
  final FutureOr<CircleSearchResultView> Function(CircleSearchQuery query)?
  search;
  final FutureOr<Circle> Function(CircleDetailQuery query)? get;
  final FutureOr<CircleFeedPageSlice> Function(CircleFeedQuery query)? feed;
  final FutureOr<CircleStatsWire> Function(CircleStatsQuery query)? stats;
  final FutureOr<CircleImpactSummary> Function(CircleImpactQuery query)? impact;
}
