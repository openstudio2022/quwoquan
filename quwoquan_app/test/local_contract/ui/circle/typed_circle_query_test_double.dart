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
    FutureOr<CircleSearchResultSlice> Function(CircleSearchQuery query)? search,
    FutureOr<CircleProjection> Function(CircleDetailQuery query)? get,
    FutureOr<CircleFeedPageSlice> Function(CircleFeedQuery query)? feed,
    FutureOr<CircleStatsSlice> Function(CircleStatsQuery query)? stats,
    FutureOr<CircleImpactSlice> Function(CircleImpactQuery query)? impact,
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
      _handlers.list?.call(query) ??
      CirclePageSlice(items: const <CircleProjection>[]);

  @override
  Future<CircleSearchResultSlice> search(CircleSearchQuery query) async =>
      _handlers.search?.call(query) ??
      CircleSearchResultSlice(
        items: const <CircleSearchItemProjection>[],
        facetBuckets: const <CircleFacetBucketProjection>[],
      );

  @override
  Future<CircleProjection> get(CircleDetailQuery query) async =>
      _handlers.get?.call(query) ??
      CircleProjection(
        circleId: query.circleId,
        name: '测试圈子',
        ownerId: 'fixture_user_owner',
      );

  @override
  Future<CircleFeedPageSlice> feed(CircleFeedQuery query) async =>
      _handlers.feed?.call(query) ??
      CircleFeedPageSlice(items: const <CircleFeedPostProjection>[]);

  @override
  Future<CircleStatsSlice> stats(CircleStatsQuery query) async =>
      _handlers.stats?.call(query) ??
      CircleStatsSlice(circleId: query.circleId);

  @override
  Future<CircleImpactSlice> impact(CircleImpactQuery query) async =>
      _handlers.impact?.call(query) ??
      CircleImpactSlice(
        circleId: query.circleId,
        total: 0,
        items: const <CircleImpactItemProjection>[],
      );
}

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
  final FutureOr<CircleSearchResultSlice> Function(CircleSearchQuery query)?
  search;
  final FutureOr<CircleProjection> Function(CircleDetailQuery query)? get;
  final FutureOr<CircleFeedPageSlice> Function(CircleFeedQuery query)? feed;
  final FutureOr<CircleStatsSlice> Function(CircleStatsQuery query)? stats;
  final FutureOr<CircleImpactSlice> Function(CircleImpactQuery query)? impact;
}
