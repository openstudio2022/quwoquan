import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/di/entity_dependencies.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/homepage_operation_ports.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_claim_request/adapters/homepage_claim_request_remote.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_status_report/adapters/homepage_status_report_remote.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/account_lifecycle_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'production_cloud_operation_telemetry_evidence.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBase = String.fromEnvironment('API_CONTRACT_BASE_URL');
const entityApiContractDeviceId = 'entity-api-contract-device';

final class EntityApiContractHarness {
  EntityApiContractHarness._({
    required this._httpClient,
    required this.telemetry,
    required this.query,
    required this.claimRequests,
    required this.statusReports,
    required this._accountLifecycle,
    required this.session,
  });

  static Future<EntityApiContractHarness> create() async {
    if (_apiBase.isEmpty) {
      throw StateError('L3: ${_apiContractEnv.toUpperCase()}_BASE_URL not set');
    }
    final tokenProvider = _MutableAccessTokenProvider();
    final httpClient = CloudHttpClient(authTokenProvider: tokenProvider);
    const clientContext = _EntityApiClientContext();
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
      String? activeIdempotencyKey;
      CloudOperationInvocationContext invocationContext(
        AppUiSurface surface,
        String clientPageId, {
        String? idempotencyKey,
      }) => CloudOperationInvocationContext(
        surfaceId: surface.id,
        routeId: surface.routeId,
        clientPageId: clientPageId,
        idempotencyKey: idempotencyKey,
        actor: CloudOperationActorContext(
          accountId: session!.ownerId,
          personaId: session.activePersona?.personaId,
          deviceActorId: entityApiContractDeviceId,
        ),
      );

      final accountSessions = RemoteAccountSessionCommandWriter(
        client: client,
        invocationContext: (clientPageId) =>
            invocationContext(AppUiSurfaces.appShell, clientPageId),
      );
      session = await accountSessions.loginAnonymous(
        LoginAnonymousCommand(
          installId:
              'entity-api-contract-${DateTime.now().microsecondsSinceEpoch}',
          deviceFingerprintHash:
              'entity-api-contract-${DateTime.now().microsecondsSinceEpoch}',
          platform: 'web',
          appVersion: 'api-integration',
        ),
      );
      tokenProvider.accessToken = session.accessToken;

      final facets = EntityProductionComposition.homepageQueryFacets(
        client: client,
        detailInvocationContext: (clientPageId, {cancellation, deadlineAt}) =>
            invocationContext(AppUiSurfaces.homepageDetail, clientPageId),
        introductionInvocationContext:
            (clientPageId, {cancellation, deadlineAt}) => invocationContext(
              AppUiSurfaces.homepageIntroduction,
              clientPageId,
            ),
        searchInvocationContext: (clientPageId, {cancellation, deadlineAt}) =>
            invocationContext(AppUiSurfaces.homepagePicker, clientPageId),
      );

      final harness = EntityApiContractHarness._(
        httpClient: httpClient,
        telemetry: telemetry,
        query: facets.query,
        claimRequests: RemoteHomepageClaimRequestWriter(
          client: client,
          invocationContext: (clientPageId, surface) => invocationContext(
            surface,
            clientPageId,
            idempotencyKey:
                activeIdempotencyKey ??
                (throw StateError(
                  '$clientPageId requires an explicit idempotency scope',
                )),
          ),
        ),
        statusReports: RemoteHomepageStatusReportWriter(
          client: client,
          invocationContext: (clientPageId, surface) => invocationContext(
            surface,
            clientPageId,
            idempotencyKey:
                activeIdempotencyKey ??
                (throw StateError(
                  '$clientPageId requires an explicit idempotency scope',
                )),
          ),
        ),
        accountLifecycle: RemoteAccountLifecycleCommandWriter(
          client: client,
          invocationContext: (clientPageId) => invocationContext(
            AppUiSurfaces.settingsAccountSecurity,
            clientPageId,
            idempotencyKey:
                'entity-api-account-cleanup-'
                '${session?.ownerId ?? (throw StateError('missing account session'))}',
          ),
        ),
        session: session,
      );
      harness._setIdempotencyKey = (value) => activeIdempotencyKey = value;
      return harness;
    } catch (_) {
      httpClient.close();
      await telemetry.dispose();
      rethrow;
    }
  }

  final CloudHttpClient _httpClient;
  final ProductionCloudOperationTelemetryEvidence telemetry;
  final HomepageQueryFacet query;
  final RemoteHomepageClaimRequestWriter claimRequests;
  final RemoteHomepageStatusReportWriter statusReports;
  final RemoteAccountLifecycleCommandWriter _accountLifecycle;
  final AuthSessionGrant session;
  late final void Function(String? value) _setIdempotencyKey;
  bool _idempotencyScopeActive = false;

  Future<T> withIdempotencyKey<T>(
    String idempotencyKey,
    Future<T> Function() operation,
  ) async {
    final normalized = idempotencyKey.trim();
    if (normalized.isEmpty) {
      throw ArgumentError.value(idempotencyKey, 'idempotencyKey');
    }
    if (_idempotencyScopeActive) {
      throw StateError('nested Entity API idempotency scope is not allowed');
    }
    _idempotencyScopeActive = true;
    _setIdempotencyKey(normalized);
    try {
      return await operation();
    } finally {
      _setIdempotencyKey(null);
      _idempotencyScopeActive = false;
    }
  }

  Future<void> close() async {
    try {
      await _accountLifecycle.closeAccount(
        CloseAccountCommand(
          clientRequestId: 'entity-api-cleanup-${session.ownerId}',
        ),
      );
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

final class _EntityApiClientContext implements CloudClientContextProvider {
  const _EntityApiClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'entity-api-contract',
      deviceActorId: entityApiContractDeviceId,
      platform: 'web',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}
