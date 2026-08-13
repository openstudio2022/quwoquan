// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-005
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/generated/rtc_contracts.dart'
    show
        CallInviteStatus,
        CallParticipant,
        CallSession,
        CallStatus,
        CallType,
        EndReason,
        ParticipantRole,
        ParticipantStatus,
        decodeRtcAnswerCallResult,
        decodeRtcInitiateCallResult,
        decodeRtcJoinCredentials;

void main() {
  group('CallSession canonical wire', () {
    test('decodes and re-encodes the complete canonical payload', () {
      final session = CallSession.fromWire(_sessionWire());

      expect(session.id, 'call_001');
      expect(session.callType, CallType.video);
      expect(session.status, CallStatus.inCall);
      expect(session.initiatorId, 'user_001');
      expect(session.initiatorRingtoneId, 'official:ringtone:gentle');
      expect(session.conversationId, 'conv_001');
      expect(session.circleId, 'circle_001');
      expect(session.roomId, 'room_abc123');
      expect(session.maxParticipants, 16);
      expect(session.participantCount, 2);
      expect(session.participants, hasLength(2));
      expect(session.participants!.first.role, ParticipantRole.initiator);
      expect(session.participants!.last.status, ParticipantStatus.invited);
      expect(session.isScreenSharing, isTrue);
      expect(session.screenShareUserId, 'user_001');
      expect(session.endReason, EndReason.normal);
      expect(session.durationMs, 930000);
      expect(session.startedAt, DateTime.utc(2026, 3, 7, 10));
      expect(session.endedAt, DateTime.utc(2026, 3, 7, 10, 15, 30));

      final encoded = session.toWire();
      expect(encoded['id'], 'call_001');
      expect(encoded, isNot(contains('callId')));
      expect(encoded, isNot(contains('_id')));
      expect(encoded['callType'], 'video');
      expect(encoded['status'], 'in_call');
      expect(encoded['participants'], isA<List<Object?>>());
      expect(
        CallSession.fromWire(encoded).participants!.map((item) => item.userId),
        orderedEquals(<String>['user_001', 'user_002']),
      );
    });

    test('accepts omitted nullable fields without inventing defaults', () {
      final wire = _sessionWire()
        ..remove('initiatorRingtoneId')
        ..remove('conversationId')
        ..remove('circleId')
        ..remove('participants')
        ..remove('screenShareUserId')
        ..remove('endReason')
        ..remove('durationMs')
        ..remove('startedAt')
        ..remove('endedAt');

      final session = CallSession.fromWire(wire);
      expect(session.initiatorRingtoneId, isNull);
      expect(session.conversationId, isNull);
      expect(session.circleId, isNull);
      expect(session.participants, isNull);
      expect(session.screenShareUserId, isNull);
      expect(session.endReason, isNull);
      expect(session.durationMs, isNull);
      expect(session.startedAt, isNull);
      expect(session.endedAt, isNull);
    });

    test(
      'rejects retired identities, unknown fields, and missing required data',
      () {
        for (final retiredIdentity in <String>['callId', '_id']) {
          final wire = _sessionWire()
            ..remove('id')
            ..[retiredIdentity] = 'call_retired';
          expect(
            () => CallSession.fromWire(wire),
            throwsFormatException,
            reason: '$retiredIdentity must not be accepted',
          );
        }

        final unknown = _sessionWire()..['isRecording'] = false;
        expect(() => CallSession.fromWire(unknown), throwsFormatException);

        for (final requiredField in <String>[
          'id',
          'callType',
          'status',
          'initiatorId',
          'roomId',
          'maxParticipants',
          'participantCount',
          'isScreenSharing',
          'createdAt',
          'updatedAt',
        ]) {
          final wire = _sessionWire()..remove(requiredField);
          expect(
            () => CallSession.fromWire(wire),
            throwsFormatException,
            reason: '$requiredField must be required',
          );
        }
      },
    );

    test('rejects malformed participant collections and enum values', () {
      expect(
        () => CallSession.fromWire(
          _sessionWire()..['participants'] = 'not-a-list',
        ),
        throwsFormatException,
      );
      expect(
        () => CallSession.fromWire(
          _sessionWire()..['participants'] = <Object?>['not-an-object'],
        ),
        throwsFormatException,
      );
      expect(
        () => CallSession.fromWire(_sessionWire()..['callType'] = 'voice'),
        throwsFormatException,
      );
      expect(
        () => CallSession.fromWire(_sessionWire()..['status'] = 'completed'),
        throwsFormatException,
      );
    });
  });

  group('CallParticipant canonical wire', () {
    test('decodes and round-trips all fields', () {
      final participant = CallParticipant.fromWire(_participantWire());

      expect(participant.userId, 'user_001');
      expect(participant.role, ParticipantRole.initiator);
      expect(participant.status, ParticipantStatus.connected);
      expect(participant.isMuted, isFalse);
      expect(participant.isCameraOn, isTrue);
      expect(participant.joinedAt, DateTime.utc(2026, 3, 7, 10));
      expect(participant.leftAt, DateTime.utc(2026, 3, 7, 10, 30));
      expect(participant.inviteStatus, CallInviteStatus.accepted);
      expect(participant.invitedBy, 'user_inviter');

      final encoded = participant.toWire();
      expect(encoded['role'], 'initiator');
      expect(encoded['status'], 'connected');
      expect(CallParticipant.fromWire(encoded).userId, participant.userId);
    });

    test('requires role, status, mute, and camera state', () {
      for (final requiredField in <String>[
        'userId',
        'role',
        'status',
        'isMuted',
        'isCameraOn',
      ]) {
        final wire = _participantWire()..remove(requiredField);
        expect(
          () => CallParticipant.fromWire(wire),
          throwsFormatException,
          reason: '$requiredField must be required',
        );
      }
    });

    test('rejects unknown fields and enum aliases', () {
      expect(
        () => CallParticipant.fromWire(
          _participantWire()..['displayName'] = 'not-owned-here',
        ),
        throwsFormatException,
      );
      expect(
        () => CallParticipant.fromWire(_participantWire()..['role'] = 'caller'),
        throwsFormatException,
      );
    });
  });

  group('RTC enum single track', () {
    test('canonical wire values use one contextual decoder', () {
      expect(CallType.fromWire('audio', 'callType'), CallType.audio);
      expect(CallStatus.fromWire('in_call', 'status'), CallStatus.inCall);
      expect(
        ParticipantRole.fromWire('initiator', 'role'),
        ParticipantRole.initiator,
      );
      expect(
        ParticipantStatus.fromWire('connected', 'status'),
        ParticipantStatus.connected,
      );
      expect(
        CallInviteStatus.fromWire('cancelled', 'inviteStatus'),
        CallInviteStatus.cancelled,
      );
      expect(EndReason.fromWire('no_answer', 'endReason'), EndReason.noAnswer);
      expect(
        EndReason.fromWire('last_leave', 'endReason'),
        EndReason.lastLeave,
      );
      expect(CallType.video.wireName, 'video');
      expect(EndReason.accountClosed.wireName, 'account_closed');
    });

    test('unknown and retired wire values fail closed', () {
      expect(
        () => CallType.fromWire('unknown', 'callType'),
        throwsFormatException,
      );
      expect(
        () => ParticipantRole.fromWire('caller', 'role'),
        throwsFormatException,
      );
      for (final retired in <String>[
        'completed',
        'busy',
        'initiator_hangup',
        'network_error',
        'unknown',
      ]) {
        expect(
          () => EndReason.fromWire(retired, 'endReason'),
          throwsFormatException,
        );
      }
    });
  });

  group('RTC result envelopes', () {
    test('join, initiate, and answer decode the canonical nested session', () {
      final envelope = <String, Object?>{
        'session': _sessionWire(),
        'mediaAccess': <String, Object?>{'accessToken': 'token_001'},
      };

      expect(decodeRtcJoinCredentials(envelope).session.id, 'call_001');
      expect(
        decodeRtcInitiateCallResult(envelope).mediaAccess.accessToken,
        'token_001',
      );
      expect(decodeRtcAnswerCallResult(envelope).session.roomId, 'room_abc123');
    });

    test('missing or null envelope members fail closed', () {
      expect(
        () => decodeRtcJoinCredentials(const <String, Object?>{}),
        throwsFormatException,
      );
      expect(
        () => decodeRtcInitiateCallResult(const <String, Object?>{
          'session': null,
          'mediaAccess': null,
        }),
        throwsFormatException,
      );
    });
  });
}

