import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/core/application/content/create_location_coordinator.dart';
import 'package:quwoquan_app/cloud/services/integration/location_query_contracts.dart';
import 'package:quwoquan_app/ui/content/entry/services/publish_circle_services.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import '../../../../../support/fake_location_gateway.dart';
import '../../../../../support/runtime_failure_fixtures.dart';

final class _SequencedLocationQuery
    implements NearbyLocationReader, LocationSearchReader {
  _SequencedLocationQuery(this.outcomes);

  final List<Object> outcomes;
  int nearbyCalls = 0;
  int searchCalls = 0;

  Object _next() {
    if (outcomes.isEmpty) {
      return LocationPoiListSlice(const <LocationPoiDto>[]);
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

final class _FakeCircleRepository extends MockCircleRepository {
  _FakeCircleRepository({required this.circles});

  final List<CircleDto> circles;

  @override
  Future<List<CircleDto>> listCircles({
    String? category,
    String? domainId,
    String? recommendFor,
    String? cursor,
    int limit = 20,
    String? sort,
    String? subCategory,
  }) async {
    return circles.take(limit).toList(growable: false);
  }
}

void main() {
  group('CreateLocationCoordinator', () {
    test('nearby 返回 typed LocationPoi Slice', () async {
      final query = _SequencedLocationQuery(<Object>[
        LocationPoiListSlice(<LocationPoiDto>[
          LocationPoiDto(
            id: 'fixture_poi',
            name: '成都·天府广场',
            latitude: 30.6586,
            longitude: 104.0648,
            address: '锦江区',
            distanceMeters: 120,
          ),
        ]),
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
        LocationPoiListSlice(<LocationPoiDto>[
          LocationPoiDto(id: 'fixture_poi', name: '杭州西湖'),
        ]),
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
        LocationPoiListSlice(<LocationPoiDto>[
          LocationPoiDto(id: 'fixture_poi', name: '杭州西湖'),
        ]),
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
      final fake = _FakeCircleRepository(
        circles: <CircleDto>[
          CircleDto.fromMap(<String, dynamic>{
            'id': 'c1',
            'name': '测试圈子A',
            'ownerId': 'u1',
            'coverUrl': 'https://example.com/c1.jpg',
            'memberCount': 88,
            'postCount': 12,
            'createdAt': '2025-01-01T00:00:00.000Z',
            'updatedAt': '2025-01-01T00:00:00.000Z',
          }),
          CircleDto.fromMap(<String, dynamic>{
            'id': 'c2',
            'name': '测试圈子B',
            'ownerId': 'u1',
            'createdAt': '2025-01-01T00:00:00.000Z',
            'updatedAt': '2025-01-01T00:00:00.000Z',
          }),
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
