import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';

/// 契约测试：ContentErrorCode — 覆盖 mock.yaml error_scenarios
///
/// 每个测试名与 mock.yaml scenario name 对应，确保 codegen 与 metadata 一致。
void main() {
  group('ContentErrorCode.fromCode — error_scenarios contract', () {
    test('parse_post_not_found → postNotFound, not retryable', () {
      final code = ContentErrorCode.fromCode('CONTENT.USER.post_not_found');
      expect(code, ContentErrorCode.postNotFound);
      expect(code.isRetryable, isFalse);
    });

    test('parse_comment_not_found → commentNotFound, not retryable', () {
      final code = ContentErrorCode.fromCode('CONTENT.USER.comment_not_found');
      expect(code, ContentErrorCode.commentNotFound);
      expect(code.isRetryable, isFalse);
    });

    test('parse_forbidden_edit → forbiddenEdit, not retryable', () {
      final code = ContentErrorCode.fromCode('CONTENT.USER.forbidden_edit');
      expect(code, ContentErrorCode.forbiddenEdit);
      expect(code.isRetryable, isFalse);
    });

    test('parse_forbidden_delete → forbiddenDelete, not retryable', () {
      final code = ContentErrorCode.fromCode('CONTENT.USER.forbidden_delete');
      expect(code, ContentErrorCode.forbiddenDelete);
      expect(code.isRetryable, isFalse);
    });

    test('parse_unauthorized → unauthorized, not retryable', () {
      final code = ContentErrorCode.fromCode('CONTENT.USER.unauthorized');
      expect(code, ContentErrorCode.unauthorized);
      expect(code.isRetryable, isFalse);
    });

    test('parse_invalid_argument → invalidArgument, not retryable', () {
      final code = ContentErrorCode.fromCode('CONTENT.USER.invalid_argument');
      expect(code, ContentErrorCode.invalidArgument);
      expect(code.isRetryable, isFalse);
    });

    test('parse_invalid_content_type → invalidContentType, not retryable', () {
      final code = ContentErrorCode.fromCode('CONTENT.USER.invalid_content_type');
      expect(code, ContentErrorCode.invalidContentType);
      expect(code.isRetryable, isFalse);
    });

    test('parse_rate_limited → rateLimited, IS retryable', () {
      final code = ContentErrorCode.fromCode('CONTENT.USER.rate_limited');
      expect(code, ContentErrorCode.rateLimited);
      expect(code.isRetryable, isTrue);
    });

    test('parse_content_too_long → contentTooLong, not retryable', () {
      final code = ContentErrorCode.fromCode('CONTENT.USER.content_too_long');
      expect(code, ContentErrorCode.contentTooLong);
      expect(code.isRetryable, isFalse);
    });

    test('parse_media_not_ready → mediaNotReady, IS retryable', () {
      final code = ContentErrorCode.fromCode('CONTENT.USER.media_not_ready');
      expect(code, ContentErrorCode.mediaNotReady);
      expect(code.isRetryable, isTrue);
    });

    test('parse_storage_write_failed → storageWriteFailed, IS retryable', () {
      final code = ContentErrorCode.fromCode('CONTENT.SYSTEM.storage_write_failed');
      expect(code, ContentErrorCode.storageWriteFailed);
      expect(code.isRetryable, isTrue);
    });

    test('parse_internal_error → internalError, not retryable', () {
      final code = ContentErrorCode.fromCode('CONTENT.SYSTEM.internal_error');
      expect(code, ContentErrorCode.internalError);
      expect(code.isRetryable, isFalse);
    });

    test('parse_upstream_timeout → upstreamTimeout, IS retryable', () {
      final code = ContentErrorCode.fromCode('CONTENT.MIDDLEWARE.upstream_timeout');
      expect(code, ContentErrorCode.upstreamTimeout);
      expect(code.isRetryable, isTrue);
    });

    test('fallback_unknown_code → unknown, not retryable', () {
      final code = ContentErrorCode.fromCode('UNKNOWN.UNKNOWN.random');
      expect(code, ContentErrorCode.unknown);
      expect(code.isRetryable, isFalse);
    });

    test('all 13 error codes have distinct enum values', () {
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
      expect(enums.length, equals(13),
          reason: 'Each error code must map to a distinct enum value');
    });

    test('localized zh messages are set for known error codes', () {
      expect(
        ContentErrorMessages.zh[ContentErrorCode.postNotFound],
        isNotNull,
      );
      expect(
        ContentErrorMessages.zh[ContentErrorCode.rateLimited],
        isNotNull,
      );
      expect(
        ContentErrorMessages.zh[ContentErrorCode.upstreamTimeout],
        isNotNull,
      );
    });
  });
}
