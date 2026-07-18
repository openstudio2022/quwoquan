import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import 'package:quwoquan_app/cloud/services/entity/remote/homepage_query_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

RemoteHomepageRepository buildRemoteHomepageRepositoryForTest({
  required CloudHttpClient httpClient,
  required String baseUrl,
}) {
  final gatewayBaseUri = Uri.parse(baseUrl);
  return RemoteHomepageRepository(
    queryAdapter: buildHomepageQueryAdapterForTest(
      httpClient: httpClient,
      gatewayBaseUri: gatewayBaseUri,
    ),
    httpClient: httpClient,
    baseUrl: baseUrl,
  );
}

RemoteHomepageQueryAdapter buildHomepageQueryAdapterForTest({
  required CloudHttpClient httpClient,
  required Uri gatewayBaseUri,
}) {
  return RemoteHomepageQueryAdapter(
    client: buildGeneratedCloudOperationClient(
      httpClient: httpClient,
      clientContextProvider: const _HomepageTestClientContext(),
      telemetrySink: const _NoopHomepageTelemetrySink(),
      environment: CloudRuntimeEnvironment(
        environment: CloudEnvironment.gamma,
        gatewayBaseUri: gatewayBaseUri,
      ),
    ),
    invocationContext: (clientPageId, surface, {cancellation, deadlineAt}) {
      final appSurface = switch (surface) {
        HomepageQuerySurface.picker => AppUiSurfaces.homepagePicker,
        HomepageQuerySurface.detail => AppUiSurfaces.homepageDetail,
        HomepageQuerySurface.introduction => AppUiSurfaces.homepageIntroduction,
      };
      return CloudOperationInvocationContext(
        surfaceId: appSurface.id,
        routeId: appSurface.routeId,
        clientPageId: clientPageId,
        cancellation: cancellation,
        deadlineAt: deadlineAt,
        actor: const CloudOperationActorContext(
          accountId: 'test-account',
          personaId: 'test-persona',
        ),
      );
    },
  );
}

final class _HomepageTestClientContext implements CloudClientContextProvider {
  const _HomepageTestClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'homepage-contract-session',
      deviceActorId: 'homepage-contract-device',
      platform: 'test',
      appVersion: 'test',
      locale: 'zh-CN',
    );
  }
}

final class _NoopHomepageTelemetrySink implements CloudOperationTelemetrySink {
  const _NoopHomepageTelemetrySink();

  @override
  void record(CloudOperationTelemetryEvent event) {}
}
