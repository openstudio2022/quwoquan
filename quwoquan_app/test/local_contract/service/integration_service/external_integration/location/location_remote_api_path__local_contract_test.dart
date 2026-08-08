// spec_ref: specs/feature-tree/runtime/runtime-external-integration/integration-service-foundation/spec.md#gwt-001
// readiness_case: location_get_nearby_locations_app_local
// readiness_case: location_search_locations_app_local
/// 对象级端云契约：Remote adapter 的 HTTP path 与 generated metadata 对齐。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/integration/integration_request_page_ids.g.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/location/adapters/location_query_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/runtime/remote_api_path_test_harness.dart';

http.Response _responseFor(http.Request request) {
  final path = request.url.path;
  if (request.method == 'GET' &&
      (path ==
              canonicalRemoteApiPath(
                AppCloudOperationIds.integrationLocationGetNearbyLocations,
              ) ||
          path ==
              canonicalRemoteApiPath(
                AppCloudOperationIds.integrationLocationSearchLocations,
              ))) {
    final isNearby = path.endsWith('/nearby');
    return remoteApiPathJsonResponse(<String, Object?>{
      'items': <Object?>[
        <String, Object?>{
          'id': isNearby ? 'poi-nearby-west-lake' : 'poi-search-west-lake',
          'name': '西湖风景名胜区',
          'latitude': 30.2431,
          'longitude': 120.15,
          'address': '杭州市西湖区',
          'distanceMeters': isNearby ? 320 : 640,
        },
      ],
    });
  }
  throw StateError('unexpected location request: ${request.method} $path');
}

void main() {
  group('RemoteLocationQueryAdapter — generated operation 路径对齐', () {
    late List<CapturedRemoteApiPathRequest> log;
    late RemoteLocationQueryAdapter adapter;

    setUp(() {
      log = [];
      final client = buildRemoteApiPathOperationClient(
        log,
        responseFor: _responseFor,
        authenticated: false,
      );
      adapter = RemoteLocationQueryAdapter(
        client: client,
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.createWorkspace.id,
          routeId: AppUiSurfaces.createWorkspace.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(),
        ),
      );
    });

    test('getNearbyLocations → GET /integration/location/nearby', () async {
      final result = await adapter.getNearbyLocations(
        const NearbyLocationQueryParams(
          latitude: 30.2431,
          longitude: 120.1500,
          radiusMeters: 2000,
          limit: 8,
        ),
      );
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        canonicalRemoteApiPath(
          AppCloudOperationIds.integrationLocationGetNearbyLocations,
        ),
      );
      expect(log.last.query['lat'], '30.2431');
      expect(log.last.query['lng'], '120.15');
      expect(log.last.query['radiusMeters'], '2000');
      expect(log.last.query['limit'], '8');
      expectRemoteApiPathHeaders(
        log.last.headers,
        clientPageId: IntegrationRequestPageIds.getNearbyLocations,
        surfaceId: AppUiSurfaces.createWorkspace.id,
        operationId: AppCloudOperationIds.integrationLocationGetNearbyLocations,
      );
      expect(result.items, hasLength(1));
      expect(result.items.single.id, 'poi-nearby-west-lake');
      expect(result.items.single.name, '西湖风景名胜区');
      expect(result.items.single.distanceMeters, 320);
      expect(
        canonicalRemoteApiOperation(
          AppCloudOperationIds.integrationLocationGetNearbyLocations,
        ).idempotency,
        'none',
      );
    });

    test('searchLocations → GET /integration/location/search', () async {
      final result = await adapter.searchLocations(
        const LocationSearchQueryParams(
          query: '西湖',
          cityCode: '330100',
          latitude: 30.2431,
          longitude: 120.1500,
          limit: 12,
        ),
      );
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        canonicalRemoteApiPath(
          AppCloudOperationIds.integrationLocationSearchLocations,
        ),
      );
      expect(log.last.query['q'], '西湖');
      expect(log.last.query['cityCode'], '330100');
      expect(log.last.query['lat'], '30.2431');
      expect(log.last.query['lng'], '120.15');
      expect(log.last.query['limit'], '12');
      expectRemoteApiPathHeaders(
        log.last.headers,
        clientPageId: IntegrationRequestPageIds.searchLocations,
        surfaceId: AppUiSurfaces.createWorkspace.id,
        operationId: AppCloudOperationIds.integrationLocationSearchLocations,
      );
      expect(result.items, hasLength(1));
      expect(result.items.single.id, 'poi-search-west-lake');
      expect(result.items.single.address, '杭州市西湖区');
      expect(result.items.single.distanceMeters, 640);
      expect(
        canonicalRemoteApiOperation(
          AppCloudOperationIds.integrationLocationSearchLocations,
        ).idempotency,
        'none',
      );
    });
  });
}
