import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/di/circle_dependencies.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group/application/public/circle_group_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group_membership/application/public/circle_group_membership_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/application/public/circle_membership_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_file/application/public/circle_file_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering_plan/adapters/gathering_plan_remote.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_post_placement/application/public/circle_post_placement_commands.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/account_lifecycle_remote.dart';
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
    required this._accountLifecycle,
    required this.behaviorFacts,
    required this.lifecycle,
    required this.query,
    required this.membership,
    required this.membershipQueries,
    required this.pendingMemberships,
    required this.fileWriter,
    required this.fileReader,
    required this.groupCommands,
    required this.groupQueries,
    required this.groupMembershipCommands,
    required this.groupMembershipQueries,
    required this.postPlacement,
    required this.gatheringPlans,
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
      accountLifecycle: RemoteAccountLifecycleCommandWriter(
        client: client,
        invocationContext: (clientPageId) =>
            harness._accountInvocationContext(clientPageId),
      ),
      behaviorFacts:
          CircleProductionComposition.generatedAdapter<
            CircleBehaviorFactWriter
          >(
            CircleProductionAdapter.behaviorFact,
            client: client,
            invocationContext: invocationContext,
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
      membershipQueries:
          CircleProductionComposition.generatedAdapter<CircleMembershipQueries>(
            CircleProductionAdapter.membership,
            client: client,
            invocationContext: invocationContext,
          ),
      pendingMemberships:
          CircleProductionComposition.generatedAdapter<
            PendingCircleMemberships
          >(
            CircleProductionAdapter.membership,
            client: client,
            invocationContext: invocationContext,
          ),
      fileWriter:
          CircleProductionComposition.generatedAdapter<CircleFileWriter>(
            CircleProductionAdapter.file,
            client: client,
            invocationContext: invocationContext,
          ),
      fileReader:
          CircleProductionComposition.generatedAdapter<CircleFileReader>(
            CircleProductionAdapter.file,
            client: client,
            invocationContext: invocationContext,
          ),
      groupCommands:
          CircleProductionComposition.generatedAdapter<CircleGroupCommands>(
            CircleProductionAdapter.group,
            client: client,
            invocationContext: invocationContext,
          ),
      groupQueries:
          CircleProductionComposition.generatedAdapter<CircleGroupQueries>(
            CircleProductionAdapter.group,
            client: client,
            invocationContext: invocationContext,
          ),
      groupMembershipCommands:
          CircleProductionComposition.generatedAdapter<
            CircleGroupMembershipCommands
          >(
            CircleProductionAdapter.groupMembership,
            client: client,
            invocationContext: invocationContext,
          ),
      groupMembershipQueries:
          CircleProductionComposition.generatedAdapter<
            CircleGroupMembershipQueries
          >(
            CircleProductionAdapter.groupMembership,
            client: client,
            invocationContext: invocationContext,
          ),
      postPlacement:
          CircleProductionComposition.generatedAdapter<
            CirclePostPlacementCommands
          >(
            CircleProductionAdapter.postPlacement,
            client: client,
            invocationContext: (String clientPageId, String idempotencyKey) =>
                harness._postPlacementInvocationContext(
                  clientPageId,
                  idempotencyKey,
                ),
          ),
      gatheringPlans: RemoteGatheringPlanFacet(
        client: client,
        invocationContext: (clientPageId, {idempotencyKey}) =>
            harness._gatheringPlanInvocationContext(clientPageId),
      ),
    );
    return harness;
  }

  static Future<CircleApiContractHarness> createManaged({
    required String accessToken,
    required String accountId,
    required String personaId,
  }) async {
    final token = accessToken.trim();
    final account = accountId.trim();
    final persona = personaId.trim();
    if (_apiContractEnv != 'gamma') {
      throw StateError('managed Circle API contract runner requires gamma');
    }
    if (token.isEmpty || account.isEmpty || persona.isEmpty) {
      throw StateError('managed Circle actor identity is incomplete');
    }
    final harness = await create();
    harness._tokenProvider.accessToken = token;
    harness._ownerId = account;
    harness._personaId = persona;
    return harness;
  }

  final CloudHttpClient _httpClient;
  final ProductionCloudOperationTelemetryEvidence telemetry;
  final _MutableAccessTokenProvider _tokenProvider;
  final RemoteAccountSessionCommandWriter accountSessions;
  final RemoteAccountLifecycleCommandWriter _accountLifecycle;
  final CircleBehaviorFactWriter behaviorFacts;
  final CircleLifecycleCommandWriter lifecycle;
  final CircleQueryReader query;
  final CircleMembershipCommands membership;
  final CircleMembershipQueries membershipQueries;
  final PendingCircleMemberships pendingMemberships;
  final CircleFileWriter fileWriter;
  final CircleFileReader fileReader;
  final CircleGroupCommands groupCommands;
  final CircleGroupQueries groupQueries;
  final CircleGroupMembershipCommands groupMembershipCommands;
  final CircleGroupMembershipQueries groupMembershipQueries;
  final CirclePostPlacementCommands postPlacement;
  final RemoteGatheringPlanFacet gatheringPlans;

  AuthSessionGrant? _session;
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
    _session = session;
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
      final session = _session;
      if (session != null) {
        await _accountLifecycle.closeAccount(
          CloseAccountCommand(
            clientRequestId: 'circle-api-cleanup-${session.ownerId}',
          ),
        );
      }
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
      CircleRequestPageIds.reportCircleBehavior ||
      CircleRequestPageIds.updateCircle ||
      CircleRequestPageIds.archiveCircle ||
      CircleRequestPageIds.getCircle ||
      CircleRequestPageIds.joinCircle ||
      CircleRequestPageIds.leaveCircle ||
      CircleRequestPageIds.createCircleGroup ||
      CircleRequestPageIds.updateCircleGroup ||
      CircleRequestPageIds.archiveCircleGroup ||
      CircleRequestPageIds.getCircleGroup ||
      CircleRequestPageIds.listCircleGroups ||
      CircleRequestPageIds.searchCircleGroups ||
      CircleRequestPageIds.applyJoinCircleGroup ||
      CircleRequestPageIds.leaveCircleGroup ||
      CircleRequestPageIds.approveCircleGroupMember ||
      CircleRequestPageIds.rejectCircleGroupMember ||
      CircleRequestPageIds.removeCircleGroupMember ||
      CircleRequestPageIds.updateCircleGroupMemberRole ||
      CircleRequestPageIds.getMyCircleGroupMembership ||
      CircleRequestPageIds.listCircleGroupMemberships ||
      CircleRequestPageIds.getMyCircleMembership ||
      CircleRequestPageIds.listCircleMemberships ||
      CircleRequestPageIds.listPendingCircleMemberships ||
      CircleRequestPageIds.listCircleFiles ||
      CircleRequestPageIds.getCircleFile ||
      CircleRequestPageIds.createCircleFile ||
      CircleRequestPageIds.updateCircleFile ||
      CircleRequestPageIds.deleteCircleFile => AppUiSurfaces.circleDetail,
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

  CloudOperationInvocationContext _gatheringPlanInvocationContext(
    String clientPageId,
  ) {
    if (clientPageId != CircleRequestPageIds.getGatheringPlan) {
      throw StateError('Unsupported GatheringPlan clientPageId: $clientPageId');
    }
    return CloudOperationInvocationContext(
      surfaceId: AppUiSurfaces.gatheringBoard.id,
      routeId: AppUiSurfaces.gatheringBoard.routeId,
      clientPageId: clientPageId,
      actor: CloudOperationActorContext(
        accountId: _ownerId,
        personaId: _personaId,
        deviceActorId: circleApiContractDeviceId,
      ),
    );
  }

  CloudOperationInvocationContext _accountInvocationContext(
    String clientPageId,
  ) {
    if (clientPageId != UserRequestPageIds.closeAccount) {
      throw StateError(
        'Unsupported Circle account cleanup clientPageId: $clientPageId',
      );
    }
    return CloudOperationInvocationContext(
      surfaceId: AppUiSurfaces.settingsAccountSecurity.id,
      routeId: AppUiSurfaces.settingsAccountSecurity.routeId,
      clientPageId: clientPageId,
      idempotencyKey: 'circle-api-account-cleanup-$_ownerId',
      actor: CloudOperationActorContext(
        accountId: _ownerId,
        personaId: _personaId,
        deviceActorId: circleApiContractDeviceId,
      ),
    );
  }

  CloudOperationInvocationContext _postPlacementInvocationContext(
    String clientPageId,
    String idempotencyKey,
  ) {
    switch (clientPageId) {
      case CircleRequestPageIds.placePostInCircle:
      case CircleRequestPageIds.removePostFromCircle:
      case CircleRequestPageIds.pinCirclePost:
      case CircleRequestPageIds.featureCirclePost:
        break;
      default:
        throw StateError(
          'Unsupported Circle post placement clientPageId: $clientPageId',
        );
    }
    final normalizedKey = idempotencyKey.trim();
    if (normalizedKey.isEmpty) {
      throw StateError('Circle post placement requires an idempotency key');
    }
    return CloudOperationInvocationContext(
      surfaceId: AppUiSurfaces.circleDetail.id,
      routeId: AppUiSurfaces.circleDetail.routeId,
      clientPageId: clientPageId,
      idempotencyKey: normalizedKey,
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
