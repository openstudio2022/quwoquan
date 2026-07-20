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
