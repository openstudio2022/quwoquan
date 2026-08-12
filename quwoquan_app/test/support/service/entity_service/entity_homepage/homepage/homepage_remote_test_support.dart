import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/adapters/homepage_facet_projection_adapter.dart';
import 'package:quwoquan_app/runtime/di/entity_dependencies.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

HomepageFacetProjectionAdapter buildRemoteHomepageRepositoryForTest({
  required CloudHttpClient httpClient,
  required String baseUrl,
}) {
  final gatewayBaseUri = Uri.parse(baseUrl);
  final client = buildGeneratedCloudOperationClient(
    httpClient: httpClient,
    clientContextProvider: const _HomepageTestClientContext(),
    telemetrySink: const _NoopHomepageTelemetrySink(),
    environment: CloudRuntimeEnvironment(
      environment: CloudEnvironment.gamma,
      gatewayBaseUri: gatewayBaseUri,
    ),
  );

  CloudOperationInvocationContext queryInvocationContext(
    AppUiSurface surface,
    String clientPageId, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) {
    return CloudOperationInvocationContext(
      surfaceId: surface.id,
      routeId: surface.routeId,
      clientPageId: clientPageId,
      cancellation: cancellation,
      deadlineAt: deadlineAt,
      actor: const CloudOperationActorContext(
        accountId: 'test-account',
        personaId: 'test-persona',
      ),
    );
  }

  final queryFacets = EntityProductionComposition.homepageQueryFacets(
    client: client,
    detailInvocationContext: (clientPageId, {cancellation, deadlineAt}) =>
        queryInvocationContext(
          AppUiSurfaces.homepageDetail,
          clientPageId,
          cancellation: cancellation,
          deadlineAt: deadlineAt,
        ),
    introductionInvocationContext: (clientPageId, {cancellation, deadlineAt}) =>
        queryInvocationContext(
          AppUiSurfaces.homepageIntroduction,
          clientPageId,
          cancellation: cancellation,
          deadlineAt: deadlineAt,
        ),
    searchInvocationContext: (clientPageId, {cancellation, deadlineAt}) =>
        queryInvocationContext(
          AppUiSurfaces.homepagePicker,
          clientPageId,
          cancellation: cancellation,
          deadlineAt: deadlineAt,
        ),
  );
  final commandFacets = EntityProductionComposition.homepageCommandFacets(
    client: client,
    invocationContext: (clientPageId, surface) =>
        CloudOperationInvocationContext(
          surfaceId: surface.id,
          routeId: surface.routeId,
          clientPageId: clientPageId,
          idempotencyKey: 'test-idempotency-key',
          actor: const CloudOperationActorContext(
            accountId: 'test-account',
            personaId: 'test-persona',
          ),
        ),
    claimRequestInvocationContext:
        (clientPageId, surface, {String? idempotencyKey}) =>
            CloudOperationInvocationContext(
              surfaceId: surface.id,
              routeId: surface.routeId,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey ?? 'test-idempotency-key',
              actor: const CloudOperationActorContext(
                accountId: 'test-account',
                personaId: 'test-persona',
              ),
            ),
    statusReportInvocationContext:
        (clientPageId, surface, {String? idempotencyKey}) =>
            CloudOperationInvocationContext(
              surfaceId: surface.id,
              routeId: surface.routeId,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey ?? 'test-idempotency-key',
              actor: const CloudOperationActorContext(
                accountId: 'test-account',
                personaId: 'test-persona',
              ),
            ),
  );
  return HomepageFacetProjectionAdapter(
    query: queryFacets.query,
    candidateWriter: commandFacets.candidateWriter,
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
