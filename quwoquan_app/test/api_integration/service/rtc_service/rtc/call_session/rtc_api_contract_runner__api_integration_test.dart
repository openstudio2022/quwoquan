// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-002
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-003
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-008
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/media-infrastructure/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/one-to-one-call/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-002.t1
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-003.t4
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/media-infrastructure/spec.md#gwt-001.t1
// readiness_case: call_session_initiate_call_app_api
// readiness_case: call_session_list_calls_app_api
// readiness_case: call_session_get_call_app_api
// readiness_case: call_session_answer_call_app_api
// readiness_case: call_session_join_call_app_api
// readiness_case: call_session_report_media_connected_app_api
// readiness_case: call_session_toggle_mute_app_api
// readiness_case: call_session_start_screen_share_app_api
// readiness_case: call_session_stop_screen_share_app_api
// readiness_case: call_session_hangup_call_app_api
// readiness_case: call_session_reject_call_app_api
// readiness_case: call_session_cancel_call_app_api
// readiness_case: call_session_leave_call_app_api
// readiness_case: call_session_invite_to_call_app_api
// readiness_case: call_session_toggle_camera_app_api

/// RTC CallSession Gamma Remote API contract runner.
///
/// 此 runner 只经 generated Cloud client 与 production Remote Facet 操作真实网关：
/// 两个短期匿名会话互相关注后，验证 1:1 视频通话的授权、生命周期、媒体控制、
/// 屏幕共享、历史回读与非参与者 BOLA 拒绝。它不注入身份 header、Mock 或 test-only
/// 服务端旁路。
///
/// 执行：
/// ```
/// flutter test test/api_integration/service/rtc_service/rtc/call_session/rtc_api_contract_runner__api_integration_test.dart \
///   --dart-define=API_CONTRACT_ENV=gamma \
///   --dart-define=API_CONTRACT_BASE_URL=<topology publicBases.api>
/// ```
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/adapters/call_lifecycle_remote.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/adapters/call_media_control_remote.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/adapters/call_participant_remote.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/adapters/call_query_remote.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/adapters/call_screen_share_remote.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/adapters/persona_relationship_follow_remote.dart'
    as relationship_follow;
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/adapters/persona_relationship_remote.dart'
    as relationship_capability;
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/generated/rtc/rtc_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/production_cloud_operation_telemetry_evidence.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBase = String.fromEnvironment('API_CONTRACT_BASE_URL');

late _GammaRtcActor _caller;
late _GammaRtcActor _callee;
late _GammaRtcActor _intruder;
late _GammaRtcActor _bystander;
final _createdActors = <_GammaRtcActor>[];

