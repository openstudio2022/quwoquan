import 'circle_operation_contracts.g.dart';

abstract interface class CircleFeedQueryReader {
  Future<CircleFeedPageSlice> feed(CircleFeedQuery query);
}

abstract interface class CircleQueryReader implements CircleFeedQueryReader {
  Future<CirclePageSlice> list(CircleListQuery query);

  Future<CircleSearchResultView> search(CircleSearchQuery query);

  Future<Circle> get(CircleDetailQuery query);

  @override
  Future<CircleFeedPageSlice> feed(CircleFeedQuery query);

  Future<CircleStatsWire> stats(CircleStatsQuery query);

  Future<CircleImpactSummary> impact(CircleImpactQuery query);
}

abstract interface class CircleDiscoveryFeedQueryReader {
  Future<CircleDiscoveryFeedPageSlice> listDiscoveryFeed(
    CircleDiscoveryFeedQuery query,
  );
}
