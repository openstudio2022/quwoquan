import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/rtc/generated/rtc_errors.g.dart';

void main() {
  // ──────────────────────────────────────────────────────────────────
  // 常规契约
  // ──────────────────────────────────────────────────────────────────
  group('RtcErrorCode — 常规契约', () {
    test('parse call_not_found → callNotFound, not retryable', () {
      final code = RtcErrorCode.fromCode('RTC.USER.call_not_found');
      expect(code, RtcErrorCode.callNotFound);
      expect(code!.isRetryable, isFalse);
      expect(code.httpStatus, 404);
    });

    test('parse unauthorized → unauthorized, not retryable', () {
      final code = RtcErrorCode.fromCode('RTC.USER.unauthorized');
      expect(code, RtcErrorCode.unauthorized);
      expect(code!.isRetryable, isFalse);
      expect(code.httpStatus, 401);
    });

    test('parse already_in_call → alreadyInCall, not retryable', () {
      final code = RtcErrorCode.fromCode('RTC.USER.already_in_call');
      expect(code, RtcErrorCode.alreadyInCall);
      expect(code!.isRetryable, isFalse);
      expect(code.httpStatus, 409);
    });

    test('parse call_full → callFull, not retryable', () {
      final code = RtcErrorCode.fromCode('RTC.USER.call_full');
      expect(code, RtcErrorCode.callFull);
      expect(code!.isRetryable, isFalse);
      expect(code.httpStatus, 409);
    });

    test('parse call_ended → callEnded, not retryable', () {
      final code = RtcErrorCode.fromCode('RTC.USER.call_ended');
      expect(code, RtcErrorCode.callEnded);
      expect(code!.isRetryable, isFalse);
      expect(code.httpStatus, 410);
    });

    test('parse not_participant → notParticipant, not retryable', () {
      final code = RtcErrorCode.fromCode('RTC.USER.not_participant');
      expect(code, RtcErrorCode.notParticipant);
      expect(code!.isRetryable, isFalse);
      expect(code.httpStatus, 403);
    });

    test('parse cannot_answer → cannotAnswer, not retryable', () {
      final code = RtcErrorCode.fromCode('RTC.USER.cannot_answer');
      expect(code, RtcErrorCode.cannotAnswer);
      expect(code!.isRetryable, isFalse);
      expect(code.httpStatus, 409);
    });

    test('parse screen_share_conflict → screenShareConflict, not retryable',
        () {
      final code = RtcErrorCode.fromCode('RTC.USER.screen_share_conflict');
      expect(code, RtcErrorCode.screenShareConflict);
      expect(code!.isRetryable, isFalse);
      expect(code.httpStatus, 409);
    });

    test('parse recording_not_allowed → recordingNotAllowed, not retryable',
        () {
      final code = RtcErrorCode.fromCode('RTC.USER.recording_not_allowed');
      expect(code, RtcErrorCode.recordingNotAllowed);
      expect(code!.isRetryable, isFalse);
      expect(code.httpStatus, 403);
    });

    test('parse rate_limited → rateLimited, retryable', () {
      final code = RtcErrorCode.fromCode('RTC.USER.rate_limited');
      expect(code, RtcErrorCode.rateLimited);
      expect(code!.isRetryable, isTrue);
      expect(code.httpStatus, 429);
    });

    test('parse livekit_unavailable → livekitUnavailable, retryable', () {
      final code = RtcErrorCode.fromCode('RTC.SYSTEM.livekit_unavailable');
      expect(code, RtcErrorCode.livekitUnavailable);
      expect(code!.isRetryable, isTrue);
      expect(code.httpStatus, 503);
    });

    test('parse internal_error → internalError, not retryable', () {
      final code = RtcErrorCode.fromCode('RTC.SYSTEM.internal_error');
      expect(code, RtcErrorCode.internalError);
      expect(code!.isRetryable, isFalse);
      expect(code.httpStatus, 500);
    });

    test('parse token_generation_failed → tokenGenerationFailed, retryable',
        () {
      final code =
          RtcErrorCode.fromCode('RTC.SYSTEM.token_generation_failed');
      expect(code, RtcErrorCode.tokenGenerationFailed);
      expect(code!.isRetryable, isTrue);
      expect(code.httpStatus, 500);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 兼容性契约
  // ──────────────────────────────────────────────────────────────────
  group('RtcErrorCode — 兼容性契约', () {
    test('unknown code → null', () {
      final code = RtcErrorCode.fromCode('RTC.USER.nonexistent_error');
      expect(code, isNull);
    });

    test('other domain code → null', () {
      final code = RtcErrorCode.fromCode('CHAT.USER.unauthorized');
      expect(code, isNull);
    });

    test('enum 总数 = 13', () {
      expect(RtcErrorCode.values.length, 13);
    });

    test('每个 code round-trip：fromCode(code) == self', () {
      for (final value in RtcErrorCode.values) {
        final parsed = RtcErrorCode.fromCode(value.code);
        expect(parsed, value, reason: 'round-trip failed for ${value.code}');
      }
    });

    test('isUserError 分类正确', () {
      expect(RtcErrorCode.callNotFound.isUserError, isTrue);
      expect(RtcErrorCode.unauthorized.isUserError, isTrue);
      expect(RtcErrorCode.alreadyInCall.isUserError, isTrue);
      expect(RtcErrorCode.rateLimited.isUserError, isTrue);
      expect(RtcErrorCode.internalError.isUserError, isFalse);
      expect(RtcErrorCode.livekitUnavailable.isUserError, isFalse);
    });

    test('isSystemError 分类正确', () {
      expect(RtcErrorCode.livekitUnavailable.isSystemError, isTrue);
      expect(RtcErrorCode.internalError.isSystemError, isTrue);
      expect(RtcErrorCode.tokenGenerationFailed.isSystemError, isTrue);
      expect(RtcErrorCode.callNotFound.isSystemError, isFalse);
      expect(RtcErrorCode.rateLimited.isSystemError, isFalse);
    });

    test('retryable 仅限 rateLimited + livekitUnavailable + tokenGenerationFailed',
        () {
      final retryable =
          RtcErrorCode.values.where((e) => e.isRetryable).toList();
      expect(retryable.length, 3);
      expect(retryable, contains(RtcErrorCode.rateLimited));
      expect(retryable, contains(RtcErrorCode.livekitUnavailable));
      expect(retryable, contains(RtcErrorCode.tokenGenerationFailed));
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 异常/边界契约
  // ──────────────────────────────────────────────────────────────────
  group('RtcErrorCode — 异常/边界契约', () {
    test('空字符串 → null', () {
      expect(RtcErrorCode.fromCode(''), isNull);
    });

    test('只有模块名 → null', () {
      expect(RtcErrorCode.fromCode('RTC'), isNull);
    });

    test('乱码字符串 → null', () {
      expect(RtcErrorCode.fromCode('abc.def.ghi'), isNull);
    });

    test('每个 code 的 defaultMessage 非空', () {
      for (final value in RtcErrorCode.values) {
        expect(value.defaultMessage, isNotEmpty,
            reason: '${value.name} defaultMessage should not be empty');
      }
    });

    test('每个 code 的 httpStatus 在合理范围', () {
      for (final value in RtcErrorCode.values) {
        expect(value.httpStatus, greaterThanOrEqualTo(400),
            reason: '${value.name} httpStatus should be >= 400');
        expect(value.httpStatus, lessThanOrEqualTo(599),
            reason: '${value.name} httpStatus should be <= 599');
      }
    });
  });
}
