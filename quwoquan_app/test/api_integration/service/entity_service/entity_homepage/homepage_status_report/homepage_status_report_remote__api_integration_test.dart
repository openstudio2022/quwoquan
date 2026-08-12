// spec_ref: specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline/homepage-offline-report-and-history-retention/spec.md#gwt-001
// spec_ref: specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline/homepage-offline-report-and-history-retention/spec.md#gwt-002
// readiness_case: homepage_status_report_create_homepage_status_report_app_api
// readiness_case: homepage_status_report_get_my_pending_homepage_status_report_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_status_report/application/public/homepage_status_report_command_writer.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/entity_api_contract_harness.dart';

void main() {
  EntityApiContractHarness? createdHarness;

  setUpAll(() async {
    createdHarness = await EntityApiContractHarness.create();
  });
  tearDownAll(() async => createdHarness?.close());

  test('production Remote 提交真实主页状态上报并返回 pending review', () async {
    final harness = createdHarness!;
    final homepage = await _firstHomepage(harness);
    final nonce = DateTime.now().toUtc().microsecondsSinceEpoch.toString();

    final result = await harness.withIdempotencyKey(
      'homepage-status-report-$nonce',
      () async {
        final draft = HomepageStatusReportDraft(
          reason: 'incorrect_info',
          description: 'api-contract-$nonce',
        );
        final created = await harness.statusReports.createStatusReport(
          homepageId: homepage.homepageId,
          draft: draft,
        );
        final replay = await harness.statusReports.createStatusReport(
          homepageId: homepage.homepageId,
          draft: draft,
        );
        expect(replay.reportId, created.reportId);
        expect(replay.createdAt, created.createdAt);
        return created;
      },
    );

    expect(result.reportId, isNotEmpty);
    expect(result.homepageId, homepage.homepageId);
    expect(result.reporterPersonaId, harness.session.activePersona?.personaId);
    expect(result.reason, HomepageStatusReportReason.incorrectInfo);
    expect(result.status, HomepageStatusReportStatus.pendingReview);
    final readback = await harness.statusReportReader.getMyPendingStatusReport(
      homepageId: homepage.homepageId,
      reason: 'incorrect_info',
    );
    expect(readback.reportId, result.reportId);
    expect(readback.reporterPersonaId, result.reporterPersonaId);
    expect(readback.status, HomepageStatusReportStatus.pendingReview);
    final events = await harness.telemetry.waitForEvents(minimumCount: 4);
    expect(events.every((event) => event.succeeded), isTrue);
  });
}

Future<HomepageSearchItemView> _firstHomepage(
  EntityApiContractHarness harness,
) async {
  final slice = await harness.query.searchHomepages(
    HomepageSearchQuery(query: '北京', limit: 10),
  );
  expect(slice.items, isNotEmpty, reason: '目标环境没有可上报的真实主页');
  return slice.items.first;
}
