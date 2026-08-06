// spec_ref: specs/feature-tree/discovery-content/content-display-consistency/content-action-intent-contract/spec.md#gwt-001

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/content_api_contract_harness.dart';

void main() {
  late ContentApiContractHarness harness;

  setUpAll(() async => harness = await ContentApiContractHarness.create());
  tearDownAll(() => harness.close());

  test('production report Remote 接受 canonical typed command', () async {
    await harness.reports.createReport(
      CreateContentReportCommand(
        targetId: 'fixture_photo_001',
        targetType: ReportTargetType.post,
        reason: ReportReason.spam,
        description: 'api contract',
      ),
    );
  });
}
