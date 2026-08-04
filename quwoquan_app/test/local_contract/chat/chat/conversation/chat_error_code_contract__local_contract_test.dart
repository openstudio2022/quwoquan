import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/chat/generated/chat_errors.g.dart';

/// L1a 契约测试：ChatErrorCode — 覆盖 errors.yaml 中的稳定错误码
///
/// 三维度覆盖：
///   常规契约  — 每个已知错误码正确解析，错误码解析与状态码正确
///   解析边界   — 未登记 code → unknown；稳定 code 集合与 metadata 对齐
///   异常/边界契约 — 空字符串/null-like 输入不崩溃
void main() {
  // ──────────────────────────────────────────────────────────────────
  // 常规契约
  // ──────────────────────────────────────────────────────────────────
  group('ChatErrorCode — 常规契约', () {
    test('parse conversation_not_found → conversationNotFound', () {
      final code = ChatErrorCode.fromCode('CHAT.USER.conversation_not_found');
      expect(code, ChatErrorCode.conversationNotFound);
      expect(code.httpStatus, 404);
    });

    test('parse unauthorized → unauthorized', () {
      final code = ChatErrorCode.fromCode('CHAT.USER.unauthorized');
      expect(code, ChatErrorCode.unauthorized);
      expect(code.httpStatus, 401);
    });

    test('parse message_too_long → messageTooLong', () {
      final code = ChatErrorCode.fromCode('CHAT.USER.message_too_long');
      expect(code, ChatErrorCode.messageTooLong);
      expect(code.httpStatus, 400);
    });

    test('parse message_idempotency_conflict → messageIdempotencyConflict', () {
      final code = ChatErrorCode.fromCode(
        'CHAT.USER.message_idempotency_conflict',
      );
      expect(code, ChatErrorCode.messageIdempotencyConflict);
      expect(code.httpStatus, 409);
    });

    test('service-local rate_limited 已退役并 fail-closed 为 unknown', () {
      final code = ChatErrorCode.fromCode('CHAT.USER.rate_limited');
      expect(code, ChatErrorCode.unknown);
    });

    test('parse not_mutual → notMutual', () {
      final code = ChatErrorCode.fromCode('CHAT.USER.not_mutual');
      expect(code, ChatErrorCode.notMutual);
      expect(code.httpStatus, 403);
    });

    test('parse greeting_required → greetingRequired', () {
      final code = ChatErrorCode.fromCode('CHAT.USER.greeting_required');
      expect(code, ChatErrorCode.greetingRequired);
      expect(code.httpStatus, 403);
    });

    test('parse blocked → blocked', () {
      final code = ChatErrorCode.fromCode('CHAT.USER.blocked');
      expect(code, ChatErrorCode.blocked);
      expect(code.httpStatus, 403);
    });

    test('parse internal_error → internalError', () {
      final code = ChatErrorCode.fromCode('CHAT.SYSTEM.internal_error');
      expect(code, ChatErrorCode.internalError);
      expect(code.httpStatus, 500);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 解析边界
  // ──────────────────────────────────────────────────────────────────
  group('ChatErrorCode — 解析边界', () {
    test('unknown code string → ChatErrorCode.unknown', () {
      final code = ChatErrorCode.fromCode('CHAT.USER.nonexistent_error');
      expect(code, ChatErrorCode.unknown);
    });

    test('other domain code → ChatErrorCode.unknown', () {
      final code = ChatErrorCode.fromCode('CONTENT.USER.post_not_found');
      expect(code, ChatErrorCode.unknown);
    });

    test('生成的稳定 code 唯一、非空且包含消息校验语义', () {
      final stable = ChatErrorCode.values
          .where((value) => value != ChatErrorCode.unknown)
          .toList(growable: false);
      final codes = stable.map((value) => value.code).toList(growable: false);

      expect(codes, everyElement(isNotEmpty));
      expect(codes.toSet(), hasLength(codes.length));
      expect(ChatErrorCode.messageInvalid.httpStatus, 400);
    });

    test('每个 code 可以 round-trip：fromCode(code) == self', () {
      for (final value in ChatErrorCode.values) {
        if (value == ChatErrorCode.unknown) continue;
        final parsed = ChatErrorCode.fromCode(value.code);
        expect(parsed, value, reason: 'round-trip failed for ${value.code}');
      }
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 异常/边界契约
  // ──────────────────────────────────────────────────────────────────
  group('ChatErrorCode — 异常/边界契约', () {
    test('空字符串 → unknown', () {
      expect(ChatErrorCode.fromCode(''), ChatErrorCode.unknown);
    });

    test('只有模块名 → unknown', () {
      expect(ChatErrorCode.fromCode('CHAT'), ChatErrorCode.unknown);
    });

    test('乱码字符串 → unknown', () {
      expect(ChatErrorCode.fromCode('abc.def.ghi'), ChatErrorCode.unknown);
    });

    test('defaultMessage 中文非空', () {
      expect(ChatErrorCode.notMutual.defaultMessage, contains('互相关注'));
      expect(ChatErrorCode.greetingRequired.defaultMessage, contains('打招呼'));
      expect(ChatErrorCode.blocked.defaultMessage, contains('不能继续发送消息'));
    });
  });
}
