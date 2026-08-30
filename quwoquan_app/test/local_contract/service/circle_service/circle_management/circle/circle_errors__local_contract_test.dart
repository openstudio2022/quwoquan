// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-002
//
// CircleErrorCode 解码契约：wire code -> typed 枚举 + HTTP 语义，
// 未知码回退 unknown，锁定端云错误链路的 App 侧映射承诺。
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/generated/circle/circle_errors.g.dart';

void main() {
  group('CircleErrorCode 解码契约', () {
    test('circle_archived → circleArchived / 409', () {
      final code = CircleErrorCode.fromCode('CIRCLE.USER.circle_archived');
      expect(code, CircleErrorCode.circleArchived);
      expect(code.httpStatus, 409);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('circle_version_conflict → circleVersionConflict / 409', () {
      final code = CircleErrorCode.fromCode(
        'CIRCLE.USER.circle_version_conflict',
      );
      expect(code, CircleErrorCode.circleVersionConflict);
      expect(code.httpStatus, 409);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('circle_idempotency_conflict → circleIdempotencyConflict / 409', () {
      final code = CircleErrorCode.fromCode(
        'CIRCLE.USER.circle_idempotency_conflict',
      );
      expect(code, CircleErrorCode.circleIdempotencyConflict);
      expect(code.httpStatus, 409);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('未知码回退 unknown 兜底', () {
      expect(
        CircleErrorCode.fromCode('CIRCLE.USER.__nonexistent__'),
        CircleErrorCode.unknown,
      );
    });
  });
}
