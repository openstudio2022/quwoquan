/// RTC CallSession Gamma Remote API contract runner.
///
/// 此 runner 只经 generated Cloud client 与 production Remote Facet 操作真实网关：
/// 两个短期匿名会话互相关注后，验证 1:1 视频通话的授权、生命周期、媒体控制、
/// 屏幕共享、历史回读与非参与者 BOLA 拒绝。它不注入身份 header、Mock 或 test-only
/// 服务端旁路。
///
/// 执行：
/// ```
/// flutter test test/api_integration/cloud/rtc/rtc_api_contract_runner.dart \
///   --dart-define=API_CONTRACT_ENV=gamma \
///   --dart-define=API_CONTRACT_BASE_URL=<topology publicBases.api>
/// ```
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/remote/rtc/call_session/call_lifecycle_remote.dart';
import 'package:quwoquan_app/cloud/remote/rtc/call_session/call_media_control_remote.dart';
import 'package:quwoquan_app/cloud/remote/rtc/call_session/call_participant_remote.dart';
import 'package:quwoquan_app/cloud/remote/rtc/call_session/call_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/rtc/call_session/call_screen_share_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/account_session/account_session_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/persona_relationship/persona_relationship_follow_remote.dart'
    as relationship_follow;
import 'package:quwoquan_app/cloud/remote/user/persona_relationship/persona_relationship_remote.dart'
    as relationship_capability;
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/cloud/runtime/generated/rtc/rtc_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../support/recording_cloud_operation_telemetry_sink.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBase = String.fromEnvironment('API_CONTRACT_BASE_URL');

late _GammaRtcActor _caller;
late _GammaRtcActor _callee;
late _GammaRtcActor _intruder;
final _createdActors = <_GammaRtcActor>[];

void main() {
  setUpAll(() async {
    if (_apiContractEnv != 'gamma') {
      throw StateError(
        'RTC API contract runner only permits gamma, got $_apiContractEnv',
      );
    }
    if (_apiBase.trim().isEmpty) {
      throw StateError('L3: ${_apiContractEnv.toUpperCase()}_BASE_URL not set');
    }
    final runId = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
    _caller = await _GammaRtcActor.signIn(
      label: 'caller',
      runId: runId,
      gatewayBaseUri: Uri.parse(_apiBase),
    );
    _createdActors.add(_caller);
    _callee = await _GammaRtcActor.signIn(
      label: 'callee',
      runId: runId,
      gatewayBaseUri: Uri.parse(_apiBase),
    );
    _createdActors.add(_callee);
    _intruder = await _GammaRtcActor.signIn(
      label: 'intruder',
      runId: runId,
      gatewayBaseUri: Uri.parse(_apiBase),
    );
    _createdActors.add(_intruder);

    await _caller.follow(_callee.personaId);
    await _callee.follow(_caller.personaId);
    final callerCapability = await _caller.getRelationshipCapability(
      _callee.personaId,
    );
    final calleeCapability = await _callee.getRelationshipCapability(
      _caller.personaId,
    );
    expect(callerCapability.canStartVoiceCall, isTrue);
    expect(calleeCapability.canStartVoiceCall, isTrue);
  });

  tearDownAll(() async {
    for (final actor in _createdActors.reversed) {
      await actor.close();
    }
  });

  test(
    'generated RTC Remote facets preserve Gamma lifecycle and reject BOLA',
    () async {
      final initiated = await _caller.lifecycle.initiateCall(
        RtcInitiateCallCommand(
          callType: CallType.video,
          inviteeIds: <String>[_callee.personaId],
          maxParticipants: 2,
        ),
      );
      final callId = initiated.session.callId;
      expect(callId, isNotEmpty);
      expect(initiated.session.callType, CallType.video);
      expect(initiated.session.status, CallStatus.ringing);
      expect(initiated.session.initiatorId, _caller.personaId);
      expect(initiated.mediaAccess.accessToken, isNotEmpty);

      final callerHistory = await _caller.query.listCalls(
        RtcListCallsQuery(limit: 10),
      );
      expect(
        callerHistory.items.any((session) => session.callId == callId),
        isTrue,
      );

      await expectLater(
        _intruder.query.getCall(RtcGetCallQuery(callId: callId)),
        throwsA(
          isA<CloudException>().having(
            (error) => error.runtimeFailure.code,
            'runtime failure code',
            'RTC.USER.not_participant',
          ),
        ),
      );

      final answered = await _callee.lifecycle.answerCall(
        RtcCallIdCommand(callId: callId),
      );
      expect(answered.session.callId, callId);
      expect(answered.session.status, CallStatus.connecting);
      expect(answered.mediaAccess.accessToken, isNotEmpty);

      final callerJoin = await _caller.participants.joinCall(
        RtcCallIdCommand(callId: callId),
      );
      final calleeJoin = await _callee.participants.joinCall(
        RtcCallIdCommand(callId: callId),
      );
      expect(callerJoin.session.callId, callId);
      expect(callerJoin.mediaAccess.accessToken, isNotEmpty);
      expect(calleeJoin.session.callId, callId);
      expect(calleeJoin.mediaAccess.accessToken, isNotEmpty);

      await _caller.participants.reportMediaConnected(
        RtcCallIdCommand(callId: callId),
      );
      final connected = await _callee.participants.reportMediaConnected(
        RtcCallIdCommand(callId: callId),
      );
      expect(connected.status, CallStatus.inCall);
      expect(connected.startedAt, isNotNull);

      final muted = await _caller.media.toggleMute(
        RtcToggleMuteCommand(callId: callId, muted: true),
      );
      expect(
        muted.participants.any(
          (participant) =>
              participant.userId == _caller.personaId && participant.isMuted,
        ),
        isTrue,
      );

      final sharing = await _callee.screenShare.startScreenShare(
        RtcCallIdCommand(callId: callId),
      );
      expect(sharing.isScreenSharing, isTrue);
      expect(sharing.screenShareUserId, _callee.personaId);
      final shareStopped = await _callee.screenShare.stopScreenShare(
        RtcCallIdCommand(callId: callId),
      );
      expect(shareStopped.isScreenSharing, isFalse);

      final ended = await _caller.lifecycle.hangupCall(
        RtcCallIdCommand(callId: callId),
      );
      expect(ended.status, CallStatus.ended);
      expect(ended.endReason, EndReason.normal);

      final readback = await _callee.query.getCall(
        RtcGetCallQuery(callId: callId),
      );
      expect(readback.status, CallStatus.ended);
      expect(readback.endReason, EndReason.normal);
      expect(
        _caller.telemetry.events.every((event) => event.succeeded),
        isTrue,
      );
      expect(
        _callee.telemetry.events.every((event) => event.succeeded),
        isTrue,
      );
      expect(_intruder.telemetry.events.last.succeeded, isFalse);
    },
  );
}

