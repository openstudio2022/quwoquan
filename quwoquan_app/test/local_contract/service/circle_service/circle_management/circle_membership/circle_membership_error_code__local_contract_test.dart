import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/generated/circle/circle_membership_errors.g.dart';
import 'package:quwoquan_app/runtime/errors/domain_error_code.dart';

void main() {
  test('CircleMembership owns membership_not_found end to end', () {
    const error = CircleMembershipErrorCode.membershipNotFound;

    expect(error.httpStatus, 404);
    expect(
      CircleMembershipErrorCode.fromCode(error.code),
      CircleMembershipErrorCode.membershipNotFound,
    );
    expect(
      DomainErrorCodeRegistry.fromCode(error.code)?.value,
      CircleMembershipErrorCode.membershipNotFound,
    );
  });
}
