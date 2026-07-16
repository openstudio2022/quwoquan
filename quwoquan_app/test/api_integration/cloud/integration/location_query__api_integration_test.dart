import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/integration/remote/location_query_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../support/recording_cloud_operation_telemetry_sink.dart';

const _gatewayUrl = String.fromEnvironment(
  'GAMMA_GATEWAY_URL',
  defaultValue: 'http://127.0.0.1:18080',
);

final class _GammaClientContext implements CloudClientContextProvider {
  const _GammaClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'gamma-location-api-integration',
      deviceActorId: 'gamma-location-device',
      platform: 'test',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}

void main() {
  test(
    'generated client 通过 gamma gateway 读取 Location nearby/search seed',
    () async {
      final httpClient = CloudHttpClient();
      final telemetry = RecordingCloudOperationTelemetrySink();
      addTearDown(httpClient.close);
      final client = buildGeneratedCloudOperationClient(
        httpClient: httpClient,
        clientContextProvider: const _GammaClientContext(),
        telemetrySink: telemetry,
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
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
            deviceActorId: 'gamma-location-device',
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
      expect(telemetry.events, hasLength(2));
      expect(telemetry.events.every((event) => event.succeeded), isTrue);
      expect(
        telemetry.events.every(
          (event) =>
              (event.requestId ?? '').isNotEmpty &&
              (event.traceId ?? '').isNotEmpty,
        ),
        isTrue,
      );
    },
  );
}
