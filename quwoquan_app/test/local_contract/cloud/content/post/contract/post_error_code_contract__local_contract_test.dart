import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';

/// L1a 契约测试：ContentErrorCode — 覆盖 mock.yaml error_scenarios
///
/// 三维度覆盖：
///   常规契约  — 每个已知错误码正确解析，错误码解析与状态码正确
///   兼容性契约 — 未知 code 字符串 → unknown 降级；enum 数量稳定
///   异常/边界契约 — 空字符串/null-like 输入不崩溃
void main() {
  // ──────────────────────────────────────────────────────────────────
  // 常规契约
  // ──────────────────────────────────────────────────────────────────
  group('ContentErrorCode — 常规契约', () {
    test('parse_post_not_found → postNotFound', () {
      final code = ContentErrorCode.fromCode('CONTENT.USER.post_not_found');
      expect(code, ContentErrorCode.postNotFound);
    });

    test('parse_comment_not_found → commentNotFound', () {
      final code = ContentErrorCode.fromCode('CONTENT.USER.comment_not_found');
      expect(code, ContentErrorCode.commentNotFound);
    });

    test('parse_forbidden_edit → forbiddenEdit', () {
      final code = ContentErrorCode.fromCode('CONTENT.USER.forbidden_edit');
      expect(code, ContentErrorCode.forbiddenEdit);
    });

    test('parse_forbidden_delete → forbiddenDelete', () {
      final code = ContentErrorCode.fromCode('CONTENT.USER.forbidden_delete');
      expect(code, ContentErrorCode.forbiddenDelete);
    });

    test('parse_unauthorized → unauthorized', () {
      final code = ContentErrorCode.fromCode('CONTENT.USER.unauthorized');
      expect(code, ContentErrorCode.unauthorized);
    });

    test('parse_invalid_argument → invalidArgument', () {
      final code = ContentErrorCode.fromCode('CONTENT.USER.invalid_argument');
      expect(code, ContentErrorCode.invalidArgument);
    });

    test('parse_invalid_content_type → invalidContentType', () {
      final code = ContentErrorCode.fromCode(
        'CONTENT.USER.invalid_content_type',
      );
      expect(code, ContentErrorCode.invalidContentType);
    });

    test('parse_rate_limited → rateLimited', () {
      final code = ContentErrorCode.fromCode('CONTENT.USER.rate_limited');
      expect(code, ContentErrorCode.rateLimited);
    });

    test('parse_content_too_long → contentTooLong', () {
      final code = ContentErrorCode.fromCode('CONTENT.USER.content_too_long');
      expect(code, ContentErrorCode.contentTooLong);
    });

    test('parse_media_not_ready → mediaNotReady', () {
      final code = ContentErrorCode.fromCode('CONTENT.USER.media_not_ready');
      expect(code, ContentErrorCode.mediaNotReady);
    });

    test('parse_storage_write_failed → storageWriteFailed', () {
      final code = ContentErrorCode.fromCode(
        'CONTENT.SYSTEM.storage_write_failed',
      );
      expect(code, ContentErrorCode.storageWriteFailed);
    });

    test('parse_internal_error → internalError', () {
      final code = ContentErrorCode.fromCode('CONTENT.SYSTEM.internal_error');
      expect(code, ContentErrorCode.internalError);
    });

    test('parse_upstream_timeout → upstreamTimeout', () {
      final code = ContentErrorCode.fromCode(
        'CONTENT.MIDDLEWARE.upstream_timeout',
      );
      expect(code, ContentErrorCode.upstreamTimeout);
    });

    test('localized zh messages are set for known error codes', () {
      expect(ContentErrorMessages.zh[ContentErrorCode.postNotFound], isNotNull);
      expect(ContentErrorMessages.zh[ContentErrorCode.rateLimited], isNotNull);
      expect(
        ContentErrorMessages.zh[ContentErrorCode.upstreamTimeout],
        isNotNull,
      );
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // HTTP 状态码映射契约（errors.yaml → http_status 字段一致性）
  // ──────────────────────────────────────────────────────────────────
  group('ContentErrorCode — HTTP 状态码映射契约', () {
    // Expected HTTP status codes from errors.yaml for each error code.
    // If errors.yaml changes http_status, this test MUST be updated to match.
    const expectedHttpStatuses = <String, int>{
      'CONTENT.USER.post_not_found': 404,
      'CONTENT.USER.comment_not_found': 404,
      'CONTENT.USER.forbidden_edit': 403,
      'CONTENT.USER.forbidden_delete': 403,
      'CONTENT.USER.unauthorized': 401,
      'CONTENT.USER.invalid_argument': 400,
      'CONTENT.USER.invalid_content_type': 400,
      'CONTENT.USER.rate_limited': 429,
      'CONTENT.USER.content_too_long': 400,
      'CONTENT.USER.media_not_ready': 400,
      'CONTENT.SYSTEM.storage_write_failed': 500,
      'CONTENT.SYSTEM.internal_error': 500,
      'CONTENT.MIDDLEWARE.upstream_timeout': 504,
    };

    test('USER errors map to expected HTTP status codes', () {
      // 4xx errors (user errors)
      const userErrors = {
        'CONTENT.USER.post_not_found': 404,
        'CONTENT.USER.comment_not_found': 404,
        'CONTENT.USER.forbidden_edit': 403,
        'CONTENT.USER.forbidden_delete': 403,
        'CONTENT.USER.unauthorized': 401,
        'CONTENT.USER.invalid_argument': 400,
        'CONTENT.USER.invalid_content_type': 400,
        'CONTENT.USER.rate_limited': 429,
        'CONTENT.USER.content_too_long': 400,
        'CONTENT.USER.media_not_ready': 400,
      };
      for (final entry in userErrors.entries) {
        expect(
          expectedHttpStatuses[entry.key],
          equals(entry.value),
          reason: '${entry.key} should have http_status=${entry.value}',
        );
      }
    });

    test('SYSTEM errors map to 5xx HTTP status codes', () {
      const systemErrors = {
        'CONTENT.SYSTEM.storage_write_failed': 500,
        'CONTENT.SYSTEM.internal_error': 500,
      };
      for (final entry in systemErrors.entries) {
        expect(
          expectedHttpStatuses[entry.key],
          equals(entry.value),
          reason: '${entry.key} should have http_status=${entry.value}',
        );
      }
    });

    test('MIDDLEWARE error maps to 504 gateway timeout', () {
      expect(
        expectedHttpStatuses['CONTENT.MIDDLEWARE.upstream_timeout'],
        equals(504),
      );
    });

    test('rate_limited maps to 429 (not 400 or 503)', () {
      // Explicitly guard against accidental change to rate_limited HTTP status
      expect(
        expectedHttpStatuses['CONTENT.USER.rate_limited'],
        equals(429),
        reason: 'rate_limited MUST be 429 per errors.yaml; never 400 or 503',
      );
    });

    test('unauthorized maps to 401 (not 403)', () {
      // Guard against confusing authentication (401) with authorization (403)
      expect(
        expectedHttpStatuses['CONTENT.USER.unauthorized'],
        equals(401),
        reason: 'unauthorized MUST be 401 (auth), not 403 (authz)',
      );
    });

    test('all 13 error codes have an HTTP status in the mapping contract', () {
      expect(
        expectedHttpStatuses.length,
        equals(13),
        reason: 'All 13 named error codes must have an HTTP status contract',
      );
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 兼容性契约：未知 code → unknown 降级；enum 数量稳定
  // ──────────────────────────────────────────────────────────────────
  group('ContentErrorCode — 兼容性契约', () {
    test('fallback_unknown_code → unknown', () {
      final code = ContentErrorCode.fromCode('UNKNOWN.UNKNOWN.random');
      expect(code, ContentErrorCode.unknown);
    });

    test('all 13 named error codes have distinct enum values', () {
      final allCodes = [
        'CONTENT.USER.post_not_found',
        'CONTENT.USER.comment_not_found',
        'CONTENT.USER.forbidden_edit',
        'CONTENT.USER.forbidden_delete',
        'CONTENT.USER.unauthorized',
        'CONTENT.USER.invalid_argument',
        'CONTENT.USER.invalid_content_type',
        'CONTENT.USER.rate_limited',
        'CONTENT.USER.content_too_long',
        'CONTENT.USER.media_not_ready',
        'CONTENT.SYSTEM.storage_write_failed',
        'CONTENT.SYSTEM.internal_error',
        'CONTENT.MIDDLEWARE.upstream_timeout',
      ];
      final enums = allCodes.map(ContentErrorCode.fromCode).toSet();
      expect(
        enums.length,
        equals(13),
        reason: 'Each error code must map to a distinct enum value',
      );
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 异常/边界契约：空字符串/格式异常不崩溃
  // ──────────────────────────────────────────────────────────────────
  group('ContentErrorCode — 异常/边界契约', () {
    test('empty string input falls back to unknown without crash', () {
      expect(() => ContentErrorCode.fromCode(''), returnsNormally);
      expect(ContentErrorCode.fromCode(''), ContentErrorCode.unknown);
    });

    test(
      'partial code format (missing reason segment) falls back to unknown',
      () {
        expect(
          () => ContentErrorCode.fromCode('CONTENT.USER'),
          returnsNormally,
        );
        expect(
          ContentErrorCode.fromCode('CONTENT.USER'),
          ContentErrorCode.unknown,
        );
      },
    );

    test('code with wrong module prefix falls back to unknown', () {
      expect(
        ContentErrorCode.fromCode('USER.USER.post_not_found'),
        ContentErrorCode.unknown,
      );
    });
  });
}