Map<String, Object?> _sessionWire() => <String, Object?>{
  'id': 'call_001',
  'callType': 'video',
  'status': 'in_call',
  'initiatorId': 'user_001',
  'initiatorRingtoneId': 'official:ringtone:gentle',
  'conversationId': 'conv_001',
  'circleId': 'circle_001',
  'roomId': 'room_abc123',
  'maxParticipants': 16,
  'participantCount': 2,
  'participants': <Object?>[
    _participantWire(),
    <String, Object?>{
      'userId': 'user_002',
      'role': 'invitee',
      'status': 'invited',
      'isMuted': true,
      'isCameraOn': false,
    },
  ],
  'isScreenSharing': true,
  'screenShareUserId': 'user_001',
  'endReason': 'normal',
  'durationMs': 930000,
  'startedAt': '2026-03-07T10:00:00Z',
  'endedAt': '2026-03-07T10:15:30Z',
  'createdAt': '2026-03-07T09:59:50Z',
  'updatedAt': '2026-03-07T10:15:30Z',
};

Map<String, Object?> _participantWire() => <String, Object?>{
  'userId': 'user_001',
  'role': 'initiator',
  'status': 'connected',
  'isMuted': false,
  'isCameraOn': true,
  'joinedAt': '2026-03-07T10:00:00Z',
  'leftAt': '2026-03-07T10:30:00Z',
  'inviteStatus': 'accepted',
  'invitedBy': 'user_inviter',
};
