import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';

/// L1a 契约测试：ContentErrorCode — 覆盖 mock.yaml error_scenarios
///
/// 三维度覆盖：
///   常规契约  — 每个已知错误码正确解析，错误码解析与状态码正确
///   演进契约 — 未知 code 字符串 → unknown 降级；全部生成 enum 可回环
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

    test('parse_interaction_type_invalid → interactionTypeInvalid', () {
      final code = ContentErrorCode.fromCode(
        'CONTENT.USER.interaction_type_invalid',
      );
      expect(code, ContentErrorCode.interactionTypeInvalid);
    });

    test('parse_interaction_cursor_invalid → interactionCursorInvalid', () {
      final code = ContentErrorCode.fromCode(
        'CONTENT.USER.interaction_cursor_invalid',
      );
      expect(code, ContentErrorCode.interactionCursorInvalid);
    });

    test('parse_interaction_owner_forbidden → interactionOwnerForbidden', () {
      final code = ContentErrorCode.fromCode(
        'CONTENT.USER.interaction_owner_forbidden',
      );
      expect(code, ContentErrorCode.interactionOwnerForbidden);
    });

    test(
      'parse_interaction_read_model_unavailable → interactionReadModelUnavailable',
      () {
        final code = ContentErrorCode.fromCode(
          'CONTENT.SYSTEM.interaction_read_model_unavailable',
        );
        expect(code, ContentErrorCode.interactionReadModelUnavailable);
      },
    );

    test('parse_publication_rejected → publicationRejected', () {
      final code = ContentErrorCode.fromCode(
        'CONTENT.USER.publication_rejected',
      );
      expect(code, ContentErrorCode.publicationRejected);
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

    test('parse_media_file_too_large → mediaFileTooLarge', () {
      final code = ContentErrorCode.fromCode(
        'CONTENT.USER.media_file_too_large',
      );
      expect(code, ContentErrorCode.mediaFileTooLarge);
    });

    test('parse_media_type_unsupported → mediaTypeUnsupported', () {
      final code = ContentErrorCode.fromCode(
        'CONTENT.USER.media_type_unsupported',
      );
      expect(code, ContentErrorCode.mediaTypeUnsupported);
    });

    test('parse_storage_write_failed → storageWriteFailed', () {
      final code = ContentErrorCode.fromCode(
        'CONTENT.SYSTEM.storage_write_failed',
      );
      expect(code, ContentErrorCode.storageWriteFailed);
    });

    test('parse_storage_read_failed → storageReadFailed', () {
      final code = ContentErrorCode.fromCode(
        'CONTENT.SYSTEM.storage_read_failed',
      );
      expect(code, ContentErrorCode.storageReadFailed);
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
        ContentErrorMessages.zh[ContentErrorCode.mediaFileTooLarge],
        isNotNull,
      );
      expect(
        ContentErrorMessages.zh[ContentErrorCode.mediaTypeUnsupported],
        isNotNull,
      );
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
      'CONTENT.USER.interaction_type_invalid': 400,
      'CONTENT.USER.interaction_cursor_invalid': 400,
      'CONTENT.USER.interaction_owner_forbidden': 403,
      'CONTENT.SYSTEM.interaction_read_model_unavailable': 503,
      'CONTENT.USER.publication_rejected': 422,
      'CONTENT.USER.invalid_content_type': 400,
      'CONTENT.USER.rate_limited': 429,
      'CONTENT.USER.content_too_long': 400,
      'CONTENT.USER.media_not_ready': 400,
      'CONTENT.USER.media_file_too_large': 413,
      'CONTENT.USER.media_type_unsupported': 415,
      'CONTENT.SYSTEM.storage_write_failed': 500,
      'CONTENT.SYSTEM.storage_read_failed': 500,
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
        'CONTENT.USER.interaction_type_invalid': 400,
        'CONTENT.USER.interaction_cursor_invalid': 400,
        'CONTENT.USER.interaction_owner_forbidden': 403,
        'CONTENT.USER.publication_rejected': 422,
        'CONTENT.USER.invalid_content_type': 400,
        'CONTENT.USER.rate_limited': 429,
        'CONTENT.USER.content_too_long': 400,
        'CONTENT.USER.media_not_ready': 400,
        'CONTENT.USER.media_file_too_large': 413,
        'CONTENT.USER.media_type_unsupported': 415,
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
        'CONTENT.SYSTEM.storage_read_failed': 500,
        'CONTENT.SYSTEM.internal_error': 500,
        'CONTENT.SYSTEM.interaction_read_model_unavailable': 503,
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
  });

  // ──────────────────────────────────────────────────────────────────
  // 演进契约：未知 code → unknown 降级；enum 与字符串映射完整
  // ──────────────────────────────────────────────────────────────────
  group('ContentErrorCode — 单轨契约', () {
    test('fallback_unknown_code → unknown', () {
      final code = ContentErrorCode.fromCode('UNKNOWN.UNKNOWN.random');
      expect(code, ContentErrorCode.unknown);
    });

    test(
      'every generated named error code round-trips through its stable code',
      () {
        final namedCodes = ContentErrorCode.values.where(
          (errorCode) => errorCode != ContentErrorCode.unknown,
        );
        for (final errorCode in namedCodes) {
          expect(
            errorCode.code,
            isNotEmpty,
            reason: '$errorCode must expose a code',
          );
          expect(
            ContentErrorCode.fromCode(errorCode.code),
            errorCode,
            reason: '$errorCode must round-trip through its stable code',
          );
        }
      },
    );
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
