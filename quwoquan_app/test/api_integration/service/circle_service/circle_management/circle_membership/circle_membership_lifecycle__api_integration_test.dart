// spec_ref: specs/feature-tree/circle-community/activity-member-governance/member-role-permission/spec.md#gwt-003

/// CircleMembership aggregate API integration contract.
///
/// The Circle create call is only real-environment setup; JoinCircle and
/// LeaveCircle remain the operations under test.
///
/// Missing or unreachable Gamma configuration fails closed in [setUpAll].
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/circle_api_contract_harness.dart';

CircleApiContractHarness? _harness;

CircleApiContractHarness get _api => _harness!;

void main() {
  setUpAll(() async {
    _harness = await CircleApiContractHarness.create();
  });

  tearDownAll(() => _harness?.close());

  // contract.yaml: membership_transaction_replay_projection_stream
  group('circle_membership_join_leave_end_to_end', () {
    late String circleId;

    setUpAll(() async {
      await _api.loginDisposableAccount('membership-owner');
      final nonce = DateTime.now().microsecondsSinceEpoch;
      final created = await _api.withIdempotencyKey(
        'l3-membership-circle-$nonce',
        () => _api.lifecycle.createCircle(
          CreateCircleCommand(name: 'L3 成员圈 $nonce', category: 'interest'),
        ),
      );
      circleId = created.circleId;
      await _api.loginDisposableAccount('membership-member');
    });

    test('JoinCircle / LeaveCircle 回执与重放语义', () async {
      final joinKey = 'l3-join-$circleId';
      final joinCommand = JoinCircleMembershipCommand(circleId: circleId);
      final joinReceipt = await _api.withIdempotencyKey(
        joinKey,
        () => _api.membership.join(joinCommand),
      );
      expect(joinReceipt.membershipId, isNotEmpty);
      expect(joinReceipt.state, CircleMembershipState.active);
      expect(joinReceipt.idempotentReplay, false);

      final joinReplay = await _api.withIdempotencyKey(
        joinKey,
        () => _api.membership.join(joinCommand),
      );
      expect(joinReplay.idempotentReplay, true);

      final left = await _api.withIdempotencyKey(
        'l3-leave-$circleId',
        () => _api.membership.leave(
          LeaveCircleMembershipCommand(circleId: circleId),
        ),
      );
      expect(left.state, CircleMembershipState.left);
    });
  });
}
