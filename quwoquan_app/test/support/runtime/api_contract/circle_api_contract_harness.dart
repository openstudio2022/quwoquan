import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/application/public/circle_membership_ports.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/di/circle_dependencies.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'production_cloud_operation_telemetry_evidence.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBase = String.fromEnvironment('API_CONTRACT_BASE_URL');
const circleApiContractDeviceId = 'circle-api-contract-device';

/// Real generated-client -> production Circle Remote composition -> process.
///
/// Commands must enter through [withIdempotencyKey]; there is no raw HTTP,
/// substitute transport, random fallback key, or fixture-backed success path.
final class CircleApiContractHarness {
  CircleApiContractHarness._({
    required this._httpClient,
    required this.telemetry,
    required this._tokenProvider,
    required this.accountSessions,
    required this.lifecycle,
    required this.query,
    required this.membership,
  });

  static Future<CircleApiContractHarness> create() async {
    if (_apiBase.isEmpty) {
      throw StateError('L3: ${_apiContractEnv.toUpperCase()}_BASE_URL not set');
    }
    final tokenProvider = _MutableAccessTokenProvider();
    final httpClient = CloudHttpClient(authTokenProvider: tokenProvider);
    late CircleApiContractHarness harness;
    const clientContext = _CircleApiClientContext();
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

    CloudOperationInvocationContext invocationContext(
      String clientPageId, {
      required bool command,
    }) => harness._invocationContext(clientPageId, command: command);

    harness = CircleApiContractHarness._(
      httpClient: httpClient,
      telemetry: telemetry,
      tokenProvider: tokenProvider,
      accountSessions: RemoteAccountSessionCommandWriter(
        client: client,
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.appShell.id,
          routeId: AppUiSurfaces.appShell.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            deviceActorId: circleApiContractDeviceId,
          ),
        ),
      ),
      lifecycle: CircleProductionComposition.generatedAdapter(
        CircleProductionAdapter.lifecycle,
        client: client,
        invocationContext: invocationContext,
      ),
      query: CircleProductionComposition.generatedAdapter(
        CircleProductionAdapter.query,
        client: client,
        invocationContext: invocationContext,
      ),
      membership: CircleProductionComposition.generatedAdapter(
        CircleProductionAdapter.membership,
        client: client,
        invocationContext: invocationContext,
      ),
    );
    return harness;
  }

  final CloudHttpClient _httpClient;
  final ProductionCloudOperationTelemetryEvidence telemetry;
  final _MutableAccessTokenProvider _tokenProvider;
  final RemoteAccountSessionCommandWriter accountSessions;
  final CircleLifecycleCommandWriter lifecycle;
  final CircleQueryReader query;
  final CircleMembershipCommands membership;

  String? _ownerId;
  String? _personaId;
  String? _activeIdempotencyKey;

  Future<AuthSessionGrant> loginDisposableAccount(String purpose) async {
    _tokenProvider.accessToken = null;
    _ownerId = null;
    _personaId = null;
    final nonce = DateTime.now().microsecondsSinceEpoch;
    final session = await accountSessions.loginAnonymous(
      LoginAnonymousCommand(
        installId: 'circle-$purpose-$nonce',
        deviceFingerprintHash: 'circle-$purpose-$nonce',
        platform: 'web',
        appVersion: 'api-integration',
      ),
    );
    _tokenProvider.accessToken = session.accessToken;
    _ownerId = session.ownerId;
    _personaId = session.activePersona?.personaId;
    return session;
  }

  Future<T> withIdempotencyKey<T>(
    String idempotencyKey,
    Future<T> Function() operation,
  ) async {
    final normalized = idempotencyKey.trim();
    if (normalized.isEmpty) {
      throw ArgumentError.value(idempotencyKey, 'idempotencyKey');
    }
    if (_activeIdempotencyKey != null) {
      throw StateError('Circle API contract commands must be sequential');
    }
    _activeIdempotencyKey = normalized;
    try {
      return await operation();
    } finally {
      _activeIdempotencyKey = null;
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

  CloudOperationInvocationContext _invocationContext(
    String clientPageId, {
    required bool command,
  }) {
    final surface = switch (clientPageId) {
      CircleRequestPageIds.createCircle ||
      CircleRequestPageIds.listCircles => AppUiSurfaces.circlesList,
      CircleRequestPageIds.updateCircle ||
      CircleRequestPageIds.archiveCircle ||
      CircleRequestPageIds.getCircle ||
      CircleRequestPageIds.joinCircle ||
      CircleRequestPageIds.leaveCircle => AppUiSurfaces.circleDetail,
      _ => throw StateError(
        'Unsupported Circle API contract clientPageId: $clientPageId',
      ),
    };
    final idempotencyKey = command ? _activeIdempotencyKey : null;
    if (command && idempotencyKey == null) {
      throw StateError('Circle command requires an explicit idempotency key');
    }
    return CloudOperationInvocationContext(
      surfaceId: surface.id,
      routeId: surface.routeId,
      clientPageId: clientPageId,
      idempotencyKey: idempotencyKey,
      actor: CloudOperationActorContext(
        accountId: _ownerId,
        personaId: _personaId,
        deviceActorId: circleApiContractDeviceId,
      ),
    );
  }
}

final class _MutableAccessTokenProvider implements CloudAuthTokenProvider {
  String? accessToken;

  @override
  Future<String?> getAccessToken() async => accessToken;
}

final class _CircleApiClientContext implements CloudClientContextProvider {
  const _CircleApiClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'circle-api-contract',
      deviceActorId: circleApiContractDeviceId,
      platform: 'web',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}
