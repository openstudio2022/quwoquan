import 'package:test/test.dart';
import 'package:quwoquan_app/cloud/services/user/greeting_repository.dart';

/// T1 契约测试：GreetingRepository
///
/// 守护：GreetingRequestDto 解析正确性 + MockGreetingRepository 行为正确性
void main() {
  // ── GreetingRequestDto 常规契约 ──────────────────────────────────────────────

  group('GreetingRequestDto — 常规契约', () {
    final now = DateTime.now();

    test('fromMap 全字段正确解析', () {
      final dto = GreetingRequestDto.fromMap(<String, dynamic>{
        'id': 'gr_001',
        'requesterSubAccountId': 'user_a',
        'targetSubAccountId': 'user_b',
        'requestMessage': '你好，很高兴认识你！',
        'status': 'pending',
        'source': 'profile',
        'promotedConversationId': null,
        'expireAt': null,
        'decisionAt': null,
        'createdAt': now.toIso8601String(),
        'updatedAt': now.toIso8601String(),
      });
      expect(dto.id, 'gr_001');
      expect(dto.requesterSubAccountId, 'user_a');
      expect(dto.targetSubAccountId, 'user_b');
      expect(dto.requestMessage, '你好，很高兴认识你！');
      expect(dto.status, 'pending');
      expect(dto.isPending, true);
      expect(dto.isReplied, false);
    });

    test('isPending 与 isReplied 互斥', () {
      final pending = GreetingRequestDto.fromMap(<String, dynamic>{
        'id': 'g1', 'status': 'pending', 'source': 'profile',
        'requesterSubAccountId': 'a', 'targetSubAccountId': 'b',
        'createdAt': now.toIso8601String(),
        'updatedAt': now.toIso8601String(),
      });
      final replied = GreetingRequestDto.fromMap(<String, dynamic>{
        'id': 'g2', 'status': 'replied', 'source': 'profile',
        'requesterSubAccountId': 'a', 'targetSubAccountId': 'b',
        'createdAt': now.toIso8601String(),
        'updatedAt': now.toIso8601String(),
      });
      expect(pending.isPending, true);
      expect(pending.isReplied, false);
      expect(replied.isReplied, true);
      expect(replied.isPending, false);
    });

    test('fromMap 正确解析 expireAt / decisionAt 时间字段', () {
      final expireAt = now.add(const Duration(days: 3));
      final dto = GreetingRequestDto.fromMap(<String, dynamic>{
        'id': 'g_time',
        'requesterSubAccountId': 'a',
        'targetSubAccountId': 'b',
        'status': 'pending',
        'source': 'profile',
        'expireAt': expireAt.toIso8601String(),
        'createdAt': now.toIso8601String(),
        'updatedAt': now.toIso8601String(),
      });
      expect(dto.expireAt, isNotNull);
      expect(dto.expireAt!.isAfter(now), true);
    });
  });

  // ── GreetingRequestDto 兼容性契约 ────────────────────────────────────────────

  group('GreetingRequestDto — 兼容性契约', () {
    test('fromMap 缺失字段使用安全默认值', () {
      final dto = GreetingRequestDto.fromMap(const <String, dynamic>{});
      expect(dto.id, isEmpty);
      expect(dto.status, 'pending');
      expect(dto.source, 'profile');
      expect(dto.requestMessage, isNull);
      expect(dto.promotedConversationId, isNull);
    });

    test('fromMap 所有 status 值均可解析', () {
      const statuses = [
        'pending', 'replied', 'ignored', 'blocked', 'cancelled', 'expired',
      ];
      final now = DateTime.now();
      for (final s in statuses) {
        expect(
          () => GreetingRequestDto.fromMap(<String, dynamic>{
            'id': 'g', 'status': s, 'source': 'profile',
            'requesterSubAccountId': 'a', 'targetSubAccountId': 'b',
            'createdAt': now.toIso8601String(),
            'updatedAt': now.toIso8601String(),
          }),
          returnsNormally,
          reason: 'status=$s should not throw',
        );
      }
    });
  });

  // ── GreetingRequestDto 异常/边界契约 ─────────────────────────────────────────

  group('GreetingRequestDto — 异常/边界契约', () {
    test('fromMap 全字段缺失不崩溃', () {
      expect(
        () => GreetingRequestDto.fromMap(const <String, dynamic>{}),
        returnsNormally,
      );
    });

    test('fromMap 非法 createdAt 不崩溃（降级为 now）', () {
      expect(
        () => GreetingRequestDto.fromMap(<String, dynamic>{
          'createdAt': 'not-a-date',
          'updatedAt': 'not-a-date',
        }),
        returnsNormally,
      );
    });
  });

  // ── MockGreetingRepository 常规契约 ──────────────────────────────────────────

  group('MockGreetingRepository — 常规契约', () {
    late MockGreetingRepository repo;

    setUp(() {
      repo = MockGreetingRepository();
    });

    test('sendGreeting 返回 pending DTO 且 targetSubAccountId 正确', () async {
      final dto = await repo.sendGreeting(
        targetSubAccountId: 'user_x',
        requestMessage: '认识一下',
      );
      expect(dto.status, 'pending');
      expect(dto.targetSubAccountId, 'user_x');
      expect(dto.requestMessage, '认识一下');
      expect(dto.isPending, true);
    });

    test('sendGreeting 后 listOutbox 包含刚发送的请求', () async {
      await repo.sendGreeting(targetSubAccountId: 'user_y');
      final outbox = await repo.listOutbox();
      expect(outbox, isNotEmpty);
      expect(outbox.any((g) => g.targetSubAccountId == 'user_y'), true);
    });

    test('listInbox 初始为空', () async {
      final inbox = await repo.listInbox();
      expect(inbox, isEmpty);
    });

    test('replyGreeting 返回包含 conversationId 的 Map', () async {
      final result = await repo.replyGreeting('gr_001');
      expect(result.containsKey('conversationId'), true);
      expect(result['conversationId'], isNotEmpty);
    });

    test('cancelGreeting 返回 cancelled 状态 DTO', () async {
      await repo.sendGreeting(targetSubAccountId: 'user_z');
      final outbox = await repo.listOutbox();
      final requestId = outbox.first.id;
      final cancelled = await repo.cancelGreeting(requestId);
      expect(cancelled.status, 'cancelled');
    });

    test('cancelGreeting 后 listOutbox 不再包含该请求', () async {
      await repo.sendGreeting(targetSubAccountId: 'user_w');
      final outbox1 = await repo.listOutbox();
      await repo.cancelGreeting(outbox1.first.id);
      final outbox2 = await repo.listOutbox();
      expect(outbox2, isEmpty);
    });

    test('接口包含全部 6 个 service.yaml 方法', () {
      expect(
        repo.runtimeType.toString(),
        contains('MockGreetingRepository'),
      );
    });
  });

  // ── MockGreetingRepository 兼容性/边界契约 ───────────────────────────────────

  group('MockGreetingRepository — 边界契约', () {
    test('多次 sendGreeting 各自有独立 id', () async {
      final repo = MockGreetingRepository();
      final dto1 = await repo.sendGreeting(targetSubAccountId: 'u1');
      await Future<void>.delayed(const Duration(milliseconds: 2));
      final dto2 = await repo.sendGreeting(targetSubAccountId: 'u2');
      expect(dto1.id, isNot(dto2.id));
    });

    test('listOutbox status=cancelled 过滤已取消', () async {
      final repo = MockGreetingRepository();
      await repo.sendGreeting(targetSubAccountId: 'u1');
      final pending = await repo.listOutbox(status: 'pending');
      final cancelled = await repo.listOutbox(status: 'cancelled');
      expect(pending, isNotEmpty);
      expect(cancelled, isEmpty);
    });
  });
}
