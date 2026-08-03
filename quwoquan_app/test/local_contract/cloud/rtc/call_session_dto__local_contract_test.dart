import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/rtc/models/call_session_dto.dart';
import 'package:quwoquan_app/cloud/rtc/models/call_participant_dto.dart';
import 'package:quwoquan_app/cloud/rtc/models/rtc_repository_result_dtos.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        CallInviteStatus,
        CallStatus,
        CallType,
        EndReason,
        ParticipantRole,
        ParticipantStatus;

void main() {
  // ──────────────────────────────────────────────────────────────────
  // CallSession — 常规契约
  // ──────────────────────────────────────────────────────────────────
  group('CallSession — 常规契约', () {
    test('fromMap 解析全字段', () {
      final raw = <String, dynamic>{
        'callId': 'call_001',
        'callType': 'video',
        'status': 'in_call',
        'initiatorId': 'user_001',
        'conversationId': 'conv_001',
        'circleId': 'circle_001',
        'roomId': 'room_abc123',
        'maxParticipants': 16,
        'participantCount': 3,
        'participants': [
          {
            'userId': 'user_001',
            'role': 'initiator',
            'status': 'connected',
            'isMuted': false,
            'isCameraOn': true,
            'joinedAt': '2026-03-07T10:00:00Z',
          },
          {
            'userId': 'user_002',
            'role': 'invitee',
            'status': 'connected',
            'isMuted': true,
            'isCameraOn': false,
            'joinedAt': '2026-03-07T10:00:05Z',
          },
        ],
        'isScreenSharing': true,
        'screenShareUserId': 'user_001',
        'endReason': null,
        'durationMs': null,
        'startedAt': '2026-03-07T10:00:00Z',
        'endedAt': null,
        'createdAt': '2026-03-07T09:59:50Z',
        'updatedAt': '2026-03-07T10:00:10Z',
      };
      final dto = CallSession.fromMap(raw);

      expect(dto.callId, equals('call_001'));
      expect(dto.callType, CallType.video);
      expect(dto.status, CallStatus.inCall);
      expect(dto.initiatorId, equals('user_001'));
      expect(dto.conversationId, equals('conv_001'));
      expect(dto.circleId, equals('circle_001'));
      expect(dto.roomId, equals('room_abc123'));
      expect(dto.maxParticipants, equals(16));
      expect(dto.participantCount, equals(3));
      expect(dto.participants.length, equals(2));
      expect(dto.isScreenSharing, isTrue);
      expect(dto.screenShareUserId, equals('user_001'));
      expect(dto.endReason, isNull);
      expect(dto.durationMs, isNull);
      expect(dto.startedAt, isNotNull);
      expect(dto.startedAt!.year, equals(2026));
      expect(dto.endedAt, isNull);
      expect(dto.createdAt.month, equals(3));
      expect(dto.updatedAt.day, equals(7));
    });

    test('participants 元素为 Map 但非 Map<String,dynamic> 仍可解析', () {
      final nested = <String, Object>{
        'userId': 'user_001',
        'role': 'initiator',
        'status': 'connected',
        'isMuted': false,
        'isCameraOn': true,
      };
      final raw = <String, dynamic>{
        'callId': 'call_p',
        'callType': 'audio',
        'status': 'ringing',
        'initiatorId': 'user_001',
        'roomId': 'room_x',
        'createdAt': '2026-01-01T00:00:00Z',
        'updatedAt': '2026-01-01T00:00:00Z',
        'participants': <Object>[nested],
      };
      final dto = CallSession.fromMap(raw);
      expect(dto.participants, hasLength(1));
      expect(dto.participants.single.userId, equals('user_001'));
    });

    test('fromMap 使用 callId 字段', () {
      final raw = <String, dynamic>{
        'callId': 'call_alias',
        'callType': 'audio',
        'status': 'ended',
        'initiatorId': 'user_002',
        'roomId': 'room_xyz',
        'createdAt': '2026-01-01T00:00:00Z',
        'updatedAt': '2026-01-01T00:00:00Z',
      };
      final dto = CallSession.fromMap(raw);
      expect(dto.callId, equals('call_alias'));
    });

    test('toMap round-trip 保持字段完整', () {
      final raw = <String, dynamic>{
        'callId': 'call_rt',
        'callType': 'video',
        'status': 'in_call',
        'initiatorId': 'u1',
        'conversationId': 'conv_rt',
        'roomId': 'room_rt',
        'maxParticipants': 8,
        'participantCount': 2,
        'participants': [
          {
            'userId': 'u1',
            'role': 'initiator',
            'status': 'connected',
            'isMuted': false,
            'isCameraOn': true,
            'joinedAt': '2026-01-01T00:00:00.000Z',
          },
        ],
        'isScreenSharing': false,
        'startedAt': '2026-01-01T00:00:00.000Z',
        'createdAt': '2026-01-01T00:00:00.000Z',
        'updatedAt': '2026-01-01T00:00:00.000Z',
      };
      final dto = CallSession.fromMap(raw);
      final map = dto.toMap();

      expect(map['callId'], equals('call_rt'));
      expect(map['callType'], equals('video'));
      expect(map['maxParticipants'], equals(8));
      expect(map['participants'], isA<List>());
      expect((map['participants'] as List).length, equals(1));
    });

    test('participants 正确解析嵌套 CallParticipant', () {
      final raw = <String, dynamic>{
        'callId': 'call_nested',
        'callType': 'video',
        'status': 'in_call',
        'initiatorId': 'u1',
        'roomId': 'room_nested',
        'participants': [
          {
            'userId': 'u1',
            'role': 'initiator',
            'status': 'connected',
            'isMuted': false,
            'isCameraOn': true,
          },
          {
            'userId': 'u2',
            'role': 'invitee',
            'status': 'invited',
            'isMuted': true,
            'isCameraOn': false,
          },
        ],
        'createdAt': '2026-01-01T00:00:00Z',
        'updatedAt': '2026-01-01T00:00:00Z',
      };
      final dto = CallSession.fromMap(raw);
      expect(dto.participants.length, equals(2));
      expect(dto.participants[0].userId, equals('u1'));
      expect(dto.participants[0].role, ParticipantRole.initiator);
      expect(dto.participants[0].isMuted, isFalse);
      expect(dto.participants[1].userId, equals('u2'));
      expect(dto.participants[1].isCameraOn, isFalse);
    });

    test('ended session 解析 endReason 和 durationMs', () {
      final raw = <String, dynamic>{
        'callId': 'call_ended',
        'callType': 'audio',
        'status': 'ended',
        'initiatorId': 'u1',
        'roomId': 'room_end',
        'endReason': 'normal',
        'durationMs': 930000,
        'startedAt': '2026-03-07T08:00:00Z',
        'endedAt': '2026-03-07T08:15:30Z',
        'createdAt': '2026-03-07T07:59:55Z',
        'updatedAt': '2026-03-07T08:15:30Z',
      };
      final dto = CallSession.fromMap(raw);
      expect(dto.endReason, EndReason.normal);
      expect(dto.durationMs, equals(930000));
      expect(dto.endedAt, isNotNull);
      expect(dto.endedAt!.minute, equals(15));
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // CallSession — 单轨契约
  // ──────────────────────────────────────────────────────────────────
  group('CallSession — 单轨契约', () {
    test('拒绝 _id 和 id alias，只认 callId', () {
      expect(
        () => CallSession.fromMap(<String, dynamic>{
          '_id': 'call_compat',
          'initiatorId': 'u1',
          'roomId': 'r1',
          'createdAt': '2026-01-01T00:00:00Z',
          'updatedAt': '2026-01-01T00:00:00Z',
        }),
        throwsFormatException,
      );
      expect(
        () => CallSession.fromMap(<String, dynamic>{
          'id': 'call_generic',
          'initiatorId': 'u1',
          'roomId': 'r1',
          'createdAt': '2026-01-01T00:00:00Z',
          'updatedAt': '2026-01-01T00:00:00Z',
        }),
        throwsFormatException,
      );
      final canonical = CallSession.fromMap(<String, dynamic>{
        'callId': 'call_canonical',
        'callType': 'audio',
        'status': 'in_call',
        'initiatorId': 'u1',
        'roomId': 'r1',
        'createdAt': '2026-01-01T00:00:00Z',
        'updatedAt': '2026-01-01T00:00:00Z',
      });
      expect(canonical.callId, equals('call_canonical'));
    });

    test('缺少 callType 默认 audio', () {
      final raw = <String, dynamic>{
        'callId': 'call_no_type',
        'status': 'in_call',
        'initiatorId': 'u1',
        'roomId': 'r1',
        'createdAt': '2026-01-01T00:00:00Z',
        'updatedAt': '2026-01-01T00:00:00Z',
      };
      final dto = CallSession.fromMap(raw);
      expect(dto.callType, CallType.audio);
    });

    test('缺少 maxParticipants 默认 32', () {
      final raw = <String, dynamic>{
        'callId': 'call_no_max',
        'callType': 'video',
        'status': 'in_call',
        'initiatorId': 'u1',
        'roomId': 'r1',
        'createdAt': '2026-01-01T00:00:00Z',
        'updatedAt': '2026-01-01T00:00:00Z',
      };
      final dto = CallSession.fromMap(raw);
      expect(dto.maxParticipants, equals(32));
    });

    test('toMap round-trip 保持 participants 顺序', () {
      final raw = <String, dynamic>{
        'callId': 'call_order',
        'callType': 'video',
        'status': 'in_call',
        'initiatorId': 'u1',
        'roomId': 'r1',
        'participants': [
          {'userId': 'u1', 'role': 'initiator', 'status': 'connected'},
          {'userId': 'u2', 'role': 'invitee', 'status': 'connected'},
          {'userId': 'u3', 'role': 'invitee', 'status': 'invited'},
        ],
        'createdAt': '2026-01-01T00:00:00.000Z',
        'updatedAt': '2026-01-01T00:00:00.000Z',
      };
      final dto = CallSession.fromMap(raw);
      final map = dto.toMap();
      final dto2 = CallSession.fromMap(map);
      expect(dto2.participants.length, equals(3));
      expect(dto2.participants[0].userId, equals('u1'));
      expect(dto2.participants[2].userId, equals('u3'));
    });

    test('copyWith 仅修改指定字段', () {
      final raw = <String, dynamic>{
        'callId': 'call_copy',
        'callType': 'audio',
        'status': 'in_call',
        'initiatorId': 'u1',
        'roomId': 'r1',
        'createdAt': '2026-01-01T00:00:00Z',
        'updatedAt': '2026-01-01T00:00:00Z',
      };
      final dto = CallSession.fromMap(raw);
      final updated = dto.copyWith(status: CallStatus.ended);
      expect(updated.status, CallStatus.ended);
      expect(updated.callId, equals('call_copy'));
      expect(updated.callType, CallType.audio);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // CallSession — 异常/边界契约
  // ──────────────────────────────────────────────────────────────────
  group('CallSession — 异常/边界契约', () {
    test('空 map 缺少必填字段时 fail-closed', () {
      expect(
        () => CallSession.fromMap(const <String, dynamic>{}),
        throwsFormatException,
      );
    });

    test('null 值字段安全', () {
      final raw = <String, dynamic>{
        'callId': null,
        'callType': null,
        'status': null,
        'initiatorId': null,
        'conversationId': null,
        'circleId': null,
        'roomId': null,
        'maxParticipants': null,
        'participantCount': null,
        'participants': null,
        'isScreenSharing': null,
        'screenShareUserId': null,
        'endReason': null,
        'durationMs': null,
        'startedAt': null,
        'endedAt': null,
        'createdAt': null,
        'updatedAt': null,
      };
      expect(() => CallSession.fromMap(raw), throwsFormatException);
    });

    test('participants 非 List 类型不崩溃', () {
      final raw = <String, dynamic>{
        'callId': 'call_bad_parts',
        'callType': 'audio',
        'status': 'in_call',
        'initiatorId': 'u1',
        'roomId': 'r1',
        'participants': 'not-a-list',
        'createdAt': '2026-01-01T00:00:00Z',
        'updatedAt': '2026-01-01T00:00:00Z',
      };
      expect(() => CallSession.fromMap(raw), returnsNormally);
      final dto = CallSession.fromMap(raw);
      expect(dto.participants, isEmpty);
    });

    test('participants 含非 Map 元素跳过', () {
      final raw = <String, dynamic>{
        'callId': 'call_mixed_parts',
        'callType': 'audio',
        'status': 'in_call',
        'initiatorId': 'u1',
        'roomId': 'r1',
        'participants': [
          {'userId': 'u1', 'role': 'initiator', 'status': 'connected'},
          'invalid-entry',
          42,
        ],
        'createdAt': '2026-01-01T00:00:00Z',
        'updatedAt': '2026-01-01T00:00:00Z',
      };
      expect(() => CallSession.fromMap(raw), returnsNormally);
      final dto = CallSession.fromMap(raw);
      expect(dto.participants.length, equals(1));
    });

    test('optional 字段缺失不影响 required 字段', () {
      final raw = <String, dynamic>{
        'callId': 'call_minimal',
        'callType': 'audio',
        'status': 'ringing',
        'initiatorId': 'u1',
        'roomId': 'r1',
        'createdAt': '2026-01-01T00:00:00Z',
        'updatedAt': '2026-01-01T00:00:00Z',
      };
      final dto = CallSession.fromMap(raw);
      expect(dto.callId, equals('call_minimal'));
      expect(dto.conversationId, isNull);
      expect(dto.circleId, isNull);
      expect(dto.screenShareUserId, isNull);
      expect(dto.endReason, isNull);
      expect(dto.durationMs, isNull);
      expect(dto.startedAt, isNull);
      expect(dto.endedAt, isNull);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // CallParticipant — 常规契约
  // ──────────────────────────────────────────────────────────────────
  group('CallParticipant — 常规契约', () {
    test('fromMap 解析全字段', () {
      final raw = <String, dynamic>{
        'userId': 'user_001',
        'role': 'initiator',
        'status': 'connected',
        'isMuted': true,
        'isCameraOn': false,
        'joinedAt': '2026-03-07T10:00:00Z',
        'leftAt': '2026-03-07T10:30:00Z',
      };
      final dto = CallParticipant.fromMap(raw);
      expect(dto.userId, equals('user_001'));
      expect(dto.role, ParticipantRole.initiator);
      expect(dto.status, ParticipantStatus.connected);
      expect(dto.isMuted, isTrue);
      expect(dto.isCameraOn, isFalse);
      expect(dto.joinedAt, isNotNull);
      expect(dto.joinedAt!.hour, equals(10));
      expect(dto.leftAt, isNotNull);
      expect(dto.leftAt!.minute, equals(30));
    });

    test('toMap round-trip 正确', () {
      final raw = <String, dynamic>{
        'userId': 'user_rt',
        'role': 'invitee',
        'status': 'connected',
        'isMuted': false,
        'isCameraOn': true,
        'joinedAt': '2026-01-01T00:00:00.000Z',
      };
      final dto = CallParticipant.fromMap(raw);
      final map = dto.toMap();
      final dto2 = CallParticipant.fromMap(map);
      expect(dto2.userId, equals(dto.userId));
      expect(dto2.role, equals(dto.role));
      expect(dto2.isMuted, equals(dto.isMuted));
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // CallParticipant — 单轨契约
  // ──────────────────────────────────────────────────────────────────
  group('CallParticipant — 单轨契约', () {
    test('缺少 role 默认 invitee', () {
      final raw = <String, dynamic>{'userId': 'u1', 'status': 'connected'};
      final dto = CallParticipant.fromMap(raw);
      expect(dto.role, ParticipantRole.invitee);
    });

    test('缺少 isCameraOn 默认 true', () {
      final raw = <String, dynamic>{
        'userId': 'u1',
        'role': 'invitee',
        'status': 'connected',
      };
      final dto = CallParticipant.fromMap(raw);
      expect(dto.isCameraOn, isTrue);
    });

    test('缺少 isMuted 默认 false', () {
      final raw = <String, dynamic>{
        'userId': 'u1',
        'role': 'invitee',
        'status': 'connected',
      };
      final dto = CallParticipant.fromMap(raw);
      expect(dto.isMuted, isFalse);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // CallParticipant — 异常/边界契约
  // ──────────────────────────────────────────────────────────────────
  group('CallParticipant — 异常/边界契约', () {
    test('空 map 缺少 userId 时 fail-closed', () {
      expect(
        () => CallParticipant.fromMap(const <String, dynamic>{}),
        throwsFormatException,
      );
    });

    test('null 值字段安全', () {
      final raw = <String, dynamic>{
        'userId': null,
        'role': null,
        'status': null,
        'isMuted': null,
        'isCameraOn': null,
        'joinedAt': null,
        'leftAt': null,
      };
      expect(() => CallParticipant.fromMap(raw), throwsFormatException);
    });
  });

  group('RTC enum — 严格单轨 wire 契约', () {
    test('canonical wire 值与 typed enum 一一对应', () {
      expect(CallType.fromString('audio'), CallType.audio);
      expect(CallStatus.fromString('in_call'), CallStatus.inCall);
      expect(
        ParticipantRole.fromString('initiator'),
        ParticipantRole.initiator,
      );
      expect(
        ParticipantStatus.fromString('connected'),
        ParticipantStatus.connected,
      );
      expect(
        CallInviteStatus.fromString('cancelled'),
        CallInviteStatus.cancelled,
      );
      expect(EndReason.fromString('no_answer'), EndReason.noAnswer);
      expect(EndReason.fromString('last_leave'), EndReason.lastLeave);
      expect(EndReason.fromString('account_closed'), EndReason.accountClosed);
      expect(
        EndReason.fromString('account_suspended'),
        EndReason.accountSuspended,
      );
    });

    test('未知值和旧 EndReason 别名全部 fail-closed', () {
      expect(() => CallType.fromString('unknown'), throwsFormatException);
      expect(() => CallStatus.fromString('completed'), throwsFormatException);
      expect(() => ParticipantRole.fromString('caller'), throwsFormatException);
      expect(
        () => ParticipantStatus.fromString('unknown'),
        throwsFormatException,
      );
      expect(
        () => CallInviteStatus.fromString('unknown'),
        throwsFormatException,
      );
      for (final legacy in <String>[
        'completed',
        'busy',
        'initiator_hangup',
        'network_error',
        'unknown',
      ]) {
        expect(() => EndReason.fromString(legacy), throwsFormatException);
      }
    });

    test('DTO decoder 遇到未知 enum wire 值直接拒绝', () {
      expect(
        () => CallSession.fromMap(<String, Object?>{
          'callId': 'call_bad_enum',
          'callType': 'voice',
          'status': 'ringing',
          'initiatorId': 'u1',
          'roomId': 'r1',
          'createdAt': '2026-01-01T00:00:00Z',
          'updatedAt': '2026-01-01T00:00:00Z',
        }),
        throwsFormatException,
      );
      expect(
        () => CallParticipant.fromMap(<String, Object?>{
          'userId': 'u1',
          'role': 'caller',
          'status': 'connected',
        }),
        throwsFormatException,
      );
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // RtcJoinCredentials 媒体访问凭据
  // ──────────────────────────────────────────────────────────────────
  group('RtcJoinCredentials — 常规契约', () {
    test('fromMap 解析全字段', () {
      final raw = <String, dynamic>{
        'mediaAccess': <String, dynamic>{
          'accessToken': 'eyJhbGciOiJIUzI1NiJ9.mock_payload.mock_sig',
        },
        'session': <String, dynamic>{
          'callId': 'call_001',
          'initiatorId': 'user_001',
          'roomId': 'room_abc123',
          'createdAt': '2026-01-01T00:00:00Z',
          'updatedAt': '2026-01-01T00:00:00Z',
        },
      };
      final dto = decodeRtcJoinCallResult(raw);
      expect(dto.mediaAccess.accessToken, startsWith('eyJ'));
      expect(dto.session.roomId, equals('room_abc123'));
      expect(dto.session.callId, equals('call_001'));
    });

    test('嵌套 session 信封（JoinCall）', () {
      final raw = <String, dynamic>{
        'mediaAccess': <String, dynamic>{'accessToken': 'tok_join'},
        'session': <String, dynamic>{
          'callId': 'call_099',
          'initiatorId': 'user_099',
          'roomId': 'room_nested',
          'createdAt': '2026-01-01T00:00:00Z',
          'updatedAt': '2026-01-01T00:00:00Z',
        },
      };
      final dto = decodeRtcJoinCallResult(raw);
      expect(dto.mediaAccess.accessToken, equals('tok_join'));
      expect(dto.session.roomId, equals('room_nested'));
      expect(dto.session.callId, equals('call_099'));
    });
  });

  group('RtcJoinCredentials — 单轨契约', () {
    test('缺少 session 时 fail-closed', () {
      expect(
        () => decodeRtcJoinCallResult(const <String, dynamic>{}),
        throwsFormatException,
      );
    });
  });

  group('RtcJoinCredentials — 异常/边界契约', () {
    test('null 值字段安全', () {
      final raw = <String, dynamic>{'session': null, 'mediaAccess': null};
      expect(() => decodeRtcJoinCallResult(raw), throwsFormatException);
    });
  });

  group('Rtc 结果 DTO — rtc-service 信封', () {
    test('RtcInitiateCallResult 嵌套 session', () {
      final raw = <String, dynamic>{
        'mediaAccess': <String, dynamic>{'accessToken': 'tok_i'},
        'session': <String, dynamic>{
          'callId': 'c1',
          'callType': 'audio',
          'status': 'ringing',
          'initiatorId': 'u1',
          'roomId': 'r1',
          'maxParticipants': 2,
          'participantCount': 1,
          'createdAt': '2026-01-01T00:00:00Z',
          'updatedAt': '2026-01-01T00:00:00Z',
        },
      };
      final dto = decodeRtcInitiateCallResult(raw);
      expect(dto.mediaAccess.accessToken, equals('tok_i'));
      expect(dto.session.callId, equals('c1'));
      expect(dto.session.roomId, equals('r1'));
    });

    test('RtcAnswerCallResult 嵌套 session', () {
      final raw = <String, dynamic>{
        'mediaAccess': <String, dynamic>{'accessToken': 'tok_a'},
        'session': <String, dynamic>{
          'callId': 'c2',
          'callType': 'video',
          'status': 'in_call',
          'initiatorId': 'u2',
          'roomId': 'r_a',
          'maxParticipants': 8,
          'participantCount': 2,
          'createdAt': '2026-01-01T00:00:00Z',
          'updatedAt': '2026-01-01T00:00:00Z',
        },
      };
      final dto = decodeRtcAnswerCallResult(raw);
      expect(dto.mediaAccess.accessToken, equals('tok_a'));
      expect(dto.session.roomId, equals('r_a'));
      expect(dto.session.callId, equals('c2'));
    });
  });
}
