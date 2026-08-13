import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'rtc_contract_test_builders.dart';

/// CallSession 对象级 typed double（仅测试树可达）。
///
/// 数据只来自构建期 immutable fixture bundle；production 依赖图不可达本类。
final class CallSessionTypedDouble
    implements
        CallLifecycleCommandWriter,
        CallParticipantCommandWriter,
        CallMediaControlWriter,
        CallScreenShareWriter,
        CallQuery {
  CallSessionTypedDouble() {
    _seed();
  }

  static final DateTime _seedTime = DateTime.utc(2026, 7, 19);
  final Map<String, CallSession> _sessions = <String, CallSession>{};

  @override
  Future<RtcInitiateCallResult> initiateCall(
    RtcInitiateCallCommand command,
  ) async {
    final callId = 'fixture_call_${_sessions.length + 1}';
    final participants = <CallParticipant>[
      buildCallParticipantContract(
        userId: 'fixture_user_current',
        role: ParticipantRole.initiator,
        status: ParticipantStatus.connecting,
        isMuted: false,
        isCameraOn: false,
      ),
      ...command.inviteeIds.map(
        (id) => buildCallParticipantContract(
          userId: id,
          role: ParticipantRole.invitee,
          status: ParticipantStatus.ringing,
          isMuted: false,
          isCameraOn: false,
        ),
      ),
    ];
    final session = buildCallSessionContract(
      id: callId,
      callType: command.callType,
      status: CallStatus.ringing,
      initiatorId: 'fixture_user_current',
      conversationId: command.conversationId,
      circleId: command.circleId,
      roomId: 'rtc-room-$callId',
      maxParticipants: command.maxParticipants,
      participantCount: participants.length,
      participants: participants,
      isScreenSharing: false,
      createdAt: _seedTime,
      updatedAt: _seedTime,
    );
    _sessions[callId] = session;
    return RtcInitiateCallResult(
      session: session,
      mediaAccess: RtcMediaSessionAccess(
        accessToken: 'alpha-media-access-$callId',
      ),
    );
  }

  @override
  Future<RtcAnswerCallResult> answerCall(RtcCallIdCommand command) async {
    final session = _updateStatus(command.callId, CallStatus.inCall);
    return RtcAnswerCallResult(
      session: session,
      mediaAccess: RtcMediaSessionAccess(
        accessToken: 'alpha-media-access-${command.callId}',
      ),
    );
  }

  @override
  Future<CallSession> rejectCall(RtcCallIdCommand command) async =>
      _end(command.callId, EndReason.rejected);

  @override
  Future<CallSession> cancelCall(RtcCallIdCommand command) async =>
      _end(command.callId, EndReason.cancelled);

  @override
  Future<CallSession> hangupCall(RtcCallIdCommand command) async =>
      _end(command.callId, EndReason.normal);

  @override
  Future<RtcJoinCredentials> joinCall(RtcCallIdCommand command) async {
    final session = _updateStatus(command.callId, CallStatus.inCall);
    return RtcJoinCredentials(
      session: session,
      mediaAccess: RtcMediaSessionAccess(
        accessToken: 'alpha-media-access-${command.callId}',
      ),
    );
  }

  @override
  Future<CallSession> leaveCall(RtcCallIdCommand command) async =>
      _end(command.callId, EndReason.lastLeave);

  @override
  Future<CallSession> inviteToCall(RtcInviteToCallCommand command) async {
    final current = _require(command.callId);
    final existing = _participants(current).map((item) => item.userId).toSet();
    final additions = command.inviteeIds
        .where((id) => !existing.contains(id))
        .map(
          (id) => buildCallParticipantContract(
            userId: id,
            role: ParticipantRole.invitee,
            status: ParticipantStatus.ringing,
            isMuted: false,
            isCameraOn: false,
          ),
        );
    final participants = <CallParticipant>[
      ..._participants(current),
      ...additions,
    ];
    return _save(
      _copySession(
        current,
        participants: participants,
        participantCount: participants.length,
        updatedAt: _seedTime,
      ),
    );
  }

  @override
  Future<CallSession> reportMediaConnected(RtcCallIdCommand command) async {
    final current = _require(command.callId);
    if (current.status == CallStatus.ended) {
      return current;
    }
    final participants = _participants(current)
        .map(
          (participant) => participant.userId == 'fixture_user_current'
              ? _copyParticipant(
                  participant,
                  status: ParticipantStatus.connected,
                )
              : participant,
        )
        .toList(growable: false);
    final connectedCount = participants
        .where(
          (participant) => participant.status == ParticipantStatus.connected,
        )
        .length;
    final becomesInCall =
        connectedCount >= 2 && current.status != CallStatus.inCall;
    return _save(
      _copySession(
        current,
        participants: participants,
        status: becomesInCall ? CallStatus.inCall : current.status,
        startedAt: becomesInCall ? _seedTime : current.startedAt,
        updatedAt: _seedTime,
      ),
    );
  }

  @override
  Future<CallSession> toggleMute(RtcToggleMuteCommand command) async =>
      _updateParticipant(
        command.callId,
        (participant) => participant.userId == 'fixture_user_current'
            ? _copyParticipant(participant, isMuted: command.muted)
            : participant,
      );

  @override
  Future<CallSession> toggleCamera(RtcToggleCameraCommand command) async =>
      _updateParticipant(
        command.callId,
        (participant) => participant.userId == 'fixture_user_current'
            ? _copyParticipant(participant, isCameraOn: command.cameraOn)
            : participant,
      );

  @override
  Future<CallSession> startScreenShare(RtcCallIdCommand command) async {
    final current = _require(command.callId);
    return _save(
      _copySession(
        current,
        isScreenSharing: true,
        screenShareUserId: () => 'fixture_user_current',
        updatedAt: _seedTime,
      ),
    );
  }

  @override
  Future<CallSession> stopScreenShare(RtcCallIdCommand command) async {
    final current = _require(command.callId);
    return _save(
      _copySession(
        current,
        isScreenSharing: false,
        screenShareUserId: () => null,
        updatedAt: _seedTime,
      ),
    );
  }

  @override
  Future<CallSession> getCall(RtcGetCallQuery query) async =>
      _require(query.callId);

  @override
  Future<RtcCallHistoryPage> listCalls(RtcListCallsQuery query) async {
    final items = _sessions.values.take(query.limit).toList(growable: false);
    return RtcCallHistoryPage(items: items);
  }

  void _seed() {
    for (final seed in _initialCallSeeds) {
      final participants = seed.participantUserIds
          .map(
            (id) => buildCallParticipantContract(
              userId: id,
              role: id == seed.callerUserId
                  ? ParticipantRole.initiator
                  : ParticipantRole.invitee,
              status: seed.status == CallStatus.ringing
                  ? ParticipantStatus.ringing
                  : ParticipantStatus.invited,
              isMuted: false,
              isCameraOn: seed.callType == CallType.video,
            ),
          )
          .toList(growable: false);
      _sessions[seed.callId] = buildCallSessionContract(
        id: seed.callId,
        callType: seed.callType,
        status: seed.status,
        initiatorId: seed.callerUserId,
        roomId: 'rtc-room-${seed.callId}',
        maxParticipants: 32,
        participantCount: participants.length,
        participants: participants,
        isScreenSharing: false,
        createdAt: _seedTime,
        updatedAt: _seedTime,
      );
    }
  }

  CallSession _require(String callId) {
    final session = _sessions[callId];
    if (session == null) {
      throw StateError('alpha rtc fixture call not found: $callId');
    }
    return session;
  }

  CallSession _save(CallSession session) {
    _sessions[session.id] = session;
    return session;
  }

  CallSession _updateStatus(String callId, CallStatus status) {
    final current = _require(callId);
    return _save(_copySession(current, status: status, updatedAt: _seedTime));
  }

  CallSession _end(String callId, EndReason reason) {
    final current = _require(callId);
    return _save(
      _copySession(
        current,
        status: CallStatus.ended,
        endReason: reason,
        endedAt: _seedTime,
        updatedAt: _seedTime,
      ),
    );
  }

  CallSession _updateParticipant(
    String callId,
    CallParticipant Function(CallParticipant participant) transform,
  ) {
    final current = _require(callId);
    return _save(
      _copySession(
        current,
        participants: _participants(
          current,
        ).map(transform).toList(growable: false),
        updatedAt: _seedTime,
      ),
    );
  }
}

