import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/di/realtime_dependencies.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/realtime_connection_operation_gateway.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/persona_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'production_cloud_operation_telemetry_evidence.dart';
import 'api_contract_environment.dart';

const realtimeApiContractDeviceId = 'realtime-api-contract-device';

final class RealtimeApiContractHarness {
  RealtimeApiContractHarness._({
    required this._httpClient,
    required this.telemetry,
    required this.connectionOperations,
    required this.session,
  });

  static Future<RealtimeApiContractHarness> create() async {
    final environment = ApiContractEnvironment.resolve();
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
      environment: environment,
    );

    try {
      AuthSessionGrant? session;
      String? activePersonaId;
      CloudOperationInvocationContext invocationContext(String clientPageId) =>
          CloudOperationInvocationContext(
            surfaceId: AppUiSurfaces.appShell.id,
            routeId: AppUiSurfaces.appShell.routeId,
            clientPageId: clientPageId,
            actor: CloudOperationActorContext(
              accountId: session!.ownerId,
              personaId: activePersonaId ?? session.activePersona?.personaId,
              deviceActorId: realtimeApiContractDeviceId,
            ),
          );

      // 登录请求发生在会话建立前，必须使用匿名 actor context；
      // 带 session 断言的共享 context 只服务登录后的对象操作。
      final accountSessions = RemoteAccountSessionCommandWriter(
        client: client,
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.appShell.id,
          routeId: AppUiSurfaces.appShell.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            deviceActorId: realtimeApiContractDeviceId,
          ),
        ),
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

      // realtime connection 契约要求 persona actor（ActorRequirement=persona，
      // api-edge fail-closed）；匿名会话不带默认 persona，按公开 command
      // 创建并激活一个 persona 作为本 harness 的 actor 身份。
      if (session.activePersona?.personaId == null) {
        final suffix = DateTime.now().microsecondsSinceEpoch;
        final personaCommands = RemotePersonaCommandWriter(
          client: client,
          invocationContext: (clientPageId) => CloudOperationInvocationContext(
            surfaceId: AppUiSurfaces.profilePersonas.id,
            routeId: AppUiSurfaces.profilePersonas.routeId,
            clientPageId: clientPageId,
            idempotencyKey: 'realtime-api-contract-persona-$suffix',
            actor: CloudOperationActorContext(
              accountId: session!.ownerId,
              deviceActorId: realtimeApiContractDeviceId,
            ),
          ),
        );
        final created = await personaCommands.createPersona(
          CreatePersonaCommand(
            displayName: 'Realtime contract $suffix',
            isolationLevel: 'strict',
            purposeHint: 'api_contract',
          ),
        );
        final activated = await personaCommands.activatePersona(
          ActivatePersonaCommand(personaId: created.personaId),
        );
        activePersonaId = activated.personaId;
      }

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
