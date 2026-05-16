// Mock 通话 DTO 与 `quwoquan_service/contracts/metadata/rtc/call_session/fields.yaml`
// 及 Go `model.CallSession` 的 JSON 形状一致；改字段时请同步 metadata / 服务端 model。
import 'package:quwoquan_app/cloud/rtc/models/call_session_dto.dart';
import 'package:quwoquan_app/cloud/rtc/models/rtc_repository_result_dtos.dart';

/// 典型会话列表（强类型；需要 Map 时可用 [CallSessionDto.toMap]）。
final List<CallSessionDto> kMockCallSessions = [
  CallSessionDto.fromMap(<String, dynamic>{
    '_id': 'call_001',
    'callType': 'video',
    'status': 'in_call',
    'initiatorId': 'user_001',
    'initiatorRingtoneId': 'default_ringtone',
    'conversationId': 'conv_001',
    'roomId': 'room_abc123',
    'maxParticipants': 32,
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
        'isCameraOn': true,
        'joinedAt': '2026-03-07T10:00:05Z',
      },
      {
        'userId': 'user_003',
        'role': 'invitee',
        'status': 'connected',
        'isMuted': false,
        'isCameraOn': false,
        'joinedAt': '2026-03-07T10:00:10Z',
      },
    ],
    'isRecording': false,
    'isScreenSharing': false,
    'createdAt': '2026-03-07T09:59:50Z',
    'updatedAt': '2026-03-07T10:00:10Z',
    'startedAt': '2026-03-07T10:00:00Z',
  }),
  CallSessionDto.fromMap(<String, dynamic>{
    '_id': 'call_002',
    'callType': 'audio',
    'status': 'ended',
    'initiatorId': 'user_002',
    'conversationId': 'conv_002',
    'roomId': 'room_def456',
    'maxParticipants': 2,
    'participantCount': 2,
    'participants': [
      {
        'userId': 'user_002',
        'role': 'initiator',
        'status': 'left',
        'isMuted': false,
        'isCameraOn': false,
        'joinedAt': '2026-03-07T08:00:00Z',
        'leftAt': '2026-03-07T08:15:30Z',
      },
      {
        'userId': 'user_001',
        'role': 'invitee',
        'status': 'left',
        'isMuted': false,
        'isCameraOn': false,
        'joinedAt': '2026-03-07T08:00:03Z',
        'leftAt': '2026-03-07T08:15:30Z',
      },
    ],
    'isRecording': false,
    'isScreenSharing': false,
    'endReason': 'normal',
    'durationMs': 930000,
    'createdAt': '2026-03-07T07:59:55Z',
    'updatedAt': '2026-03-07T08:15:30Z',
    'startedAt': '2026-03-07T08:00:00Z',
    'endedAt': '2026-03-07T08:15:30Z',
  }),
  CallSessionDto.fromMap(<String, dynamic>{
    '_id': 'call_003',
    'callType': 'video',
    'status': 'ringing',
    'initiatorId': 'user_001',
    'circleId': 'circle_001',
    'roomId': 'room_ghi789',
    'maxParticipants': 8,
    'participantCount': 1,
    'participants': [
      {
        'userId': 'user_001',
        'role': 'initiator',
        'status': 'connected',
        'isMuted': false,
        'isCameraOn': true,
        'joinedAt': '2026-03-07T14:30:00Z',
      },
    ],
    'isRecording': false,
    'isScreenSharing': false,
    'createdAt': '2026-03-07T14:29:55Z',
    'updatedAt': '2026-03-07T14:30:00Z',
    'startedAt': '2026-03-07T14:30:00Z',
  }),
];

final RtcJoinCredentialsDto
kMockRtcJoinCredentials = RtcJoinCredentialsDto.fromMap(<String, dynamic>{
  'token':
      'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyXzAwMSIsInJvb20iOiJyb29tX2FiYzEyMyJ9.mock_signature',
  'roomId': 'room_abc123',
  'callId': 'call_001',
});

final List<CallSessionDto> kMockCallHistory = [
  CallSessionDto.fromMap(<String, dynamic>{
    '_id': 'call_002',
    'callType': 'audio',
    'status': 'ended',
    'initiatorId': 'user_002',
    'conversationId': 'conv_002',
    'roomId': 'room_def456',
    'maxParticipants': 2,
    'participantCount': 2,
    'endReason': 'normal',
    'durationMs': 930000,
    'createdAt': '2026-03-07T07:59:55Z',
    'startedAt': '2026-03-07T08:00:00Z',
    'endedAt': '2026-03-07T08:15:30Z',
    'updatedAt': '2026-03-07T08:15:30Z',
  }),
];