typedef _InitialCallSeed = ({
  String callId,
  CallType callType,
  CallStatus status,
  String callerUserId,
  List<String> participantUserIds,
});

const List<_InitialCallSeed> _initialCallSeeds = <_InitialCallSeed>[
  (
    callId: '11111111-1111-4111-8111-111111111111',
    callType: CallType.audio,
    status: CallStatus.ringing,
    callerUserId: 'fixture_user_friend',
    participantUserIds: <String>['fixture_user_current', 'fixture_user_friend'],
  ),
  (
    callId: '22222222-2222-4222-8222-222222222222',
    callType: CallType.video,
    status: CallStatus.initiated,
    callerUserId: 'fixture_user_current',
    participantUserIds: <String>[
      'fixture_user_current',
      'fixture_user_weekend_1',
    ],
  ),
];

List<CallParticipant> _participants(CallSession session) =>
    session.participants ?? <CallParticipant>[];

CallParticipant _copyParticipant(
  CallParticipant current, {
  ParticipantStatus? status,
  bool? isMuted,
  bool? isCameraOn,
}) {
  return buildCallParticipantContract(
    userId: current.userId,
    role: current.role,
    status: status ?? current.status,
    isMuted: isMuted ?? current.isMuted,
    isCameraOn: isCameraOn ?? current.isCameraOn,
    joinedAt: current.joinedAt,
    leftAt: current.leftAt,
    inviteStatus: current.inviteStatus,
    invitedBy: current.invitedBy,
  );
}

CallSession _copySession(
  CallSession current, {
  CallStatus? status,
  int? participantCount,
  List<CallParticipant>? participants,
  bool? isScreenSharing,
  String? Function()? screenShareUserId,
  EndReason? endReason,
  DateTime? startedAt,
  DateTime? endedAt,
  DateTime? updatedAt,
}) {
  return buildCallSessionContract(
    id: current.id,
    callType: current.callType,
    status: status ?? current.status,
    initiatorId: current.initiatorId,
    initiatorRingtoneId: current.initiatorRingtoneId,
    conversationId: current.conversationId,
    circleId: current.circleId,
    roomId: current.roomId,
    maxParticipants: current.maxParticipants,
    participantCount: participantCount ?? current.participantCount,
    participants: participants ?? current.participants,
    isScreenSharing: isScreenSharing ?? current.isScreenSharing,
    screenShareUserId: screenShareUserId == null
        ? current.screenShareUserId
        : screenShareUserId(),
    endReason: endReason ?? current.endReason,
    durationMs: current.durationMs,
    startedAt: startedAt ?? current.startedAt,
    endedAt: endedAt ?? current.endedAt,
    createdAt: current.createdAt,
    updatedAt: updatedAt ?? current.updatedAt,
  );
}
