// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-plan-collaboration/spec.md#gwt-001
// readiness_case: circle-gathering-plan

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/gathering_board_ports.dart';

import '../../../../../support/runtime/api_contract/circle_api_contract_harness.dart';

const _accessToken = String.fromEnvironment('QWQ_GATHERING_PLAN_ACCESS_TOKEN');
const _accountId = String.fromEnvironment('QWQ_GATHERING_PLAN_ACCOUNT_ID');
const _personaId = String.fromEnvironment('QWQ_GATHERING_PLAN_PERSONA_ID');
const _gatheringId = String.fromEnvironment('QWQ_GATHERING_PLAN_GATHERING_ID');
const _planId = String.fromEnvironment('QWQ_GATHERING_PLAN_PLAN_ID');
const _planVersion = int.fromEnvironment('QWQ_GATHERING_PLAN_VERSION');
const _currentRevisionId = String.fromEnvironment(
  'QWQ_GATHERING_PLAN_CURRENT_REVISION_ID',
);
const _currentRevisionNumber = int.fromEnvironment(
  'QWQ_GATHERING_PLAN_CURRENT_REVISION_NUMBER',
);
const _currentRevisionDigest = String.fromEnvironment(
  'QWQ_GATHERING_PLAN_CURRENT_REVISION_DIGEST',
);

void main() {
  test('production Remote reads the managed canonical GatheringPlan identity and Board slice', () async {
    _requireManagedInputs();
    final harness = await CircleApiContractHarness.createManaged(
      accessToken: _accessToken,
      accountId: _accountId,
      personaId: _personaId,
    );
    addTearDown(harness.close);

    final result = await harness.gatheringPlans.readPlanResult(_gatheringId);

    expect(result.planId, _planId);
    expect(result.gatheringId, _gatheringId);
    expect(result.planVersion, _planVersion);
    expect(result.currentRevisionId, _currentRevisionId);
    expect(result.currentRevisionNumber, _currentRevisionNumber);
    expect(result.currentRevisionDigest, _currentRevisionDigest);
    expect(
      result.board.capability.state,
      GatheringBoardCapabilityState.available,
    );
    expect(result.board.items, isNotEmpty);
    expect(result.board.items.first.planItemId, 'agenda-1');
  });
}

void _requireManagedInputs() {
  final strings = <String>[
    _accessToken,
    _accountId,
    _personaId,
    _gatheringId,
    _planId,
    _currentRevisionId,
    _currentRevisionDigest,
  ];
  if (strings.any((value) => value.trim().isEmpty) ||
      _planVersion < 1 ||
      _currentRevisionNumber < 1) {
    throw StateError('managed GatheringPlan inputs are incomplete');
  }
}