void main() {
  setUpAll(() async {
    if (_apiContractEnv != 'gamma') {
      throw StateError(
        'RTC API contract runner only permits gamma, got $_apiContractEnv',
      );
    }
    if (_apiBase.trim().isEmpty) {
      throw StateError('L3: API_CONTRACT_BASE_URL not set');
    }
    final gatewayBaseUri = Uri.tryParse(_apiBase);
    if (gatewayBaseUri == null ||
        gatewayBaseUri.scheme != 'https' ||
        gatewayBaseUri.host != 'api.gamma.quwoquan.com') {
      throw StateError(
        'RTC API contract runner requires the canonical Gamma HTTPS endpoint',
      );
    }
    final runId = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
    _caller = await _GammaRtcActor.signIn(
      label: 'caller',
      runId: runId,
      gatewayBaseUri: gatewayBaseUri,
    );
    _createdActors.add(_caller);
    _callee = await _GammaRtcActor.signIn(
      label: 'callee',
      runId: runId,
      gatewayBaseUri: gatewayBaseUri,
    );
    _createdActors.add(_callee);
    _intruder = await _GammaRtcActor.signIn(
      label: 'intruder',
      runId: runId,
      gatewayBaseUri: gatewayBaseUri,
    );
    _createdActors.add(_intruder);
    _bystander = await _GammaRtcActor.signIn(
      label: 'bystander',
      runId: runId,
      gatewayBaseUri: gatewayBaseUri,
    );
    _createdActors.add(_bystander);

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
      final callId = initiated.session.id;
      expect(callId, isNotEmpty);
      expect(initiated.session.callType, CallType.video);
      expect(initiated.session.status, CallStatus.ringing);
      expect(initiated.session.initiatorId, _caller.personaId);
      expect(initiated.mediaAccess.accessToken, isNotEmpty);

      final callerHistory = await _caller.query.listCalls(
        RtcListCallsQuery(limit: 10),
      );
      expect(
        callerHistory.items.any((session) => session.id == callId),
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
      expect(answered.session.id, callId);
      expect(answered.session.status, CallStatus.connecting);
      expect(answered.mediaAccess.accessToken, isNotEmpty);

      final callerJoin = await _caller.participants.joinCall(
        RtcCallIdCommand(callId: callId),
      );
      final calleeJoin = await _callee.participants.joinCall(
        RtcCallIdCommand(callId: callId),
      );
      expect(callerJoin.session.id, callId);
      expect(callerJoin.mediaAccess.accessToken, isNotEmpty);
      expect(calleeJoin.session.id, callId);
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
        (muted.participants ?? const <CallParticipant>[]).any(
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
      final callerTelemetry = await _caller.telemetry.waitForEvents(
        minimumCount: 1,
      );
      final calleeTelemetry = await _callee.telemetry.waitForEvents(
        minimumCount: 1,
      );
      final intruderTelemetry = await _intruder.telemetry.waitForEvents(
        minimumCount: 1,
      );
      expect(callerTelemetry.every((event) => event.succeeded), isTrue);
      expect(calleeTelemetry.every((event) => event.succeeded), isTrue);
      expect(intruderTelemetry.last.succeeded, isFalse);
    },
  );

  test(
    'remaining RTC commands replay and preserve authoritative Gamma state',
    () async {
      final telemetry = _RtcTelemetryLedger();

      final rejectSession = await _initiateCall('reject', maxParticipants: 2);
      final rejectBefore = await _caller.query.getCall(
        RtcGetCallQuery(callId: rejectSession.id),
      );
      await _expectRtcFailure(
        telemetry.observe(
          AppCloudOperationIds.rtcCallSessionRejectCall,
          () => _bystander.withRtcIdempotencyKey(
            'reject-bola-${rejectSession.id}',
            () => _bystander.lifecycle.rejectCall(
              RtcCallIdCommand(callId: rejectSession.id),
            ),
          ),
        ),
        operationId: AppCloudOperationIds.rtcCallSessionRejectCall,
        code: 'RTC.USER.not_participant',
        statusCode: 403,
      );
      expect(
        (await _caller.query.getCall(
          RtcGetCallQuery(callId: rejectSession.id),
        )).toWire(),
        rejectBefore.toWire(),
      );
      final rejected = await _replaySessionCommand(
        telemetry,
        operationId: AppCloudOperationIds.rtcCallSessionRejectCall,
        actor: _callee,
        idempotencyKey: 'reject-${rejectSession.id}',
        command: () => _callee.lifecycle.rejectCall(
          RtcCallIdCommand(callId: rejectSession.id),
        ),
      );
      expect(rejected.first.status, CallStatus.ended);
      expect(rejected.first.endReason, EndReason.rejected);
      final rejectedReadback = await _caller.query.getCall(
        RtcGetCallQuery(callId: rejectSession.id),
      );
      expect(rejectedReadback.toWire(), rejected.first.toWire());

      final cancelSession = await _initiateCall('cancel', maxParticipants: 2);
      final cancelBefore = await _caller.query.getCall(
        RtcGetCallQuery(callId: cancelSession.id),
      );
      await _expectRtcFailure(
        telemetry.observe(
          AppCloudOperationIds.rtcCallSessionCancelCall,
          () => _bystander.withRtcIdempotencyKey(
            'cancel-bola-${cancelSession.id}',
            () => _bystander.lifecycle.cancelCall(
              RtcCallIdCommand(callId: cancelSession.id),
            ),
          ),
        ),
        operationId: AppCloudOperationIds.rtcCallSessionCancelCall,
        code: 'RTC.USER.not_participant',
        statusCode: 403,
      );
      expect(
        (await _caller.query.getCall(
          RtcGetCallQuery(callId: cancelSession.id),
        )).toWire(),
        cancelBefore.toWire(),
      );
      final cancelled = await _replaySessionCommand(
        telemetry,
        operationId: AppCloudOperationIds.rtcCallSessionCancelCall,
        actor: _caller,
        idempotencyKey: 'cancel-${cancelSession.id}',
        command: () => _caller.lifecycle.cancelCall(
          RtcCallIdCommand(callId: cancelSession.id),
        ),
      );
      expect(cancelled.first.status, CallStatus.ended);
      expect(cancelled.first.endReason, EndReason.cancelled);
      final cancelledReadback = await _callee.query.getCall(
        RtcGetCallQuery(callId: cancelSession.id),
      );
      expect(cancelledReadback.toWire(), cancelled.first.toWire());

      final leaveSession = await _connectCall('leave', maxParticipants: 2);
      final leaveBefore = await _caller.query.getCall(
        RtcGetCallQuery(callId: leaveSession.id),
      );
      await _expectRtcFailure(
        telemetry.observe(
          AppCloudOperationIds.rtcCallSessionLeaveCall,
          () => _bystander.withRtcIdempotencyKey(
            'leave-bola-${leaveSession.id}',
            () => _bystander.participants.leaveCall(
              RtcCallIdCommand(callId: leaveSession.id),
            ),
          ),
        ),
        operationId: AppCloudOperationIds.rtcCallSessionLeaveCall,
        code: 'RTC.USER.not_participant',
        statusCode: 403,
      );
      expect(
        (await _caller.query.getCall(
          RtcGetCallQuery(callId: leaveSession.id),
        )).toWire(),
        leaveBefore.toWire(),
      );
      final left = await _replaySessionCommand(
        telemetry,
        operationId: AppCloudOperationIds.rtcCallSessionLeaveCall,
        actor: _callee,
        idempotencyKey: 'leave-${leaveSession.id}',
        command: () => _callee.participants.leaveCall(
          RtcCallIdCommand(callId: leaveSession.id),
        ),
      );
      expect(left.first.status, CallStatus.ended);
      expect(left.first.endReason, EndReason.lastLeave);
      expect(
        _participant(left.first, _callee.personaId).status,
        ParticipantStatus.left,
      );
      final leftReadback = await _caller.query.getCall(
        RtcGetCallQuery(callId: leaveSession.id),
      );
      expect(leftReadback.toWire(), left.first.toWire());

      final activeSession = await _connectCall('invite', maxParticipants: 3);
      final inviteBefore = await _caller.query.getCall(
        RtcGetCallQuery(callId: activeSession.id),
      );
      await _expectRtcFailure(
        telemetry.observe(
          AppCloudOperationIds.rtcCallSessionInviteToCall,
          () => _bystander.withRtcIdempotencyKey(
            'invite-bola-${activeSession.id}',
            () => _bystander.participants.inviteToCall(
              RtcInviteToCallCommand(
                callId: activeSession.id,
                inviteeIds: <String>[_intruder.personaId],
              ),
            ),
          ),
        ),
        operationId: AppCloudOperationIds.rtcCallSessionInviteToCall,
        code: 'RTC.USER.not_participant',
        statusCode: 403,
      );
      expect(
        (await _caller.query.getCall(
          RtcGetCallQuery(callId: activeSession.id),
        )).toWire(),
        inviteBefore.toWire(),
      );
      final inviteKey = 'invite-${activeSession.id}';
      final invited = await _replaySessionCommand(
        telemetry,
        operationId: AppCloudOperationIds.rtcCallSessionInviteToCall,
        actor: _caller,
        idempotencyKey: inviteKey,
        command: () => _caller.participants.inviteToCall(
          RtcInviteToCallCommand(
            callId: activeSession.id,
            inviteeIds: <String>[_intruder.personaId],
          ),
        ),
      );
      expect(invited.first.status, CallStatus.inCall);
      expect(invited.first.participantCount, 3);
      final invitedParticipant = _participant(
        invited.first,
        _intruder.personaId,
      );
      expect(invitedParticipant.status, ParticipantStatus.invited);
      expect(invitedParticipant.inviteStatus, CallInviteStatus.pending);

      await _expectRtcFailure(
        telemetry.observe(
          AppCloudOperationIds.rtcCallSessionInviteToCall,
          () => _caller.withRtcIdempotencyKey(
            inviteKey,
            () => _caller.participants.inviteToCall(
              RtcInviteToCallCommand(
                callId: activeSession.id,
                inviteeIds: <String>[_bystander.personaId],
              ),
            ),
          ),
        ),
        operationId: AppCloudOperationIds.rtcCallSessionInviteToCall,
        code: 'RTC.USER.idempotency_conflict',
        statusCode: 409,
      );
      await _expectRtcFailure(
        telemetry.observe(
          AppCloudOperationIds.rtcCallSessionInviteToCall,
          () => _caller.withRtcIdempotencyKey(
            'invite-full-${activeSession.id}',
            () => _caller.participants.inviteToCall(
              RtcInviteToCallCommand(
                callId: activeSession.id,
                inviteeIds: <String>[_bystander.personaId],
              ),
            ),
          ),
        ),
        operationId: AppCloudOperationIds.rtcCallSessionInviteToCall,
        code: 'RTC.USER.call_full',
        statusCode: 409,
      );
      final invitedReadback = await _caller.query.getCall(
        RtcGetCallQuery(callId: activeSession.id),
      );
      expect(invitedReadback.toWire(), invited.first.toWire());
      expect(
        (invitedReadback.participants ?? const <CallParticipant>[]).any(
          (participant) => participant.userId == _bystander.personaId,
        ),
        isFalse,
      );

      final cameraBefore = _participant(invitedReadback, _caller.personaId);
      expect(cameraBefore.isCameraOn, isFalse);
      await _expectRtcFailure(
        telemetry.observe(
          AppCloudOperationIds.rtcCallSessionToggleCamera,
          () => _bystander.withRtcIdempotencyKey(
            'camera-bola-${activeSession.id}',
            () => _bystander.media.toggleCamera(
              RtcToggleCameraCommand(callId: activeSession.id, cameraOn: true),
            ),
          ),
        ),
        operationId: AppCloudOperationIds.rtcCallSessionToggleCamera,
        code: 'RTC.USER.not_participant',
        statusCode: 403,
      );
      final cameraKey = 'camera-${activeSession.id}';
      final camera = await _replaySessionCommand(
        telemetry,
        operationId: AppCloudOperationIds.rtcCallSessionToggleCamera,
        actor: _caller,
        idempotencyKey: cameraKey,
        command: () => _caller.media.toggleCamera(
          RtcToggleCameraCommand(callId: activeSession.id, cameraOn: true),
        ),
      );
      expect(_participant(camera.first, _caller.personaId).isCameraOn, isTrue);
      await _expectRtcFailure(
        telemetry.observe(
          AppCloudOperationIds.rtcCallSessionToggleCamera,
          () => _caller.withRtcIdempotencyKey(
            cameraKey,
            () => _caller.media.toggleCamera(
              RtcToggleCameraCommand(callId: activeSession.id, cameraOn: false),
            ),
          ),
        ),
        operationId: AppCloudOperationIds.rtcCallSessionToggleCamera,
        code: 'RTC.USER.idempotency_conflict',
        statusCode: 409,
      );
      final cameraReadback = await _callee.query.getCall(
        RtcGetCallQuery(callId: activeSession.id),
      );
      expect(
        _participant(cameraReadback, _caller.personaId).isCameraOn,
        isTrue,
      );
      expect(cameraReadback.toWire(), camera.first.toWire());

      await _caller.withRtcIdempotencyKey(
        'cleanup-caller-${activeSession.id}',
        () => _caller.lifecycle.hangupCall(
          RtcCallIdCommand(callId: activeSession.id),
        ),
      );
      final cleaned = await _callee.withRtcIdempotencyKey(
        'cleanup-callee-${activeSession.id}',
        () => _callee.lifecycle.hangupCall(
          RtcCallIdCommand(callId: activeSession.id),
        ),
      );
      expect(cleaned.status, CallStatus.ended);

      await telemetry.expectExactEvidence(<_GammaRtcActor>[
        _caller,
        _callee,
        _bystander,
      ]);
    },
  );
}

const _remainingRtcOperationIds = <String>{
  AppCloudOperationIds.rtcCallSessionRejectCall,
  AppCloudOperationIds.rtcCallSessionCancelCall,
  AppCloudOperationIds.rtcCallSessionLeaveCall,
  AppCloudOperationIds.rtcCallSessionInviteToCall,
  AppCloudOperationIds.rtcCallSessionToggleCamera,
};

Future<CallSession> _initiateCall(
  String label, {
  required int maxParticipants,
}) async {
  final initiated = await _caller.withRtcIdempotencyKey(
    'initiate-$label',
    () => _caller.lifecycle.initiateCall(
      RtcInitiateCallCommand(
        callType: CallType.video,
        inviteeIds: <String>[_callee.personaId],
        maxParticipants: maxParticipants,
      ),
    ),
  );
  expect(initiated.session.id, isNotEmpty);
  expect(initiated.session.status, CallStatus.ringing);
  expect(initiated.session.initiatorId, _caller.personaId);
  expect(initiated.mediaAccess.accessToken, isNotEmpty);
  addTearDown(() => _cleanupCall(label, initiated.session.id));
  return initiated.session;
}

Future<CallSession> _connectCall(
  String label, {
  required int maxParticipants,
}) async {
  final initiated = await _initiateCall(
    label,
    maxParticipants: maxParticipants,
  );
  final callId = initiated.id;
  final answered = await _callee.withRtcIdempotencyKey(
    'answer-$label',
    () => _callee.lifecycle.answerCall(RtcCallIdCommand(callId: callId)),
  );
  expect(answered.session.status, CallStatus.connecting);
  expect(answered.mediaAccess.accessToken, isNotEmpty);
  final callerJoined = await _caller.withRtcIdempotencyKey(
    'join-caller-$label',
    () => _caller.participants.joinCall(RtcCallIdCommand(callId: callId)),
  );
  final calleeJoined = await _callee.withRtcIdempotencyKey(
    'join-callee-$label',
    () => _callee.participants.joinCall(RtcCallIdCommand(callId: callId)),
  );
  expect(callerJoined.mediaAccess.accessToken, isNotEmpty);
  expect(calleeJoined.mediaAccess.accessToken, isNotEmpty);
  await _caller.participants.reportMediaConnected(
    RtcCallIdCommand(callId: callId),
  );
  final connected = await _callee.participants.reportMediaConnected(
    RtcCallIdCommand(callId: callId),
  );
  expect(connected.status, CallStatus.inCall);
  expect(connected.startedAt, isNotNull);
  return _caller.query.getCall(RtcGetCallQuery(callId: callId));
}

Future<({CallSession first, CallSession replay})> _replaySessionCommand(
  _RtcTelemetryLedger telemetry, {
  required String operationId,
  required _GammaRtcActor actor,
  required String idempotencyKey,
  required Future<CallSession> Function() command,
}) async {
  final first = await telemetry.observe(
    operationId,
    () => actor.withRtcIdempotencyKey(idempotencyKey, command),
  );
  final replay = await telemetry.observe(
    operationId,
    () => actor.withRtcIdempotencyKey(idempotencyKey, command),
  );
  expect(replay.toWire(), first.toWire());
  return (first: first, replay: replay);
}

Future<void> _expectRtcFailure(
  Future<Object?> call, {
  required String operationId,
  required String code,
  required int statusCode,
}) async {
  await expectLater(
    call,
    throwsA(
      isA<CloudException>()
          .having(
            (error) => error.runtimeFailure.code,
            'runtimeFailure.code',
            code,
          )
          .having((error) => error.statusCode, 'statusCode', statusCode)
          .having(
            (error) => error.sourceOperationId,
            'sourceOperationId',
            operationId,
          )
          .having((error) => error.requestId, 'requestId', isNotEmpty)
          .having((error) => error.traceId, 'traceId', isNotEmpty),
    ),
  );
}

CallParticipant _participant(CallSession session, String personaId) =>
    (session.participants ?? const <CallParticipant>[]).singleWhere(
      (participant) => participant.userId == personaId,
    );

Future<void> _cleanupCall(String label, String callId) async {
  try {
    var current = await _caller.query.getCall(RtcGetCallQuery(callId: callId));
    if (current.status == CallStatus.ended) {
      return;
    }
    if (current.status == CallStatus.initiated ||
        current.status == CallStatus.ringing) {
      await _caller.withRtcIdempotencyKey(
        'teardown-cancel-$label-$callId',
        () => _caller.lifecycle.cancelCall(RtcCallIdCommand(callId: callId)),
      );
      return;
    }
    await _caller.withRtcIdempotencyKey(
      'teardown-hangup-caller-$label-$callId',
      () => _caller.lifecycle.hangupCall(RtcCallIdCommand(callId: callId)),
    );
    current = await _callee.query.getCall(RtcGetCallQuery(callId: callId));
    if (current.status != CallStatus.ended) {
      await _callee.withRtcIdempotencyKey(
        'teardown-hangup-callee-$label-$callId',
        () => _callee.lifecycle.hangupCall(RtcCallIdCommand(callId: callId)),
      );
    }
  } on CloudException catch (error) {
    if (error.runtimeFailure.code != 'RTC.USER.call_not_found') {
      rethrow;
    }
  }
}

final class _RtcTelemetryLedger {
  final Map<String, int> _success = <String, int>{};
  final Map<String, int> _failure = <String, int>{};

  Future<T> observe<T>(
    String operationId,
    Future<T> Function() operation,
  ) async {
    try {
      final value = await operation();
      _success.update(operationId, (count) => count + 1, ifAbsent: () => 1);
      return value;
    } catch (_) {
      _failure.update(operationId, (count) => count + 1, ifAbsent: () => 1);
      rethrow;
    }
  }

  Future<void> expectExactEvidence(List<_GammaRtcActor> actors) async {
    final events = <ProductionCloudOperationTelemetryEvent>[];
    for (final actor in actors) {
      events.addAll(await actor.telemetry.waitForEvents(minimumCount: 1));
    }
    final operationEvents = events
        .where(
          (event) =>
              _remainingRtcOperationIds.contains(event.canonicalOperationId),
        )
        .toList(growable: false);
    expect(
      operationEvents.map((event) => event.canonicalOperationId).toSet(),
      _remainingRtcOperationIds,
    );
    for (final operationId in _remainingRtcOperationIds) {
      final current = operationEvents
          .where((event) => event.canonicalOperationId == operationId)
          .toList(growable: false);
      final succeeded = current
          .where((event) => event.succeeded)
          .toList(growable: false);
      final failed = current
          .where((event) => !event.succeeded)
          .toList(growable: false);
      expect(succeeded, hasLength(_success[operationId] ?? 0));
      expect(failed, hasLength(_failure[operationId] ?? 0));
      expect(
        current.every(
          (event) => event.requestId.isNotEmpty && event.traceId.isNotEmpty,
        ),
        isTrue,
      );
      expect(
        succeeded.every(
          (event) =>
              event.statusCode != null &&
              event.statusCode! >= 200 &&
              event.statusCode! < 300,
        ),
        isTrue,
      );
      expect(
        failed.every(
          (event) => event.statusCode != null && event.statusCode! >= 400,
        ),
        isTrue,
      );
    }
  }
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
    required this.telemetry,
  }) : _deviceActorId = 'rtc-api-contract-$runId-$label-device' {
    _httpClient = CloudHttpClient(authTokenProvider: _tokenProvider);
    _client = buildGeneratedCloudOperationClient(
      httpClient: _httpClient,
      clientContextProvider: _GammaRtcClientContext(_deviceActorId),
      telemetrySink: telemetry.sink,
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
  final ProductionCloudOperationTelemetryEvidence telemetry;

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
  String? _activeRtcIdempotencyKey;

  String get accountId => _requireSession().ownerId;

  String get personaId => _requireSession().activePersona!.personaId;

  static Future<_GammaRtcActor> signIn({
    required String label,
    required String runId,
    required Uri gatewayBaseUri,
  }) async {
    final deviceActorId = 'rtc-api-contract-$runId-$label-device';
    final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
      clientContextProvider: _GammaRtcClientContext(deviceActorId),
    );
    final actor = _GammaRtcActor._(
      label: label,
      runId: runId,
      gatewayBaseUri: gatewayBaseUri,
      telemetry: telemetry,
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
      await telemetry.dispose();
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

  Future<RelationshipCapabilityView> getRelationshipCapability(
    String targetPersonaId,
  ) => relationshipCapability.getRelationshipCapability(
    GetRelationshipCapabilityQuery(targetPersonaId: targetPersonaId),
  );

  Future<T> withRtcIdempotencyKey<T>(
    String idempotencyKey,
    Future<T> Function() operation,
  ) async {
    final normalized = idempotencyKey.trim();
    if (normalized.isEmpty) {
      throw ArgumentError.value(idempotencyKey, 'idempotencyKey');
    }
    if (_activeRtcIdempotencyKey != null) {
      throw StateError(
        'RTC API contract commands must be sequential per actor',
      );
    }
    _activeRtcIdempotencyKey = normalized;
    try {
      return await operation();
    } finally {
      _activeRtcIdempotencyKey = null;
    }
  }

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
    await telemetry.dispose();
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
    idempotencySuffix: command ? _activeRtcIdempotencyKey : null,
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
