// spec_ref: specs/feature-tree/discovery-content/content-display-consistency/content-action-intent-contract/spec.md#gwt-001

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/user_api_contract_harness.dart';

void main() {
  late UserApiContractHarness harness;

  setUpAll(() async {
    harness = await UserApiContractHarness.create();
    await harness.loginDisposableAccount('persona-block');
  });
  tearDownAll(() => harness.close());

  test('block 与 unblock persona 走真实 User service', () async {
    const targetPersonaId = 'contract_block_target_001';
    final blocked = await harness.personaRelationships.blockUser(
      BlockUserCommand(targetPersonaId: targetPersonaId),
    );
    expect(blocked.targetPersonaId, targetPersonaId);

    final unblocked = await harness.personaRelationships.unblockUser(
      UnblockUserCommand(targetPersonaId: targetPersonaId),
    );
    expect(unblocked.targetPersonaId, targetPersonaId);
  });
}
