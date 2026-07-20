import 'dart:convert';

import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../generated/alpha_fixture_bundle.g.dart';

/// Alpha-only CallSession Facet 组合。
///
/// 数据只来自构建期 immutable fixture bundle；production 依赖图不可达本类。
final class AlphaRtcCallSessionFacets
    implements
        CallLifecycleCommandWriter,
        CallParticipantCommandWriter,
        CallMediaControlWriter,
        CallScreenShareWriter,
        CallQuery {
  AlphaRtcCallSessionFacets() {
    _seed();
  }

  static final DateTime _seedTime = DateTime.utc(2026, 7, 19);
  final Map<String, CallSessionDto> _sessions = <String, CallSessionDto>{};

  @override
  Future<RtcInitiateCallResultDto> initiateCall(
    RtcInitiateCallCommand command,
  ) async {
    final callId = 'alpha_call_${_sessions.length + 1}';
    final participants = <CallParticipantDto>[
      const CallParticipantDto(
        userId: 'fixture_user_current',
        role: 'initiator',
        status: 'connecting',
      ),
      ...command.inviteeIds.map(
        (id) =>
            CallParticipantDto(userId: id, role: 'invitee', status: 'ringing'),
      ),
    ];
    final session = CallSessionDto(
      callId: callId,
      callType: command.callType,
      status: 'ringing',
      initiatorId: 'fixture_user_current',
      conversationId: command.conversationId,
      circleId: command.circleId,
      roomId: 'rtc-room-$callId',
      maxParticipants: command.maxParticipants,
      participantCount: participants.length,
      participants: participants,
      createdAt: _seedTime,
      updatedAt: _seedTime,
    );
    _sessions[callId] = session;
    return RtcInitiateCallResultDto(
      session: session,
      token: 'alpha-livekit-token-$callId',
      livekitUrl: 'ws://127.0.0.1:19280',
    );
  }

  @override
  Future<RtcAnswerCallResultDto> answerCall(RtcCallIdCommand command) async {
    final session = _updateStatus(command.callId, 'in_call');
    return RtcAnswerCallResultDto(
      session: session,
      token: 'alpha-livekit-token-${command.callId}',
      roomId: session.roomId,
      livekitUrl: 'ws://127.0.0.1:19280',
    );
  }

  @override
  Future<CallSessionDto> rejectCall(RtcCallIdCommand command) async =>
      _end(command.callId, 'rejected');

  @override
  Future<CallSessionDto> cancelCall(RtcCallIdCommand command) async =>
      _end(command.callId, 'cancelled');

  @override
  Future<CallSessionDto> hangupCall(RtcCallIdCommand command) async =>
      _end(command.callId, 'normal');

  @override
  Future<RtcJoinCredentialsDto> joinCall(RtcCallIdCommand command) async {
    final session = _updateStatus(command.callId, 'in_call');
    return RtcJoinCredentialsDto(
      session: session,
      token: 'alpha-livekit-token-${command.callId}',
      livekitUrl: 'ws://127.0.0.1:19280',
    );
  }

  @override
  Future<CallSessionDto> leaveCall(RtcCallIdCommand command) async =>
      _end(command.callId, 'last_leave');

  @override
  Future<CallSessionDto> inviteToCall(RtcInviteToCallCommand command) async {
    final current = _require(command.callId);
    final existing = current.participants.map((item) => item.userId).toSet();
    final additions = command.inviteeIds
        .where((id) => !existing.contains(id))
        .map(
          (id) => CallParticipantDto(
            userId: id,
            role: 'invitee',
            status: 'ringing',
          ),
        );
    final participants = <CallParticipantDto>[
      ...current.participants,
      ...additions,
    ];
    return _save(
      current.copyWith(
        participants: participants,
        participantCount: participants.length,
        updatedAt: _seedTime,
      ),
    );
  }

  @override
  Future<CallSessionDto> reportMediaConnected(RtcCallIdCommand command) async {
    final current = _require(command.callId);
    if (current.status == 'ended') {
      return current;
    }
    final participants = current.participants
        .map(
          (participant) => participant.userId == 'fixture_user_current'
              ? participant.copyWith(status: 'connected')
              : participant,
        )
        .toList(growable: false);
    final connectedCount = participants
        .where((participant) => participant.status == 'connected')
        .length;
    final becomesInCall = connectedCount >= 2 && current.status != 'in_call';
    return _save(
      current.copyWith(
        participants: participants,
        status: becomesInCall ? 'in_call' : current.status,
        startedAt: becomesInCall ? _seedTime : current.startedAt,
        updatedAt: _seedTime,
      ),
    );
  }

  @override
  Future<CallSessionDto> toggleMute(RtcToggleMuteCommand command) async =>
      _updateParticipant(
        command.callId,
        (participant) => participant.userId == 'fixture_user_current'
            ? participant.copyWith(isMuted: command.muted)
            : participant,
      );

  @override
  Future<CallSessionDto> toggleCamera(RtcToggleCameraCommand command) async =>
      _updateParticipant(
        command.callId,
        (participant) => participant.userId == 'fixture_user_current'
            ? participant.copyWith(isCameraOn: command.cameraOn)
            : participant,
      );

  @override
  Future<CallSessionDto> startScreenShare(RtcCallIdCommand command) async {
    final current = _require(command.callId);
    return _save(
      current.copyWith(
        isScreenSharing: true,
        screenShareUserId: 'fixture_user_current',
        updatedAt: _seedTime,
      ),
    );
  }

  @override
  Future<CallSessionDto> stopScreenShare(RtcCallIdCommand command) async {
    final current = _require(command.callId);
    return _save(
      CallSessionDto(
        callId: current.callId,
        callType: current.callType,
        status: current.status,
        initiatorId: current.initiatorId,
        initiatorRingtoneId: current.initiatorRingtoneId,
        conversationId: current.conversationId,
        circleId: current.circleId,
        roomId: current.roomId,
        maxParticipants: current.maxParticipants,
        participantCount: current.participantCount,
        participants: current.participants,
        isScreenSharing: false,
        endReason: current.endReason,
        durationMs: current.durationMs,
        startedAt: current.startedAt,
        endedAt: current.endedAt,
        createdAt: current.createdAt,
        updatedAt: _seedTime,
      ),
    );
  }

  @override
  Future<CallSessionDto> getCall(RtcGetCallQuery query) async =>
      _require(query.callId);

  @override
  Future<RtcCallHistoryPage> listCalls(RtcListCallsQuery query) async {
    final items = _sessions.values.take(query.limit).toList(growable: false);
    return RtcCallHistoryPage(items: items);
  }

  void _seed() {
    final asset = alphaFixtureBundle.assets['rtc'];
    if (asset == null) return;
    final root = jsonDecode(asset.sourceJson);
    if (root is! Map<Object?, Object?>) return;
    final seedSets = root['seedSets'];
    if (seedSets is! Map<Object?, Object?>) return;
    final core = seedSets['rtc_core'];
    if (core is! Map<Object?, Object?>) return;
    final sessions = core['sessions'];
    if (sessions is! List<Object?>) return;
    for (final raw in sessions) {
      if (raw is! Map<Object?, Object?>) continue;
      final callId = raw['sessionId']?.toString().trim() ?? '';
      final callerId = raw['callerUserId']?.toString().trim() ?? '';
      final participantIds = raw['participantUserIds'];
      if (callId.isEmpty || callerId.isEmpty || participantIds is! List) {
        continue;
      }
      final callType = raw['type'] == 'video' ? 'video' : 'audio';
      final state = raw['state'] == 'incoming' ? 'ringing' : 'initiated';
      final participants = participantIds
          .map((value) => value.toString().trim())
          .where((id) => id.isNotEmpty)
          .map(
            (id) => CallParticipantDto(
              userId: id,
              role: id == callerId ? 'initiator' : 'invitee',
              status: state == 'ringing' ? 'ringing' : 'invited',
              isCameraOn: callType == 'video',
            ),
          )
          .toList(growable: false);
      _sessions[callId] = CallSessionDto(
        callId: callId,
        callType: callType,
        status: state,
        initiatorId: callerId,
        roomId: 'rtc-room-$callId',
        maxParticipants: 32,
        participantCount: participants.length,
        participants: participants,
        createdAt: _seedTime,
        updatedAt: _seedTime,
      );
    }
  }

  CallSessionDto _require(String callId) {
    final session = _sessions[callId];
    if (session == null) {
      throw StateError('alpha rtc fixture call not found: $callId');
    }
    return session;
  }

  CallSessionDto _save(CallSessionDto session) {
    _sessions[session.callId] = session;
    return session;
  }

  CallSessionDto _updateStatus(String callId, String status) {
    final current = _require(callId);
    return _save(current.copyWith(status: status, updatedAt: _seedTime));
  }

  CallSessionDto _end(String callId, String reason) {
    final current = _require(callId);
    return _save(
      current.copyWith(
        status: 'ended',
        endReason: reason,
        endedAt: _seedTime,
        updatedAt: _seedTime,
      ),
    );
  }

  CallSessionDto _updateParticipant(
    String callId,
    CallParticipantDto Function(CallParticipantDto participant) transform,
  ) {
    final current = _require(callId);
    return _save(
      current.copyWith(
        participants: current.participants
            .map(transform)
            .toList(growable: false),
        updatedAt: _seedTime,
      ),
    );
  }
}