final class _MutableAccessTokenProvider implements CloudAuthTokenProvider {
  String? accessToken;

  @override
  Future<String?> getAccessToken() async => accessToken;
}

final class _GammaRtcClientContext implements CloudClientContextProvider {
  const _GammaRtcClientContext(this._deviceActorId);

  final String _deviceActorId;

  @override
  CloudClientContextSnapshot snapshot() => CloudClientContextSnapshot(
    sessionId: 'rtc-api-contract-$_deviceActorId',
    deviceActorId: _deviceActorId,
    platform: 'test',
    appVersion: 'api-integration',
    locale: 'zh-CN',
  );
}

final class _GammaRtcActor {
  _GammaRtcActor._({
    required this.label,
    required this.runId,
    required this._gatewayBaseUri,
  }) : _deviceActorId = 'rtc-api-contract-$runId-$label-device' {
    _httpClient = CloudHttpClient(authTokenProvider: _tokenProvider);
    _client = buildGeneratedCloudOperationClient(
      httpClient: _httpClient,
      clientContextProvider: _GammaRtcClientContext(_deviceActorId),
      telemetrySink: telemetry,
      environment: CloudRuntimeEnvironment(
        environment: CloudEnvironment.gamma,
        gatewayBaseUri: _gatewayBaseUri,
      ),
    );
    accountSessions = RemoteAccountSessionCommandWriter(
      client: _client,
      invocationContext: _accountInvocationContext,
    );
    lifecycle = RemoteCallLifecycleCommandWriter(
      client: _client,
      invocationContext: _rtcInvocationContext,
    );
    participants = RemoteCallParticipantCommandWriter(
      client: _client,
      invocationContext: _rtcInvocationContext,
    );
    media = RemoteCallMediaControlWriter(
      client: _client,
      invocationContext: _rtcInvocationContext,
    );
    screenShare = RemoteCallScreenShareWriter(
      client: _client,
      invocationContext: _rtcInvocationContext,
    );
    query = RemoteCallQuery(
      client: _client,
      invocationContext: _rtcInvocationContext,
    );
    relationshipFollow =
        relationship_follow.RemotePersonaRelationshipFollowAdapter(
          client: _client,
          invocationContext: _relationshipCommandInvocationContext,
        );
    relationshipCapability =
        relationship_capability.RemotePersonaRelationshipFacet(
          client: _client,
          invocationContext: _relationshipQueryInvocationContext,
        );
  }

  final String label;
  final String runId;
  final Uri _gatewayBaseUri;
  final String _deviceActorId;
  final _MutableAccessTokenProvider _tokenProvider =
      _MutableAccessTokenProvider();
  final RecordingCloudOperationTelemetrySink telemetry =
      RecordingCloudOperationTelemetrySink();

  late final CloudHttpClient _httpClient;
  late final GeneratedCloudOperationClient _client;
  late final RemoteAccountSessionCommandWriter accountSessions;
  late final RemoteCallLifecycleCommandWriter lifecycle;
  late final RemoteCallParticipantCommandWriter participants;
  late final RemoteCallMediaControlWriter media;
  late final RemoteCallScreenShareWriter screenShare;
  late final RemoteCallQuery query;
  late final relationship_follow.RemotePersonaRelationshipFollowAdapter
  relationshipFollow;
  late final relationship_capability.RemotePersonaRelationshipFacet
  relationshipCapability;
  AuthSessionGrant? _session;

