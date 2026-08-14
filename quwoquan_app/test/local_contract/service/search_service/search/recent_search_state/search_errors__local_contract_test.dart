// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-002
//
// SearchErrorCode 解码契约：wire code -> typed 枚举 + HTTP 语义，
// 未知码回退 unknown，锁定端云错误链路的 App 侧映射承诺。
// search 域为单枚举文件，recent_search_state 承载主要错误面，
// hot_query（search_request_fact）的码一并在此锁定。
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/generated/search/search_errors.g.dart';

void main() {
  group('SearchErrorCode 解码契约', () {
    test('hot_query_invalid_argument → searchHotQueryInvalidArgument / 400',
        () {
      final code =
          SearchErrorCode.fromCode('SEARCH.USER.hot_query_invalid_argument');
      expect(code, SearchErrorCode.searchHotQueryInvalidArgument);
      expect(code.httpStatus, 400);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('recent_invalid_argument → searchRecentInvalidArgument / 400', () {
      final code =
          SearchErrorCode.fromCode('SEARCH.USER.recent_invalid_argument');
      expect(code, SearchErrorCode.searchRecentInvalidArgument);
      expect(code.httpStatus, 400);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('recent_version_conflict → recentVersionConflict / 409', () {
      final code =
          SearchErrorCode.fromCode('SEARCH.USER.recent_version_conflict');
      expect(code, SearchErrorCode.recentVersionConflict);
      expect(code.httpStatus, 409);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('recent_idempotency_conflict → recentIdempotencyConflict / 409', () {
      final code =
          SearchErrorCode.fromCode('SEARCH.USER.recent_idempotency_conflict');
      expect(code, SearchErrorCode.recentIdempotencyConflict);
      expect(code.httpStatus, 409);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('recent_storage_failed → recentStorageFailed / 500', () {
      final code =
          SearchErrorCode.fromCode('SEARCH.SYSTEM.recent_storage_failed');
      expect(code, SearchErrorCode.recentStorageFailed);
      expect(code.httpStatus, 500);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('未知码回退 unknown 兜底', () {
      expect(
        SearchErrorCode.fromCode('SEARCH.USER.__nonexistent__'),
        SearchErrorCode.unknown,
      );
    });
  });
}
