import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/location/application/public/location_query_contracts.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/create_location_coordinator.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/publish_circle_services.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import '../../../../../../support/runtime/platform/location/fake_location_gateway.dart';
import '../../../../../../support/runtime/errors/runtime_failure_fixtures.dart';
import '../../../../../../support/service/circle_service/circle_management/circle/circle_contract_test_builders.dart';

final class _SequencedLocationQuery
    implements NearbyLocationReader, LocationSearchReader {
  _SequencedLocationQuery(this.outcomes);

  final List<Object> outcomes;
  int nearbyCalls = 0;
  int searchCalls = 0;

  Object _next() {
    if (outcomes.isEmpty) {
      return LocationPoiListSlice(items: <LocationPoi>[]);
    }
    return outcomes.removeAt(0);
  }

  @override
  Future<LocationPoiListSlice> getNearbyLocations(
    NearbyLocationQueryParams query,
  ) async {
    nearbyCalls++;
    final outcome = _next();
    if (outcome is LocationPoiListSlice) return outcome;
    throw outcome;
  }

  @override
  Future<LocationPoiListSlice> searchLocations(
    LocationSearchQueryParams query,
  ) async {
    searchCalls++;
    final outcome = _next();
    if (outcome is LocationPoiListSlice) return outcome;
    throw outcome;
  }
}

final class _FakeCircleQueryReader implements CircleQueryReader {
  _FakeCircleQueryReader({required this.circles});

  final List<Circle> circles;

  @override
  Future<CirclePageSlice> list(CircleListQuery query) async =>
      CirclePageSlice(items: circles.take(query.limit).toList());

  @override
  Future<CircleSearchResultView> search(CircleSearchQuery query) async =>
      CircleSearchResultView(
        items: const <CircleSearchItemView>[],
        facetBuckets: const <CircleFacetBucketView>[],
      );

  @override
  Future<Circle> get(CircleDetailQuery query) async =>
      throw UnimplementedError();

  @override
  Future<CircleFeedPageSlice> feed(CircleFeedQuery query) async =>
      CircleFeedPageSlice(items: const <CircleFeedItemView>[]);

  @override
  Future<CircleStatsWire> stats(CircleStatsQuery query) async =>
      buildCircleStatsContract(circleId: query.circleId);

  @override
  Future<CircleImpactSummary> impact(CircleImpactQuery query) async =>
      CircleImpactSummary(
        circleId: query.circleId,
        total: 0,
        items: const <CircleImpactItem>[],
      );
}

void main() {
  group('CreateLocationCoordinator', () {
    test('nearby 返回 typed LocationPoi Slice', () async {
      final query = _SequencedLocationQuery(<Object>[
        LocationPoiListSlice(
          items: <LocationPoi>[
            LocationPoi(
              id: 'fixture_poi',
              name: '成都·天府广场',
              latitude: 30.6586,
              longitude: 104.0648,
              address: '锦江区',
              distanceMeters: 120,
            ),
          ],
        ),
      ]);
      final coordinator = CreateLocationCoordinator(
        nearbyReader: query,
        searchReader: query,
        locationGateway: FakeLocationGateway(),
      );

      final nearby = await coordinator.nearby();

      expect(nearby, hasLength(1));
      expect(nearby.single.name, '成都·天府广场');
    });

    test('空搜索词回退 nearby，不调用 Search operation', () async {
      final query = _SequencedLocationQuery(<Object>[
        LocationPoiListSlice(
          items: <LocationPoi>[
            const LocationPoi(
              id: 'fixture_poi',
              name: '杭州西湖',
              latitude: 30.2431,
              longitude: 120.1505,
            ),
          ],
        ),
      ]);
      final coordinator = CreateLocationCoordinator(
        nearbyReader: query,
        searchReader: query,
        locationGateway: FakeLocationGateway(),
      );

      final result = await coordinator.search('   ');

      expect(result.single.name, '杭州西湖');
      expect(query.nearbyCalls, 1);
      expect(query.searchCalls, 0);
    });

    test('429 保留最近一次 nearby Slice', () async {
      final query = _SequencedLocationQuery(<Object>[
        LocationPoiListSlice(
          items: <LocationPoi>[
            const LocationPoi(
              id: 'fixture_poi',
              name: '杭州西湖',
              latitude: 30.2431,
              longitude: 120.1505,
            ),
          ],
        ),
        CloudException(
          type: CloudErrorType.unknown,
          message: 'rate limited',
          statusCode: 429,
          runtimeFailure: testRuntimeFailure(
            code: 'APP.RATE_LIMITED.test_failure',
            kind: RuntimeFailureKind.rateLimited,
            nature: RuntimeFailureNature.transient,
          ),
        ),
      ]);
      final coordinator = CreateLocationCoordinator(
        nearbyReader: query,
        searchReader: query,
        locationGateway: FakeLocationGateway(),
      );

      final first = await coordinator.nearby();
      final second = await coordinator.nearby();

      expect(first.single.name, '杭州西湖');
      expect(second.single.name, '杭州西湖');
    });
  });

  group('CreateCircleService', () {
    test('uses remote circles when endpoint has data', () async {
      const service = CreateCircleService();
      final fake = _FakeCircleQueryReader(
        circles: <Circle>[
          buildCircleContract(
            circleId: 'c1',
            name: '测试圈子A',
            ownerId: 'u1',
            coverUrl: 'https://example.com/c1.jpg',
            memberCount: 88,
            postCount: 12,
          ),
          buildCircleContract(circleId: 'c2', name: '测试圈子B', ownerId: 'u1'),
        ],
      );

      final result = await service.listCircles(fake);

      expect(result, hasLength(2));
      expect(result.first.id, 'c1');
      expect(result.first.name, '测试圈子A');
      expect(result.first.coverUrl, 'https://example.com/c1.jpg');
      expect(result.first.memberCount, 88);
    });
  });
}
