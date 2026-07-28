import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/remote/circle/circle/circle_query_remote.dart';
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../support/recording_cloud_operation_telemetry_sink.dart';

const _gatewayUrl = String.fromEnvironment(
  'GAMMA_GATEWAY_URL',
  defaultValue: '',
);

final class _GammaCircleClientContext implements CloudClientContextProvider {
  const _GammaCircleClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'gamma-circle-discovery-api-integration',
      deviceActorId: 'gamma-circle-discovery-device',
      platform: 'test',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}

void main() {
  test('generated Circle Remote 读取 discovery 与单圈 typed feed', () async {
    final httpClient = CloudHttpClient();
    final telemetry = RecordingCloudOperationTelemetrySink();
    addTearDown(httpClient.close);
    final client = buildGeneratedCloudOperationClient(
      httpClient: httpClient,
      clientContextProvider: const _GammaCircleClientContext(),
      telemetrySink: telemetry,
      environment: CloudRuntimeEnvironment(
        environment: CloudEnvironment.gamma,
        gatewayBaseUri: Uri.parse(_gatewayUrl),
      ),
    );
    final remote = RemoteCircleQueryReader(
      client: client,
      invocationContext: (clientPageId, {required command}) =>
          CloudOperationInvocationContext(
            surfaceId: AppUiSurfaces.circlesList.id,
            routeId: AppUiSurfaces.circlesList.routeId,
            clientPageId: clientPageId,
            actor: const CloudOperationActorContext(
              deviceActorId: 'gamma-circle-discovery-device',
            ),
          ),
    );

    final discovery = await remote.listDiscoveryFeed(
      const CircleDiscoveryFeedQuery(
        scope: CircleDiscoveryFeedScope.recommended,
        sort: 'recommended',
        limit: 20,
      ),
    );
    expect(discovery.circles, isNotEmpty);
    expect(
      discovery.items.every(
        (item) => item.circleId.isNotEmpty && item.placementId.isNotEmpty,
      ),
      isTrue,
      reason: '聚合 feed 必须始终交付 placement 归属，而非 Post 动态 wire',
    );

    final techFeed = await remote.feed(
      const CircleFeedQuery(circleId: 'fixture_circle_tech_01', limit: 20),
    );
    expect(techFeed.items, isNotEmpty);
    expect(techFeed.items.every((item) => item.placementId.isNotEmpty), isTrue);
    expect(telemetry.events, hasLength(2));
    expect(telemetry.events.every((event) => event.succeeded), isTrue);
  });
}
