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
    return remoteApiPathJsonResponse('{"items":[]}');
  }
  return remoteApiPathJsonResponse({
    'items': <dynamic>[],
    'data': <String, dynamic>{'id': 'mock_id', 'type': 'mock'},
    'cursor': null,
  });
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

    test(
      'getNearbyLocations → GET /integration/external_integration/location/nearby',
      () async {
        await adapter.getNearbyLocations(
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
          operationId:
              AppCloudOperationIds.integrationLocationGetNearbyLocations,
        );
      },
    );

    test(
      'searchLocations → GET /integration/external_integration/location/search',
      () async {
        await adapter.searchLocations(
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
      },
    );
  });
}
