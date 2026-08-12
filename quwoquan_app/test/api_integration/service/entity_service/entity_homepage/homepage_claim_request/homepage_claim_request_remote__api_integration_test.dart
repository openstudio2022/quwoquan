// spec_ref: specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline/homepage-claim-request-and-review/spec.md#gwt-001
// spec_ref: specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline/homepage-claim-request-and-review/spec.md#gwt-002
// readiness_case: homepage_claim_request_create_homepage_claim_request_app_api
// readiness_case: homepage_claim_request_get_my_pending_homepage_claim_request_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_claim_request/application/public/homepage_claim_request_command_writer.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/entity_api_contract_harness.dart';

void main() {
  EntityApiContractHarness? createdHarness;

  setUpAll(() async {
    createdHarness = await EntityApiContractHarness.create();
  });
  tearDownAll(() async => createdHarness?.close());

  test('production Remote 提交真实主页认领并返回 pending review', () async {
    final harness = createdHarness!;
    final homepage = await _firstHomepage(harness);
    final nonce = DateTime.now().toUtc().microsecondsSinceEpoch.toString();

    final result = await harness.withIdempotencyKey(
      'homepage-claim-$nonce',
      () async {
        final draft = HomepageClaimRequestDraft(
          claimTier: 'basic',
          contactPhone: '13800000000',
          note: 'api-contract-$nonce',
        );
        final created = await harness.claimRequests.createClaimRequest(
          homepageId: homepage.homepageId,
          draft: draft,
        );
        final replay = await harness.claimRequests.createClaimRequest(
          homepageId: homepage.homepageId,
          draft: draft,
        );
        expect(replay.claimRequestId, created.claimRequestId);
        expect(replay.createdAt, created.createdAt);
        return created;
      },
    );

    expect(result.claimRequestId, isNotEmpty);
    expect(result.homepageId, homepage.homepageId);
    expect(result.requesterPersonaId, harness.session.activePersona?.personaId);
    expect(result.claimTier, HomepageClaimTier.basic);
    expect(result.status, HomepageClaimReviewStatus.pendingReview);
    final readback = await harness.claimRequestReader.getMyPendingClaimRequest(
      homepageId: homepage.homepageId,
    );
    expect(readback.claimRequestId, result.claimRequestId);
    expect(readback.requesterPersonaId, result.requesterPersonaId);
    expect(readback.status, HomepageClaimReviewStatus.pendingReview);
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
  expect(slice.items, isNotEmpty, reason: '目标环境没有可认领的真实主页');
  return slice.items.first;
}
