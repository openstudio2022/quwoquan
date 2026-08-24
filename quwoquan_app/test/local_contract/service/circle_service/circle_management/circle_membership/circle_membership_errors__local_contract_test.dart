// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-002
//
// CircleMembershipErrorCode 解码契约：wire code -> typed 枚举 + HTTP 语义，
// 未知码回退 unknown，锁定端云错误链路的 App 侧映射承诺。
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/generated/circle/circle_membership_errors.g.dart';

void main() {
  group('CircleMembershipErrorCode 解码契约', () {
    test('membership_already_active → membershipAlreadyActive / 409', () {
      final code = CircleMembershipErrorCode.fromCode(
        'CIRCLE.USER.membership_already_active',
      );
      expect(code, CircleMembershipErrorCode.membershipAlreadyActive);
      expect(code.httpStatus, 409);
      expect(code.defaultMessage, isNotEmpty);
    });

    test(
      'membership_owner_cannot_leave → membershipOwnerCannotLeave / 409',
      () {
        final code = CircleMembershipErrorCode.fromCode(
          'CIRCLE.USER.membership_owner_cannot_leave',
        );
        expect(code, CircleMembershipErrorCode.membershipOwnerCannotLeave);
        expect(code.httpStatus, 409);
        expect(code.defaultMessage, isNotEmpty);
      },
    );

    test('membership_role_invalid → membershipRoleInvalid / 400', () {
      final code = CircleMembershipErrorCode.fromCode(
        'CIRCLE.USER.membership_role_invalid',
      );
      expect(code, CircleMembershipErrorCode.membershipRoleInvalid);
      expect(code.httpStatus, 400);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('membership_state_conflict → membershipStateConflict / 409', () {
      final code = CircleMembershipErrorCode.fromCode(
        'CIRCLE.USER.membership_state_conflict',
      );
      expect(code, CircleMembershipErrorCode.membershipStateConflict);
      expect(code.httpStatus, 409);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('membership_version_conflict → membershipVersionConflict / 409', () {
      final code = CircleMembershipErrorCode.fromCode(
        'CIRCLE.USER.membership_version_conflict',
      );
      expect(code, CircleMembershipErrorCode.membershipVersionConflict);
      expect(code.httpStatus, 409);
      expect(code.defaultMessage, isNotEmpty);
    });

    test(
      'membership_idempotency_conflict → membershipIdempotencyConflict / 409',
      () {
        final code = CircleMembershipErrorCode.fromCode(
          'CIRCLE.USER.membership_idempotency_conflict',
        );
        expect(code, CircleMembershipErrorCode.membershipIdempotencyConflict);
        expect(code.httpStatus, 409);
        expect(code.defaultMessage, isNotEmpty);
      },
    );

    test('未知码回退 unknown 兜底', () {
      expect(
        CircleMembershipErrorCode.fromCode('CIRCLE.USER.__nonexistent__'),
        CircleMembershipErrorCode.unknown,
      );
    });
  });
}
