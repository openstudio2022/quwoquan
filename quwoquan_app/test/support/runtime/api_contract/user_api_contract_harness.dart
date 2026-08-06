import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/account_lifecycle_remote.dart';
import 'package:quwoquan_app/service/user_service/account/user_settings/adapters/user_settings_remote.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/adapters/persona_relationship_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'production_cloud_operation_telemetry_evidence.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBase = String.fromEnvironment('API_CONTRACT_BASE_URL');
const userApiContractDeviceId = 'user-identity-api-contract-device';

final class UserApiContractHarness {
  UserApiContractHarness._({
    required this._httpClient,
    required this._tokenProvider,
    required this.telemetry,
    required this.accountSessions,
    required this.accountLifecycle,
    required this.settingsReader,
    required this.settingsCommands,
    required this.personaRelationships,
  });

  static Future<UserApiContractHarness> create() async {
    if (_apiBase.isEmpty) {
      throw StateError('L3: ${_apiContractEnv.toUpperCase()}_BASE_URL not set');
    }
    final tokenProvider = _MutableAccessTokenProvider();
    final httpClient = CloudHttpClient(authTokenProvider: tokenProvider);
    const clientContext = _UserApiClientContext();
    final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
      clientContextProvider: clientContext,
    );
    late UserApiContractHarness harness;
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
    CloudOperationInvocationContext invocationContext(String clientPageId) =>
        harness._invocationContext(clientPageId);
    harness = UserApiContractHarness._(
      httpClient: httpClient,
      tokenProvider: tokenProvider,
      telemetry: telemetry,
      accountSessions: RemoteAccountSessionCommandWriter(
        client: client,
        invocationContext: invocationContext,
      ),
      accountLifecycle: RemoteAccountLifecycleCommandWriter(
        client: client,
        invocationContext: invocationContext,
      ),
      settingsReader: RemoteUserSettingsQueryReader(
        client: client,
        invocationContext: invocationContext,
      ),
      settingsCommands: RemoteUserSettingsCommandWriter(
        client: client,
        invocationContext: invocationContext,
      ),
      personaRelationships: RemotePersonaRelationshipFacet(
        client: client,
        invocationContext: invocationContext,
      ),
    );
    return harness;
  }

  final CloudHttpClient _httpClient;
  final _MutableAccessTokenProvider _tokenProvider;
  final ProductionCloudOperationTelemetryEvidence telemetry;
  final RemoteAccountSessionCommandWriter accountSessions;
  final RemoteAccountLifecycleCommandWriter accountLifecycle;
  final RemoteUserSettingsQueryReader settingsReader;
  final RemoteUserSettingsCommandWriter settingsCommands;
  final RemotePersonaRelationshipFacet personaRelationships;

  AuthSessionGrant? _session;
  LoginAnonymousCommand? _sessionBootstrapCommand;
  String? _ownerId;
  String? _personaId;

  AuthSessionGrant get session => _session!;
  LoginAnonymousCommand get sessionBootstrapCommand =>
      _sessionBootstrapCommand!;

  Future<AuthSessionGrant> loginDisposableAccount(String purpose) async {
    final subject =
        'user-identity-$purpose-${DateTime.now().microsecondsSinceEpoch}';
    final command = LoginAnonymousCommand(
      installId: 'api-contract-$subject',
      deviceFingerprintHash: 'api-contract-$subject',
      platform: 'web',
      appVersion: 'api-integration',
    );
    final session = await accountSessions.loginAnonymous(command);
    _sessionBootstrapCommand = command;
    _session = session;
    _ownerId = session.ownerId;
    _personaId = session.activePersona?.personaId;
    _tokenProvider.accessToken = session.accessToken;
    return session;
  }

  Future<AuthSessionGrant> replayAnonymousLogin() async {
    final original = session;
    _tokenProvider.accessToken = null;
    final replay = await accountSessions.loginAnonymous(
      sessionBootstrapCommand,
    );
    _tokenProvider.accessToken = original.accessToken;
    return replay;
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
    final surface = _surfaceForClientPage(clientPageId);
    return CloudOperationInvocationContext(
      surfaceId: surface.id,
      routeId: surface.routeId,
      clientPageId: clientPageId,
      idempotencyKey: clientPageId == UserRequestPageIds.closeAccount
          ? 'user-close-contract-${DateTime.now().microsecondsSinceEpoch}'
          : null,
      actor: CloudOperationActorContext(
        accountId: _ownerId,
        personaId: _personaId,
        deviceActorId: userApiContractDeviceId,
      ),
    );
  }
}

AppUiSurface _surfaceForClientPage(String clientPageId) {
  if (clientPageId == UserRequestPageIds.loginAnonymous ||
      clientPageId == UserRequestPageIds.refreshToken) {
    return AppUiSurfaces.appShell;
  }
  if (clientPageId == UserRequestPageIds.getNotificationSettings ||
      clientPageId == UserRequestPageIds.updateNotificationSettings) {
    return AppUiSurfaces.settingsNotifications;
  }
  if (clientPageId == UserRequestPageIds.getPrivacySettings ||
      clientPageId == UserRequestPageIds.updatePrivacySettings) {
    return AppUiSurfaces.settingsPrivacy;
  }
  if (clientPageId == UserRequestPageIds.getCallSettings ||
      clientPageId == UserRequestPageIds.updateCallSettings) {
    return AppUiSurfaces.settingsCalls;
  }
  if (clientPageId == UserRequestPageIds.logout ||
      clientPageId == UserRequestPageIds.closeAccount) {
    return AppUiSurfaces.settingsAccountSecurity;
  }
  if (clientPageId == UserRequestPageIds.blockUser ||
      clientPageId == UserRequestPageIds.unblockUser ||
      clientPageId == UserRequestPageIds.listBlockedUsers) {
    return AppUiSurfaces.blockedUsers;
  }
  throw StateError('unsupported User API contract clientPageId: $clientPageId');
}

final class _MutableAccessTokenProvider implements CloudAuthTokenProvider {
  String? accessToken;

  @override
  Future<String?> getAccessToken() async => accessToken;
}

final class _UserApiClientContext implements CloudClientContextProvider {
  const _UserApiClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'user-identity-api-contract',
      deviceActorId: userApiContractDeviceId,
      platform: 'web',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}