  String get accountId => _requireSession().ownerId;

  String get personaId => _requireSession().activePersona!.personaId;

  static Future<_GammaRtcActor> signIn({
    required String label,
    required String runId,
    required Uri gatewayBaseUri,
  }) async {
    final actor = _GammaRtcActor._(
      label: label,
      runId: runId,
      gatewayBaseUri: gatewayBaseUri,
    );
    final identitySeed = 'rtc-api-contract-$runId-$label';
    final session = await actor.accountSessions.loginAnonymous(
      LoginAnonymousCommand(
        installId: '$identitySeed-install',
        deviceFingerprintHash: '$identitySeed-fingerprint',
        platform: 'test',
        appVersion: 'api-integration',
      ),
    );
    if (session.activePersona == null) {
      actor._httpClient.close();
      throw StateError('anonymous login omitted activePersona for $label');
    }
    actor._session = session;
    actor._tokenProvider.accessToken = session.accessToken;
    return actor;
  }

  Future<void> follow(String targetPersonaId) => relationshipFollow.follow(
    targetPersonaId,
    sourceSurfaceId: AppUiSurfaces.userProfile.id,
  );

  Future<RelationshipCapabilityResult> getRelationshipCapability(
    String targetPersonaId,
  ) => relationshipCapability.getRelationshipCapability(
    GetRelationshipCapabilityQuery(targetPersonaId: targetPersonaId),
  );

  Future<void> close() async {
    final session = _session;
    if (session != null) {
      await accountSessions.logout(
        LogoutCommand(
          refreshToken: session.refreshToken,
          deviceId: _deviceActorId,
        ),
      );
    }
    _httpClient.close();
  }

  CloudOperationInvocationContext _accountInvocationContext(
    String clientPageId,
  ) {
    final surface = clientPageId == UserRequestPageIds.logout
        ? AppUiSurfaces.settingsAccountSecurity
        : AppUiSurfaces.appShell;
    return _invocationContext(
      surface: surface,
      clientPageId: clientPageId,
      command: false,
    );
  }

  CloudOperationInvocationContext _relationshipCommandInvocationContext(
    String clientPageId,
    String canonicalOperationId,
  ) => _invocationContext(
    surface: AppUiSurfaces.userProfile,
    clientPageId: clientPageId,
    command: true,
    idempotencySuffix: canonicalOperationId,
  );

  CloudOperationInvocationContext _relationshipQueryInvocationContext(
    String clientPageId,
  ) => _invocationContext(
    surface: AppUiSurfaces.userProfile,
    clientPageId: clientPageId,
    command: false,
  );

  CloudOperationInvocationContext _rtcInvocationContext(
    String clientPageId, {
    required bool command,
  }) => _invocationContext(
    surface: _rtcSurfaceFor(clientPageId),
    clientPageId: clientPageId,
    command: command,
  );

  CloudOperationInvocationContext _invocationContext({
    required AppUiSurface surface,
    required String clientPageId,
    required bool command,
    String? idempotencySuffix,
  }) => CloudOperationInvocationContext(
    surfaceId: surface.id,
    routeId: surface.routeId,
    clientPageId: clientPageId,
    idempotencyKey: command
        ? 'rtc-api-contract-$runId-$label-'
              '${idempotencySuffix ?? clientPageId}'
        : null,
    actor: CloudOperationActorContext(
      accountId: _session?.ownerId,
      personaId: _session?.activePersona?.personaId,
      deviceActorId: _deviceActorId,
    ),
  );

  AppUiSurface _rtcSurfaceFor(String clientPageId) {
    switch (clientPageId) {
      case RtcRequestPageIds.initiateCall:
      case RtcRequestPageIds.inviteToCall:
        return AppUiSurfaces.rtcPickParticipants;
      case RtcRequestPageIds.answerCall:
      case RtcRequestPageIds.rejectCall:
        return AppUiSurfaces.rtcIncoming;
      case RtcRequestPageIds.cancelCall:
        return AppUiSurfaces.rtcOutgoing;
      case RtcRequestPageIds.listCalls:
        return AppUiSurfaces.chatList;
      case RtcRequestPageIds.getCall:
      case RtcRequestPageIds.hangupCall:
      case RtcRequestPageIds.joinCall:
      case RtcRequestPageIds.leaveCall:
      case RtcRequestPageIds.reportMediaConnected:
      case RtcRequestPageIds.startScreenShare:
      case RtcRequestPageIds.stopScreenShare:
      case RtcRequestPageIds.toggleCamera:
      case RtcRequestPageIds.toggleMute:
        return AppUiSurfaces.rtcVoice;
    }
    throw StateError('unsupported RTC clientPageId: $clientPageId');
  }

  AuthSessionGrant _requireSession() {
    final session = _session;
    if (session == null || session.activePersona == null) {
      throw StateError('Gamma RTC actor $label is not signed in');
    }
    return session;
  }
}
