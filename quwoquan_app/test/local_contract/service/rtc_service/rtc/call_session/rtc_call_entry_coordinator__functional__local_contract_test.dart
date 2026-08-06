import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/public/rtc_call_entry_coordinator.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/service/rtc_service/rtc/call_session/rtc_contract_test_builders.dart';

void main() {
  group('RtcCallEntryCoordinator - 1v1 关系能力合同', () {
    test('mutual 且对应能力位开启时创建 canonical direct command', () async {
      final writer = _RecordingCallLifecycleWriter();
      final intent = RtcCallEntryIntent.direct(
        mediaType: RtcCallEntryMediaType.video,
        targetUserId: 'target-persona',
        capability: _capability(
          relationState: 'mutual',
          canStartVoiceCall: true,
          canStartVideoCall: true,
        ),
      );

      expect(intent.availability.isAvailable, isTrue);
      await RtcCallEntryCoordinator(lifecycleWriter: writer).initiate(intent);

      final command = writer.initiateCommands.single;
      expect(command.callType, CallType.video);
      expect(command.inviteeIds, const <String>['target-persona']);
      expect(command.conversationId, isNull);
      expect(command.circleId, isNull);
    });

    test('单向关注即使错误下发能力位也按 notMutual fail-closed', () async {
      final writer = _RecordingCallLifecycleWriter();
      final intent = RtcCallEntryIntent.direct(
        mediaType: RtcCallEntryMediaType.audio,
        targetUserId: 'target-persona',
        capability: _capability(
          relationState: 'following',
          canStartVoiceCall: true,
          canStartVideoCall: true,
        ),
      );

      expect(
        intent.availability.reason,
        RtcCallEntryUnavailableReason.notMutual,
      );
      await expectLater(
        RtcCallEntryCoordinator(lifecycleWriter: writer).initiate(intent),
        throwsA(
          isA<RtcCallEntryRejected>().having(
            (error) => error.reason,
            'reason',
            RtcCallEntryUnavailableReason.notMutual,
          ),
        ),
      );
      expect(writer.initiateCommands, isEmpty);
    });

    test('blocked 即使 mutual 且能力位为 true 也隐藏并拒绝', () async {
      final writer = _RecordingCallLifecycleWriter();
      final intent = RtcCallEntryIntent.direct(
        mediaType: RtcCallEntryMediaType.video,
        targetUserId: 'target-persona',
        capability: _capability(
          relationState: 'mutual',
          canStartVoiceCall: true,
          canStartVideoCall: true,
          isBlocked: true,
        ),
      );

      expect(intent.availability.reason, RtcCallEntryUnavailableReason.blocked);
      await expectLater(
        RtcCallEntryCoordinator(lifecycleWriter: writer).initiate(intent),
        throwsA(isA<RtcCallEntryRejected>()),
      );
      expect(writer.initiateCommands, isEmpty);
    });

    test('语音与视频分别消费对应 capability', () {
      final capability = _capability(
        relationState: 'mutual',
        canStartVoiceCall: true,
        canStartVideoCall: false,
      );

      expect(
        RtcCallEntryIntent.direct(
          mediaType: RtcCallEntryMediaType.audio,
          targetUserId: 'target-persona',
          capability: capability,
        ).availability.isAvailable,
        isTrue,
      );
      expect(
        RtcCallEntryIntent.direct(
          mediaType: RtcCallEntryMediaType.video,
          targetUserId: 'target-persona',
          capability: capability,
        ).availability.reason,
        RtcCallEntryUnavailableReason.capabilityDenied,
      );
    });
  });

  group('RtcCallEntryCoordinator - 多人上下文与选人合同', () {
    test('群成员 <=8 默认全选，>8 默认空选', () {
      expect(
        RtcCallEntryIntent.conversation(
          mediaType: RtcCallEntryMediaType.audio,
          conversationId: 'conversation-small',
          participantCount: 8,
        ).defaultSelectAll,
        isTrue,
      );
      expect(
        RtcCallEntryIntent.conversation(
          mediaType: RtcCallEntryMediaType.audio,
          conversationId: 'conversation-large',
          participantCount: 9,
        ).defaultSelectAll,
        isFalse,
      );
    });

    test('群入口保留 conversation context 并去重选中参与者', () async {
      final writer = _RecordingCallLifecycleWriter();
      final intent = RtcCallEntryIntent.conversation(
        mediaType: RtcCallEntryMediaType.audio,
        conversationId: 'conversation-group',
        participantCount: 6,
      );

      await RtcCallEntryCoordinator(lifecycleWriter: writer).initiate(
        intent,
        selectedInviteeIds: const <String>['member-1', 'member-1', 'member-2'],
      );

      final command = writer.initiateCommands.single;
      expect(command.inviteeIds, const <String>['member-1', 'member-2']);
      expect(command.conversationId, 'conversation-group');
      expect(command.circleId, isNull);
    });

    test('初始多人通话最多选择 maxParticipants - 1 个受邀者', () async {
      final writer = _RecordingCallLifecycleWriter();
      final intent = RtcCallEntryIntent.conversation(
        mediaType: RtcCallEntryMediaType.audio,
        conversationId: 'conversation-capacity',
        participantCount: 40,
        maxParticipants: 32,
      );

      expect(intent.initialInviteeLimit, 31);
      await expectLater(
        RtcCallEntryCoordinator(lifecycleWriter: writer).initiate(
          intent,
          selectedInviteeIds: List<String>.generate(
            32,
            (index) => 'member-$index',
          ),
        ),
        throwsA(
          isA<RtcCallEntryRejected>().having(
            (error) => error.reason,
            'reason',
            RtcCallEntryUnavailableReason.participantLimitExceeded,
          ),
        ),
      );
      expect(writer.initiateCommands, isEmpty);
    });

    test('圈子入口同时保留 circle 与默认群 conversation context', () async {
      final writer = _RecordingCallLifecycleWriter();
      final intent = RtcCallEntryIntent.circle(
        mediaType: RtcCallEntryMediaType.video,
        circleId: 'circle-1',
        conversationId: 'conversation-circle',
        participantCount: 12,
      );

      await RtcCallEntryCoordinator(
        lifecycleWriter: writer,
      ).initiate(intent, selectedInviteeIds: const <String>['member-1']);

      final command = writer.initiateCommands.single;
      expect(command.callType, CallType.video);
      expect(command.conversationId, 'conversation-circle');
      expect(command.circleId, 'circle-1');
    });

    test('缺失 canonical conversation context 时不调用 writer', () async {
      final writer = _RecordingCallLifecycleWriter();
      final intent = RtcCallEntryIntent.circle(
        mediaType: RtcCallEntryMediaType.audio,
        circleId: 'circle-1',
        conversationId: '',
        participantCount: 4,
      );

      await expectLater(
        RtcCallEntryCoordinator(
          lifecycleWriter: writer,
        ).initiate(intent, selectedInviteeIds: const <String>['member-1']),
        throwsA(isA<RtcCallEntryRejected>()),
      );
      expect(writer.initiateCommands, isEmpty);
    });
  });
}

