import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef CircleQueryInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      required bool command,
    });

final class RemoteCircleQueryReader
    implements CircleQueryReader, CircleDiscoveryFeedQueryReader {
  const RemoteCircleQueryReader({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final CircleQueryInvocationContextFactory invocationContext;

  @override
  Future<CirclePageSlice> list(CircleListQuery query) =>
      client.circleCircleListCircles(
        query,
        context: _context(CircleRequestPageIds.listCircles),
      );

  @override
  Future<CircleDiscoveryFeedPageSlice> listDiscoveryFeed(
    CircleDiscoveryFeedQuery query,
  ) => client.circleCircleListCircleDiscoveryFeed(
    query,
    context: _context(CircleRequestPageIds.listCircleDiscoveryFeed),
  );

  @override
  Future<CircleSearchResultView> search(CircleSearchQuery query) =>
      client.circleCircleSearchCircles(
        query,
        context: _context(CircleRequestPageIds.searchCircles),
      );

  @override
  Future<Circle> get(CircleDetailQuery query) => client.circleCircleGetCircle(
    query,
    context: _context(CircleRequestPageIds.getCircle),
  );

  @override
  Future<CircleFeedPageSlice> feed(CircleFeedQuery query) =>
      client.circleCircleGetCircleFeed(
        query,
        context: _context(CircleRequestPageIds.getCircleFeed),
      );

  @override
  Future<CircleStatsWire> stats(CircleStatsQuery query) =>
      client.circleCircleGetCircleStats(
        query,
        context: _context(CircleRequestPageIds.getCircleStats),
      );

  @override
  Future<CircleImpactSummary> impact(CircleImpactQuery query) =>
      client.circleCircleGetCircleImpact(
        query,
        context: _context(CircleRequestPageIds.getCircleImpact),
      );

  CloudOperationInvocationContext _context(String clientPageId) =>
      invocationContext(clientPageId, command: false);
}
