import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/di/entity_dependencies.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_search_reader.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_app/service/user_service/account/device_registration/adapters/device_push_endpoint_remote.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/account_lifecycle_remote.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/user_profile_query_remote.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/user_sync_remote.dart';
import 'package:quwoquan_app/service/user_service/account/user_settings/adapters/user_settings_remote.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/persona_remote.dart';
import 'package:quwoquan_app/service/user_service/profile_projection/following_subject/adapters/following_subject_remote.dart';
import 'package:quwoquan_app/service/user_service/relationship/followed_subject_visit_state/adapters/followed_subject_visit_state_remote.dart';
import 'package:quwoquan_app/service/user_service/relationship/greeting_request/adapters/greeting_request_remote.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/adapters/persona_relationship_follow_remote.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/adapters/persona_relationship_remote.dart';
import 'package:quwoquan_app/service/user_service/relationship/subject_follow/adapters/subject_follow_remote.dart';
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
    required this.userProfiles,
    required this.userSync,
    required this.devicePushEndpoints,
    required this.homepageSearch,
    required this.subjectFollows,
    required this.followingSubjects,
    required this.followedSubjectVisits,
    required this.greetingRequests,
    required this.personaRelationshipFollows,
    required this.personaCommands,
    required this.settingsReader,
    required this.settingsCommands,
    required this.personaRelationships,
  });

  static Future<UserApiContractHarness> create() async {
    if (_apiBase.isEmpty) {
      throw StateError('L3: API_CONTRACT_BASE_URL not set');
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
    CloudOperationInvocationContext invocationContext(
      String clientPageId, {
      String? idempotencyKey,
    }) => harness._invocationContext(
      clientPageId,
      idempotencyKey: idempotencyKey,
    );
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
      userProfiles: RemoteUserProfileQueryFacet(
        client: client,
        invocationContext: (clientPageId, _) =>
            harness._invocationContext(clientPageId),
      ),
      userSync: RemoteUserSyncRepository(
        client: client,
        invocationContext: invocationContext,
      ),
      devicePushEndpoints: RemoteDevicePushEndpointWriter(
        client: client,
        invocationContext: invocationContext,
        clientContextSnapshot: clientContext.snapshot,
      ),
      homepageSearch: EntityProductionComposition.homepageQueryFacets(
        client: client,
        detailInvocationContext: (clientPageId, {cancellation, deadlineAt}) =>
            harness._invocationContextForSurface(
              AppUiSurfaces.homepageDetail,
              clientPageId,
              cancellation: cancellation,
              deadlineAt: deadlineAt,
            ),
        introductionInvocationContext:
            (clientPageId, {cancellation, deadlineAt}) =>
                harness._invocationContextForSurface(
                  AppUiSurfaces.homepageIntroduction,
                  clientPageId,
                  cancellation: cancellation,
                  deadlineAt: deadlineAt,
                ),
        searchInvocationContext: (clientPageId, {cancellation, deadlineAt}) =>
            harness._invocationContextForSurface(
              AppUiSurfaces.homepagePicker,
              clientPageId,
              cancellation: cancellation,
              deadlineAt: deadlineAt,
            ),
      ).query,
      subjectFollows: RemoteSubjectFollowFacet(
        client: client,
        invocationContext: invocationContext,
      ),
      followingSubjects: RemoteFollowingSubjectReader(
        client: client,
        invocationContext: (clientPageId, {idempotencyKey}) => harness
            ._invocationContext(clientPageId, idempotencyKey: idempotencyKey),
      ),
      followedSubjectVisits: RemoteFollowedSubjectVisitStateWriter(
        client: client,
        invocationContext: (clientPageId, {idempotencyKey}) => harness
            ._invocationContext(clientPageId, idempotencyKey: idempotencyKey),
      ),
      greetingRequests: RemoteGreetingRequestFacet(
        client: client,
        invocationContext: invocationContext,
      ),
      personaRelationshipFollows: RemotePersonaRelationshipFollowAdapter(
        client: client,
        invocationContext: (clientPageId, _) {
          final idempotencyKey = switch (clientPageId) {
            UserRequestPageIds.followUser || UserRequestPageIds.unfollowUser =>
              harness._activeIdempotencyKey ??
                  (throw StateError(
                    '$clientPageId requires an explicit idempotency scope',
                  )),
            _ => null,
          };
          return harness._invocationContextForSurface(
            AppUiSurfaces.userProfile,
            clientPageId,
            idempotencyKey: idempotencyKey,
          );
        },
      ),
      personaCommands: RemotePersonaCommandWriter(
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
  final RemoteUserProfileQueryFacet userProfiles;
  final RemoteUserSyncRepository userSync;
  final RemoteDevicePushEndpointWriter devicePushEndpoints;
  final HomepageSearchReader homepageSearch;
  final RemoteSubjectFollowFacet subjectFollows;
  final RemoteFollowingSubjectReader followingSubjects;
  final RemoteFollowedSubjectVisitStateWriter followedSubjectVisits;
  final RemoteGreetingRequestFacet greetingRequests;
  final RemotePersonaRelationshipFollowAdapter personaRelationshipFollows;
  final RemotePersonaCommandWriter personaCommands;
  final RemoteUserSettingsQueryReader settingsReader;
  final RemoteUserSettingsCommandWriter settingsCommands;
  final RemotePersonaRelationshipFacet personaRelationships;

  AuthSessionGrant? _session;
  LoginAnonymousCommand? _sessionBootstrapCommand;
  String? _ownerId;
  String? _personaId;
  String? _activeIdempotencyKey;

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

  Future<T> withTemporaryAccessToken<T>({
    required String accessToken,
    required Future<T> Function() action,
  }) async {
    final current = _tokenProvider.accessToken;
    _tokenProvider.accessToken = accessToken;
    try {
      return await action();
    } finally {
      _tokenProvider.accessToken = current;
    }
  }

  Future<T> withSession<T>({
    required AuthSessionGrant session,
    required Future<T> Function() action,
  }) async {
    final currentAccessToken = _tokenProvider.accessToken;
    final currentOwnerId = _ownerId;
    final currentPersonaId = _personaId;
    _tokenProvider.accessToken = session.accessToken;
    _ownerId = session.ownerId;
    _personaId = session.activePersona?.personaId;
    try {
      return await action();
    } finally {
      _tokenProvider.accessToken = currentAccessToken;
      _ownerId = currentOwnerId;
      _personaId = currentPersonaId;
    }
  }

  Future<T> withIdempotencyKey<T>({
    required String idempotencyKey,
    required Future<T> Function() action,
  }) async {
    final normalized = idempotencyKey.trim();
    if (normalized.isEmpty) {
      throw ArgumentError.value(idempotencyKey, 'idempotencyKey');
    }
    if (_activeIdempotencyKey != null) {
      throw StateError('nested User API idempotency scope is not allowed');
    }
    _activeIdempotencyKey = normalized;
    try {
      return await action();
    } finally {
      _activeIdempotencyKey = null;
    }
  }

  Future<ActivePersonaContextView> activatePersona(
    ActivatePersonaCommand command,
  ) async {
    final context = await personaCommands.activatePersona(command);
    _personaId = context.personaId;
    return context;
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
    String? idempotencyKey,
  }) {
    return _invocationContextForSurface(
      _surfaceForClientPage(clientPageId),
      clientPageId,
      idempotencyKey: idempotencyKey,
    );
  }

  CloudOperationInvocationContext _invocationContextForSurface(
    AppUiSurface surface,
    String clientPageId, {
    String? idempotencyKey,
    DateTime? deadlineAt,
    CloudOperationCancellationSignal? cancellation,
  }) {
    final requiresExplicitIdempotencyKey =
        clientPageId == UserRequestPageIds.followSubject ||
        clientPageId == UserRequestPageIds.unfollowSubject ||
        clientPageId == UserRequestPageIds.createPersona ||
        clientPageId == UserRequestPageIds.updatePersona ||
        clientPageId == UserRequestPageIds.applyPersonaProfileSync ||
        clientPageId == UserRequestPageIds.retirePersona ||
        clientPageId == UserRequestPageIds.activatePersona ||
        clientPageId == UserRequestPageIds.sendGreetingRequest ||
        clientPageId == UserRequestPageIds.replyGreetingRequest ||
        clientPageId == UserRequestPageIds.ignoreGreetingRequest ||
        clientPageId == UserRequestPageIds.cancelGreetingRequest;
    final resolvedIdempotencyKey =
        idempotencyKey ??
        (requiresExplicitIdempotencyKey
            ? _activeIdempotencyKey ??
                  (throw StateError(
                    '$clientPageId requires an explicit idempotency scope',
                  ))
            : clientPageId == UserRequestPageIds.closeAccount
            ? _activeIdempotencyKey ??
                  'user-close-contract-${DateTime.now().microsecondsSinceEpoch}'
            : null);
    return CloudOperationInvocationContext(
      surfaceId: surface.id,
      routeId: surface.routeId,
      clientPageId: clientPageId,
      idempotencyKey: resolvedIdempotencyKey,
      deadlineAt: deadlineAt,
      cancellation: cancellation,
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
      clientPageId == UserRequestPageIds.updateNotificationSettings ||
      clientPageId == UserRequestPageIds.upsertDevicePushEndpoint ||
      clientPageId == UserRequestPageIds.removeDevicePushEndpoint) {
    return AppUiSurfaces.settingsNotifications;
  }
  if (clientPageId == UserRequestPageIds.followSubject ||
      clientPageId == UserRequestPageIds.unfollowSubject) {
    return AppUiSurfaces.homepageDetail;
  }
  if (clientPageId == UserRequestPageIds.listFollowingSubjects ||
      clientPageId == UserRequestPageIds.markFollowedSubjectVisited) {
    return AppUiSurfaces.homeFeed;
  }
  if (clientPageId == UserRequestPageIds.createPersona ||
      clientPageId == UserRequestPageIds.updatePersona ||
      clientPageId == UserRequestPageIds.applyPersonaProfileSync ||
      clientPageId == UserRequestPageIds.retirePersona ||
      clientPageId == UserRequestPageIds.activatePersona) {
    return AppUiSurfaces.profilePersonas;
  }
  if (clientPageId == UserRequestPageIds.listPersonas ||
      clientPageId == UserRequestPageIds.getPersonaManagementSummary ||
      clientPageId == UserRequestPageIds.getPersonaLifecycleGuard) {
    return AppUiSurfaces.profilePersonas;
  }
  if (clientPageId == UserRequestPageIds.getActivePersonaContext) {
    return AppUiSurfaces.appShell;
  }
  if (clientPageId == UserRequestPageIds.getPersonaProfile ||
      clientPageId == UserRequestPageIds.getUserHomepageBundle) {
    return AppUiSurfaces.userProfile;
  }
  if (clientPageId == UserRequestPageIds.getMeProfile) {
    return AppUiSurfaces.profileHome;
  }
  if (clientPageId == UserRequestPageIds.searchSocialRelations) {
    return AppUiSurfaces.addContactSearch;
  }
  if (clientPageId == UserRequestPageIds.getProfileEditSnapshot) {
    return AppUiSurfaces.profileEdit;
  }
  if (clientPageId == UserRequestPageIds.getProfileQrCard) {
    return AppUiSurfaces.myQrCode;
  }
  if (clientPageId == UserRequestPageIds.resolveProfileQrToken) {
    return AppUiSurfaces.addContactScan;
  }
  if (clientPageId == UserRequestPageIds.pullUserSync) {
    return AppUiSurfaces.chatList;
  }
  if (clientPageId == UserRequestPageIds.sendGreetingRequest ||
      clientPageId == UserRequestPageIds.getRelationshipCapability) {
    return AppUiSurfaces.userProfile;
  }
  if (clientPageId == UserRequestPageIds.listGreetingInbox ||
      clientPageId == UserRequestPageIds.listGreetingOutbox ||
      clientPageId == UserRequestPageIds.replyGreetingRequest ||
      clientPageId == UserRequestPageIds.ignoreGreetingRequest ||
      clientPageId == UserRequestPageIds.cancelGreetingRequest) {
    return AppUiSurfaces.greetingInbox;
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