RelationshipCapabilityViewData _capability({
  required String relationState,
  required bool canStartVoiceCall,
  required bool canStartVideoCall,
  bool isBlocked = false,
  bool isBlockedBy = false,
}) {
  return RelationshipCapabilityViewData(
    viewerPersonaId: 'viewer-persona',
    targetPersonaId: 'target-persona',
    relationState: relationState,
    canFollow: false,
    canUnfollow: false,
    canFollowBack: false,
    canGreet: false,
    canOpenConversation: false,
    canCreateDirectConversation: false,
    canSendMessage: false,
    hasPendingGreeting: false,
    hasFormalConversation: false,
    canStartVoiceCall: canStartVoiceCall,
    canStartVideoCall: canStartVideoCall,
    isBlocked: isBlocked,
    isBlockedBy: isBlockedBy,
  );
}

final class _RecordingCallLifecycleWriter
    implements CallLifecycleCommandWriter {
  final List<RtcInitiateCallCommand> initiateCommands =
      <RtcInitiateCallCommand>[];

  @override
  Future<RtcInitiateCallResult> initiateCall(
    RtcInitiateCallCommand command,
  ) async {
    initiateCommands.add(command);
    final now = DateTime.utc(2026, 7, 20);
    return RtcInitiateCallResult(
      session: buildCallSessionContract(
        id: 'call-${initiateCommands.length}',
        callType: command.callType,
        status: CallStatus.ringing,
        initiatorId: 'viewer-persona',
        conversationId: command.conversationId,
        circleId: command.circleId,
        roomId: 'room-${initiateCommands.length}',
        maxParticipants: 16,
        participantCount: command.inviteeIds.length + 1,
        participants: command.inviteeIds
            .map(
              (userId) => buildCallParticipantContract(
                userId: userId,
                role: ParticipantRole.invitee,
                status: ParticipantStatus.invited,
                isMuted: false,
                isCameraOn: false,
              ),
            )
            .toList(growable: false),
        isScreenSharing: false,
        createdAt: now,
        updatedAt: now,
      ),
      mediaAccess: const RtcMediaSessionAccess(
        accessToken: 'fixture-media-access',
      ),
    );
  }

  @override
  Future<RtcAnswerCallResult> answerCall(RtcCallIdCommand command) =>
      throw UnimplementedError();

  @override
  Future<CallSession> cancelCall(RtcCallIdCommand command) =>
      throw UnimplementedError();

  @override
  Future<CallSession> hangupCall(RtcCallIdCommand command) =>
      throw UnimplementedError();

  @override
  Future<CallSession> rejectCall(RtcCallIdCommand command) =>
      throw UnimplementedError();
}
