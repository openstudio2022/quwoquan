import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/content_service/content/intersection_visit_state/adapters/intersection_repository.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/account_lifecycle_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'api_contract_environment.dart';
import 'production_cloud_operation_telemetry_evidence.dart';

const recommendationApiContractDeviceId = 'recommendation-api-contract-device';

final class RecommendationApiContractHarness {
  RecommendationApiContractHarness._({
    required this._httpClient,
    required this._accountLifecycle,
    required this.telemetry,
    required this.intersections,
    required this.session,
  });

  static Future<RecommendationApiContractHarness> create() async {
    final environment = ApiContractEnvironment.resolve();
    final tokenProvider = _MutableAccessTokenProvider();
    final httpClient = CloudHttpClient(authTokenProvider: tokenProvider);
    const clientContext = _RecommendationApiClientContext();
    final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
      clientContextProvider: clientContext,
    );
    final client = buildGeneratedCloudOperationClient(
      httpClient: httpClient,
      clientContextProvider: clientContext,
      telemetrySink: telemetry.sink,
      environment: environment,
    );

    try {
      AuthSessionGrant? session;
      CloudOperationInvocationContext intersectionContext(
        String clientPageId,
      ) => CloudOperationInvocationContext(
        surfaceId: AppUiSurfaces.myIntersections.id,
        routeId: AppUiSurfaces.myIntersections.routeId,
        clientPageId: clientPageId,
        actor: CloudOperationActorContext(
          accountId: session!.ownerId,
          personaId: session.activePersona?.personaId,
          deviceActorId: recommendationApiContractDeviceId,
        ),
      );

      final accountSessions = RemoteAccountSessionCommandWriter(
        client: client,
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.appShell.id,
          routeId: AppUiSurfaces.appShell.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            deviceActorId: recommendationApiContractDeviceId,
          ),
        ),
      );
      session = await accountSessions.loginAnonymous(
        LoginAnonymousCommand(
          installId:
              'recommendation-api-contract-${DateTime.now().microsecondsSinceEpoch}',
          deviceFingerprintHash:
              'recommendation-api-contract-${DateTime.now().microsecondsSinceEpoch}',
          platform: 'web',
          appVersion: 'api-integration',
        ),
      );
      tokenProvider.accessToken = session.accessToken;

      final intersections = RemoteIntersectionRepository(
        client: client,
        myIntersectionsInvocationContext: intersectionContext,
        objectIntersectionsInvocationContext: intersectionContext,
      );

      return RecommendationApiContractHarness._(
        httpClient: httpClient,
        accountLifecycle: RemoteAccountLifecycleCommandWriter(
          client: client,
          invocationContext: (clientPageId) => CloudOperationInvocationContext(
            surfaceId: AppUiSurfaces.settingsAccountSecurity.id,
            routeId: AppUiSurfaces.settingsAccountSecurity.routeId,
            clientPageId: clientPageId,
            // CloseAccount 是幂等写命令，契约要求随 invocation 提供幂等键。
            idempotencyKey:
                'recommendation-api-account-cleanup-${session!.ownerId}',
            actor: CloudOperationActorContext(
              accountId: session.ownerId,
              personaId: session.activePersona?.personaId,
              deviceActorId: recommendationApiContractDeviceId,
            ),
          ),
        ),
        telemetry: telemetry,
        intersections: intersections,
        session: session,
      );
    } catch (_) {
      httpClient.close();
      await telemetry.dispose();
      rethrow;
    }
  }

  final CloudHttpClient _httpClient;
  final RemoteAccountLifecycleCommandWriter _accountLifecycle;
  final ProductionCloudOperationTelemetryEvidence telemetry;
  final RemoteIntersectionRepository intersections;
  final AuthSessionGrant session;
  var _closed = false;

  Future<void> close() async {
    if (_closed) return;
    _closed = true;
    try {
      await _accountLifecycle.closeAccount(
        CloseAccountCommand(
          clientRequestId: 'recommendation-api-cleanup-${session.ownerId}',
        ),
      );
      await telemetry.waitForEvents(minimumCount: 1);
    } finally {
      _httpClient.close();
      await telemetry.dispose();
    }
  }
}

final class _MutableAccessTokenProvider implements CloudAuthTokenProvider {
  String? accessToken;

  @override
  Future<String?> getAccessToken() async => accessToken;
}

final class _RecommendationApiClientContext
    implements CloudClientContextProvider {
  const _RecommendationApiClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'recommendation-api-contract',
      deviceActorId: recommendationApiContractDeviceId,
      platform: 'web',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}
