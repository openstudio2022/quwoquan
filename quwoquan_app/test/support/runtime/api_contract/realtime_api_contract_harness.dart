import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/di/realtime_dependencies.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/realtime_connection_operation_gateway.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'production_cloud_operation_telemetry_evidence.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBase = String.fromEnvironment('API_CONTRACT_BASE_URL');
const realtimeApiContractDeviceId = 'realtime-api-contract-device';

final class RealtimeApiContractHarness {
  RealtimeApiContractHarness._({
    required this._httpClient,
    required this.telemetry,
    required this.connectionOperations,
    required this.session,
  });

  static Future<RealtimeApiContractHarness> create() async {
    if (_apiBase.isEmpty) {
      throw StateError('L3: ${_apiContractEnv.toUpperCase()}_BASE_URL not set');
    }
    final tokenProvider = _MutableAccessTokenProvider();
    final httpClient = CloudHttpClient(authTokenProvider: tokenProvider);
    const clientContext = _RealtimeApiClientContext();
    final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
      clientContextProvider: clientContext,
    );
    final client = buildGeneratedCloudOperationClient(
      httpClient: httpClient,
      clientContextProvider: clientContext,
      telemetrySink: telemetry.sink,
      environment: CloudRuntimeEnvironment(
        environment: CloudEnvironment.values.firstWhere(
          (candidate) => candidate.name == _apiContractEnv,
          orElse: () => throw StateError(
            'Unsupported API_CONTRACT_ENV: $_apiContractEnv',
          ),
        ),
        gatewayBaseUri: Uri.parse(_apiBase),
      ),
    );

    try {
      AuthSessionGrant? session;
      CloudOperationInvocationContext invocationContext(String clientPageId) =>
          CloudOperationInvocationContext(
            surfaceId: AppUiSurfaces.appShell.id,
            routeId: AppUiSurfaces.appShell.routeId,
            clientPageId: clientPageId,
            actor: CloudOperationActorContext(
              accountId: session!.ownerId,
              personaId: session.activePersona?.personaId,
              deviceActorId: realtimeApiContractDeviceId,
            ),
          );

      final accountSessions = RemoteAccountSessionCommandWriter(
        client: client,
        invocationContext: invocationContext,
      );
      session = await accountSessions.loginAnonymous(
        LoginAnonymousCommand(
          installId:
              'realtime-api-contract-${DateTime.now().microsecondsSinceEpoch}',
          deviceFingerprintHash:
              'realtime-api-contract-${DateTime.now().microsecondsSinceEpoch}',
          platform: 'web',
          appVersion: 'api-integration',
        ),
      );
      tokenProvider.accessToken = session.accessToken;

      final connectionOperations =
          RealtimeProductionComposition.connectionOperations(
            client: client,
            invocationContext: invocationContext,
          );

      return RealtimeApiContractHarness._(
        httpClient: httpClient,
        telemetry: telemetry,
        connectionOperations: connectionOperations,
        session: session,
      );
    } catch (_) {
      httpClient.close();
      await telemetry.dispose();
      rethrow;
    }
  }

  final CloudHttpClient _httpClient;
  final ProductionCloudOperationTelemetryEvidence telemetry;
  final RealtimeConnectionOperationGateway connectionOperations;
  final AuthSessionGrant session;

  Future<void> close() async {
    try {
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

final class _RealtimeApiClientContext implements CloudClientContextProvider {
  const _RealtimeApiClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'realtime-api-contract',
      deviceActorId: realtimeApiContractDeviceId,
      platform: 'web',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}
