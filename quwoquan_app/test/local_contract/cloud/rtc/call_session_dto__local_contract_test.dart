import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/rtc/models/call_session_dto.dart';
import 'package:quwoquan_app/cloud/rtc/models/call_participant_dto.dart';
import 'package:quwoquan_app/cloud/rtc/models/rtc_repository_result_dtos.dart';

void main() {
  // ──────────────────────────────────────────────────────────────────
  // CallSessionDto — 常规契约
  // ──────────────────────────────────────────────────────────────────
  group('CallSessionDto — 常规契约', () {
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
      final dto = CallSessionDto.fromMap(raw);

      expect(dto.callId, equals('call_001'));
      expect(dto.callType, equals('video'));
      expect(dto.status, equals('in_call'));
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
      final dto = CallSessionDto.fromMap(raw);
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
      final dto = CallSessionDto.fromMap(raw);
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
      final dto = CallSessionDto.fromMap(raw);
      final map = dto.toMap();

      expect(map['callId'], equals('call_rt'));
      expect(map['callType'], equals('video'));
      expect(map['maxParticipants'], equals(8));
      expect(map['participants'], isA<List>());
      expect((map['participants'] as List).length, equals(1));
    });

    test('participants 正确解析嵌套 CallParticipantDto', () {
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
      final dto = CallSessionDto.fromMap(raw);
      expect(dto.participants.length, equals(2));
      expect(dto.participants[0].userId, equals('u1'));
      expect(dto.participants[0].role, equals('initiator'));
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
      final dto = CallSessionDto.fromMap(raw);
      expect(dto.endReason, equals('normal'));
      expect(dto.durationMs, equals(930000));
      expect(dto.endedAt, isNotNull);
      expect(dto.endedAt!.minute, equals(15));
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // CallSessionDto — 单轨契约
  // ──────────────────────────────────────────────────────────────────
  group('CallSessionDto — 单轨契约', () {
    test('拒绝 _id 和 id alias，只认 callId', () {
      expect(
        () => CallSessionDto.fromMap(<String, dynamic>{
          '_id': 'call_compat',
          'initiatorId': 'u1',
          'roomId': 'r1',
          'createdAt': '2026-01-01T00:00:00Z',
          'updatedAt': '2026-01-01T00:00:00Z',
        }),
        throwsFormatException,
      );
      expect(
        () => CallSessionDto.fromMap(<String, dynamic>{
          'id': 'call_generic',
          'initiatorId': 'u1',
          'roomId': 'r1',
          'createdAt': '2026-01-01T00:00:00Z',
          'updatedAt': '2026-01-01T00:00:00Z',
        }),
        throwsFormatException,
      );
      final canonical = CallSessionDto.fromMap(<String, dynamic>{
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
      final dto = CallSessionDto.fromMap(raw);
      expect(dto.callType, equals('audio'));
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
      final dto = CallSessionDto.fromMap(raw);
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
      final dto = CallSessionDto.fromMap(raw);
      final map = dto.toMap();
      final dto2 = CallSessionDto.fromMap(map);
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
      final dto = CallSessionDto.fromMap(raw);
      final updated = dto.copyWith(status: 'ended');
      expect(updated.status, equals('ended'));
      expect(updated.callId, equals('call_copy'));
      expect(updated.callType, equals('audio'));
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // CallSessionDto — 异常/边界契约
  // ──────────────────────────────────────────────────────────────────
  group('CallSessionDto — 异常/边界契约', () {
    test('空 map 缺少必填字段时 fail-closed', () {
      expect(
        () => CallSessionDto.fromMap(const <String, dynamic>{}),
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
      expect(() => CallSessionDto.fromMap(raw), throwsFormatException);
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
      expect(() => CallSessionDto.fromMap(raw), returnsNormally);
      final dto = CallSessionDto.fromMap(raw);
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
      expect(() => CallSessionDto.fromMap(raw), returnsNormally);
      final dto = CallSessionDto.fromMap(raw);
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
      final dto = CallSessionDto.fromMap(raw);
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
  // CallParticipantDto — 常规契约
  // ──────────────────────────────────────────────────────────────────
  group('CallParticipantDto — 常规契约', () {
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
      final dto = CallParticipantDto.fromMap(raw);
      expect(dto.userId, equals('user_001'));
      expect(dto.role, equals('initiator'));
      expect(dto.status, equals('connected'));
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
      final dto = CallParticipantDto.fromMap(raw);
      final map = dto.toMap();
      final dto2 = CallParticipantDto.fromMap(map);
      expect(dto2.userId, equals(dto.userId));
      expect(dto2.role, equals(dto.role));
      expect(dto2.isMuted, equals(dto.isMuted));
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // CallParticipantDto — 单轨契约
  // ──────────────────────────────────────────────────────────────────
  group('CallParticipantDto — 单轨契约', () {
    test('缺少 role 默认 invitee', () {
      final raw = <String, dynamic>{'userId': 'u1', 'status': 'connected'};
      final dto = CallParticipantDto.fromMap(raw);
      expect(dto.role, equals('invitee'));
    });

    test('缺少 isCameraOn 默认 true', () {
      final raw = <String, dynamic>{
        'userId': 'u1',
        'role': 'invitee',
        'status': 'connected',
      };
      final dto = CallParticipantDto.fromMap(raw);
      expect(dto.isCameraOn, isTrue);
    });

    test('缺少 isMuted 默认 false', () {
      final raw = <String, dynamic>{
        'userId': 'u1',
        'role': 'invitee',
        'status': 'connected',
      };
      final dto = CallParticipantDto.fromMap(raw);
      expect(dto.isMuted, isFalse);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // CallParticipantDto — 异常/边界契约
  // ──────────────────────────────────────────────────────────────────
  group('CallParticipantDto — 异常/边界契约', () {
    test('空 map 缺少 userId 时 fail-closed', () {
      expect(
        () => CallParticipantDto.fromMap(const <String, dynamic>{}),
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
      expect(() => CallParticipantDto.fromMap(raw), throwsFormatException);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // RtcJoinCredentialsDto（原 RtcTokenDto 合并）
  // ──────────────────────────────────────────────────────────────────
  group('RtcJoinCredentialsDto — 常规契约', () {
    test('fromMap 解析全字段', () {
      final raw = <String, dynamic>{
        'token': 'eyJhbGciOiJIUzI1NiJ9.mock_payload.mock_sig',
        'session': <String, dynamic>{
          'callId': 'call_001',
          'initiatorId': 'user_001',
          'roomId': 'room_abc123',
          'createdAt': '2026-01-01T00:00:00Z',
          'updatedAt': '2026-01-01T00:00:00Z',
        },
      };
      final dto = decodeRtcJoinCallResult(raw);
      expect(dto.token, startsWith('eyJ'));
      expect(dto.roomId, equals('room_abc123'));
      expect(dto.callId, equals('call_001'));
    });

    test('嵌套 session 信封（JoinCall）', () {
      final raw = <String, dynamic>{
        'token': 'tok_join',
        'session': <String, dynamic>{
          'callId': 'call_099',
          'initiatorId': 'user_099',
          'roomId': 'room_nested',
          'createdAt': '2026-01-01T00:00:00Z',
          'updatedAt': '2026-01-01T00:00:00Z',
        },
      };
      final dto = decodeRtcJoinCallResult(raw);
      expect(dto.token, equals('tok_join'));
      expect(dto.roomId, equals('room_nested'));
      expect(dto.callId, equals('call_099'));
    });
  });

  group('RtcJoinCredentialsDto — 单轨契约', () {
    test('缺少 session 时 fail-closed', () {
      expect(
        () => decodeRtcJoinCallResult(const <String, dynamic>{}),
        throwsFormatException,
      );
    });
  });

  group('RtcJoinCredentialsDto — 异常/边界契约', () {
    test('null 值字段安全', () {
      final raw = <String, dynamic>{
        'token': null,
        'roomId': null,
        'callId': null,
      };
      expect(() => decodeRtcJoinCallResult(raw), throwsFormatException);
    });
  });

  group('Rtc 结果 DTO — rtc-service 信封', () {
    test('RtcInitiateCallResultDto 嵌套 session', () {
      final raw = <String, dynamic>{
        'token': 'tok_i',
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
      expect(dto.token, equals('tok_i'));
      expect(dto.session.callId, equals('c1'));
      expect(dto.session.roomId, equals('r1'));
    });

    test('RtcAnswerCallResultDto 嵌套 session', () {
      final raw = <String, dynamic>{
        'token': 'tok_a',
        'roomId': 'r_a',
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
      expect(dto.token, equals('tok_a'));
      expect(dto.roomId, equals('r_a'));
      expect(dto.session.callId, equals('c2'));
    });
  });
}
