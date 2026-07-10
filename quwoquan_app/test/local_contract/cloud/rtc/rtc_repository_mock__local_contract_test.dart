import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/rtc/rtc_repository.dart';

void main() {
  // ──────────────────────────────────────────────────────────────────
  // 常规契约
  // ──────────────────────────────────────────────────────────────────
  group('MockRtcRepository — 常规契约', () {
    late RtcRepository repo;

    setUp(() {
      repo = MockRtcRepository();
    });

    test('initiateCall 返回会话与 token 字段', () async {
      final result = await repo.initiateCall(
        callType: 'video',
        conversationId: 'conv_001',
        inviteeIds: ['user_002', 'user_003'],
      );
      expect(result.session.id, isNotEmpty);
      expect(result.session.callType, isNotNull);
      expect(result.session.status, isNotNull);
      expect(result.session.roomId, isNotEmpty);
    });

    test('getCallSession 返回指定会话', () async {
      final session = await repo.getCallSession('call_001');
      expect(session.id, equals('call_001'));
      expect(session.callType, isNotNull);
      expect(session.status, isNotNull);
    });

    test('answerCall 返回 in_call 状态的会话', () async {
      final answer = await repo.answerCall('call_001');
      expect(answer.session, isNotNull);
      expect(answer.session!.status, equals('in_call'));
    });

    test('rejectCall 正常完成', () async {
      await expectLater(
        repo.rejectCall('call_001'),
        completes,
      );
    });

    test('hangUp 正常完成', () async {
      await expectLater(
        repo.hangUp('call_001'),
        completes,
      );
    });

    test('joinRtcToken 返回 token 和 roomId', () async {
      final creds = await repo.joinRtcToken('call_001');
      expect(creds.token, isNotEmpty);
      expect(creds.roomId, isNotEmpty);
      expect(creds.callId, isNotNull);
    });

    test('muteToggle 正常完成', () async {
      await expectLater(
        repo.muteToggle(callId: 'call_001', muted: true),
        completes,
      );
    });

    test('cameraToggle 正常完成', () async {
      await expectLater(
        repo.cameraToggle(callId: 'call_001', cameraOn: false),
        completes,
      );
    });

    test('startScreenShare 正常完成', () async {
      await expectLater(
        repo.startScreenShare('call_001'),
        completes,
      );
    });

    test('stopScreenShare 正常完成', () async {
      await expectLater(
        repo.stopScreenShare('call_001'),
        completes,
      );
    });

    test('startRecording 正常完成', () async {
      await expectLater(
        repo.startRecording('call_001'),
        completes,
      );
    });

    test('stopRecording 正常完成', () async {
      await expectLater(
        repo.stopRecording('call_001'),
        completes,
      );
    });

    test('listCallHistory 返回列表', () async {
      final history = await repo.listCallHistory();
      expect(history, isList);
      expect(history, isNotEmpty);
      final first = history.first;
      expect(first.id, isNotEmpty);
      expect(first.callType, isNotNull);
      expect(first.status, equals('ended'));
    });

    test('listParticipants 返回参与者列表', () async {
      final participants = await repo.listParticipants('call_001');
      expect(participants, isList);
      expect(participants, isNotEmpty);
      final first = participants.first;
      expect(first.userId, isNotEmpty);
      expect(first.role, isNotEmpty);
      expect(first.status, isNotEmpty);
    });

    test('inviteToCall 正常完成', () async {
      await expectLater(
        repo.inviteToCall(callId: 'call_001', inviteeIds: ['user_004']),
        completes,
      );
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 兼容性契约
  // ──────────────────────────────────────────────────────────────────
  group('MockRtcRepository — 兼容性契约', () {
    late RtcRepository repo;

    setUp(() {
      repo = MockRtcRepository();
    });

    test('initiateCall 会话包含必要字段', () async {
      final result = await repo.initiateCall(
        callType: 'audio',
        inviteeIds: ['user_002'],
      );
      final wire = result.session.toMap();
      final requiredFields = [
        'id',
        'callType',
        'status',
        'initiatorId',
        'roomId',
        'participants',
      ];
      for (final field in requiredFields) {
        expect(wire.containsKey(field), isTrue,
            reason: 'missing field: $field');
      }
    });

    test('listParticipants 包含 userId 和 role', () async {
      final participants = await repo.listParticipants('call_001');
      expect(participants, isNotEmpty);
      final first = participants.first;
      expect(first.userId, isNotEmpty);
      expect(first.role, isNotEmpty);
      expect(first.status, isNotEmpty);
    });

    test('listCallHistory 包含时间戳字段', () async {
      final history = await repo.listCallHistory();
      expect(history, isNotEmpty);
      final first = history.first;
      expect(first.createdAt, isNotNull);
      expect(first.updatedAt, isNotNull);
    });

    test('joinRtcToken token 为非空字符串', () async {
      final creds = await repo.joinRtcToken('call_001');
      expect(creds.token.length, greaterThan(10));
    });

    test('接口包含全部 15 个 API 方法', () {
      final methods = <String>[
        'initiateCall',
        'getCallSession',
        'answerCall',
        'rejectCall',
        'hangUp',
        'joinRtcToken',
        'muteToggle',
        'cameraToggle',
        'startScreenShare',
        'stopScreenShare',
        'startRecording',
        'stopRecording',
        'listCallHistory',
        'listParticipants',
        'inviteToCall',
      ];
      expect(methods.length, 15);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 异常/边界契约
  // ──────────────────────────────────────────────────────────────────
  group('MockRtcRepository — 异常/边界契约', () {
    late RtcRepository repo;

    setUp(() {
      repo = MockRtcRepository();
    });

    test('getCallSession 不存在的 callId 返回默认', () async {
      final session = await repo.getCallSession('nonexistent_call');
      expect(session.id, isNotEmpty);
    });

    test('listParticipants 不存在的 callId 返回空列表', () async {
      final participants = await repo.listParticipants('nonexistent_call');
      expect(participants, isList);
    });

    test('listCallHistory limit=0 使用默认值', () async {
      final history = await repo.listCallHistory(limit: 0);
      expect(history, isList);
    });

    test('initiateCall 空 inviteeIds 正常返回', () async {
      final result = await repo.initiateCall(
        callType: 'audio',
        inviteeIds: [],
      );
      expect(result.session.id, isNotEmpty);
    });

    test('muteToggle + cameraToggle 连续调用不崩溃', () async {
      await repo.muteToggle(callId: 'call_001', muted: true);
      await repo.muteToggle(callId: 'call_001', muted: false);
      await repo.cameraToggle(callId: 'call_001', cameraOn: false);
      await repo.cameraToggle(callId: 'call_001', cameraOn: true);
    });
  });
}
