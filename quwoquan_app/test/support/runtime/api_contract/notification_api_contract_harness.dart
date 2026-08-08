import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/di/notification_dependencies.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/notification_service/notification_delivery/notification/application/notification_facets.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'production_cloud_operation_telemetry_evidence.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBase = String.fromEnvironment('API_CONTRACT_BASE_URL');
const notificationApiContractDeviceId = 'notification-api-contract-device';

final class NotificationApiContractHarness {
  NotificationApiContractHarness._({
    required this._httpClient,
    required this._tokenProvider,
    required this.telemetry,
    required this.query,
    required this.commandWriter,
    required this.session,
  });

  static Future<NotificationApiContractHarness> create() async {
    if (_apiBase.isEmpty) {
      throw StateError('L3: API_CONTRACT_BASE_URL not set');
    }
    final tokenProvider = _MutableAccessTokenProvider();
    final httpClient = CloudHttpClient(authTokenProvider: tokenProvider);
    const clientContext = _NotificationApiClientContext();
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
      final accountSessions = RemoteAccountSessionCommandWriter(
        client: client,
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.appShell.id,
          routeId: AppUiSurfaces.appShell.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            deviceActorId: notificationApiContractDeviceId,
          ),
        ),
      );
      final session = await accountSessions.loginAnonymous(
        LoginAnonymousCommand(
          installId:
              'notification-api-contract-${DateTime.now().microsecondsSinceEpoch}',
          deviceFingerprintHash:
              'notification-api-contract-${DateTime.now().microsecondsSinceEpoch}',
          platform: 'web',
          appVersion: 'api-integration',
        ),
      );
      tokenProvider.accessToken = session.accessToken;

      late NotificationApiContractHarness harness;
      CloudOperationInvocationContext invocationContext(String clientPageId) =>
          harness._invocationContext(clientPageId);
      final facets = NotificationProductionComposition.appMessageFacets(
        client: client,
        invocationContext: invocationContext,
      );

      harness = NotificationApiContractHarness._(
        httpClient: httpClient,
        tokenProvider: tokenProvider,
        telemetry: telemetry,
        query: facets.query,
        commandWriter: facets.commandWriter,
        session: session,
      );
      return harness;
    } catch (_) {
      httpClient.close();
      await telemetry.dispose();
      rethrow;
    }
  }

  final CloudHttpClient _httpClient;
  final _MutableAccessTokenProvider _tokenProvider;
  final ProductionCloudOperationTelemetryEvidence telemetry;
  final AppMessageQuery query;
  final AppMessageCommandWriter commandWriter;
  AuthSessionGrant session;

  Future<T> withSession<T>({
    required AuthSessionGrant session,
    required Future<T> Function() action,
  }) async {
    final currentSession = this.session;
    final currentAccessToken = _tokenProvider.accessToken;
    this.session = session;
    _tokenProvider.accessToken = session.accessToken;
    try {
      return await action();
    } finally {
      this.session = currentSession;
      _tokenProvider.accessToken = currentAccessToken;
    }
  }

  Future<void> close() async {
    try {
      await telemetry.waitForEvents(minimumCount: 1);
    } finally {
      _httpClient.close();
      await telemetry.dispose();
    }
  }

  CloudOperationInvocationContext _invocationContext(String clientPageId) {
    return CloudOperationInvocationContext(
      surfaceId: AppUiSurfaces.chatList.id,
      routeId: AppUiSurfaces.chatList.routeId,
      clientPageId: clientPageId,
      actor: CloudOperationActorContext(
        accountId: session.ownerId,
        personaId: session.activePersona?.personaId,
        deviceActorId: notificationApiContractDeviceId,
      ),
    );
  }
}

final class _MutableAccessTokenProvider implements CloudAuthTokenProvider {
  String? accessToken;

  @override
  Future<String?> getAccessToken() async => accessToken;
}

final class _NotificationApiClientContext
    implements CloudClientContextProvider {
  const _NotificationApiClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'notification-api-contract',
      deviceActorId: notificationApiContractDeviceId,
      platform: 'web',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}
