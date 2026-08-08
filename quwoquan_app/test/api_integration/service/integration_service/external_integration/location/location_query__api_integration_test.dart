// spec_ref: specs/feature-tree/runtime/runtime-external-integration/integration-service-foundation/spec.md#gwt-001
// readiness_case: location_get_nearby_locations_app_api
// readiness_case: location_search_locations_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/location/adapters/location_query_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/production_cloud_operation_telemetry_evidence.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _gatewayUrl = String.fromEnvironment('API_CONTRACT_BASE_URL');

final class _GammaClientContext implements CloudClientContextProvider {
  const _GammaClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'location-api-integration',
      deviceActorId: 'location-api-integration-device',
      platform: 'test',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}

void main() {
  test(
    'generated client 通过 candidate gateway 读取 Location nearby/search',
    () async {
      expect(
        _apiContractEnv,
        'gamma',
        reason: 'Location App API readiness case 只绑定 gamma candidate',
      );
      expect(
        Uri.tryParse(_gatewayUrl),
        isA<Uri>().having((uri) => uri.scheme, 'scheme', 'https'),
        reason: 'API_CONTRACT_BASE_URL 必须由 candidate launcher 显式注入',
      );
      final httpClient = CloudHttpClient();
      final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
        clientContextProvider: const _GammaClientContext(),
      );
      addTearDown(httpClient.close);
      addTearDown(telemetry.dispose);
      final client = buildGeneratedCloudOperationClient(
        httpClient: httpClient,
        clientContextProvider: const _GammaClientContext(),
        telemetrySink: telemetry.sink,
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.values.firstWhere(
            (candidate) => candidate.name == _apiContractEnv,
          ),
          gatewayBaseUri: Uri.parse(_gatewayUrl),
        ),
      );
      final adapter = RemoteLocationQueryAdapter(
        client: client,
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.createWorkspace.id,
          routeId: AppUiSurfaces.createWorkspace.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            deviceActorId: 'location-api-integration-device',
          ),
        ),
      );

      final nearby = await adapter.getNearbyLocations(
        const NearbyLocationQueryParams(
          latitude: 30.2431,
          longitude: 120.1505,
          limit: 20,
        ),
      );
      final search = await adapter.searchLocations(
        const LocationSearchQueryParams(query: '西湖', limit: 20),
      );

      expect(nearby.items, isNotEmpty);
      expect(
        nearby.items.every(
          (item) => item.id.isNotEmpty && item.name.isNotEmpty,
        ),
        isTrue,
      );
      expect(search.items.any((item) => item.name.contains('西湖')), isTrue);
      final telemetryEvents = await telemetry.waitForEvents(minimumCount: 2);
      final locationEvents = telemetryEvents
          .where(
            (event) =>
                event.canonicalOperationId ==
                    AppCloudOperationIds
                        .integrationLocationGetNearbyLocations ||
                event.canonicalOperationId ==
                    AppCloudOperationIds.integrationLocationSearchLocations,
          )
          .toList(growable: false);
      expect(
        locationEvents.map((event) => event.canonicalOperationId),
        <String>[
          AppCloudOperationIds.integrationLocationGetNearbyLocations,
          AppCloudOperationIds.integrationLocationSearchLocations,
        ],
      );
      expect(locationEvents.every((event) => event.succeeded), isTrue);
      expect(locationEvents.every((event) => event.statusCode == 200), isTrue);
      expect(
        locationEvents.every(
          (event) => event.requestId.isNotEmpty && event.traceId.isNotEmpty,
        ),
        isTrue,
      );
    },
  );
}
