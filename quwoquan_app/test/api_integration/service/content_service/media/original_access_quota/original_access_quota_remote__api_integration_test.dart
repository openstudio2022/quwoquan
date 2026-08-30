// spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-003
// readiness_case: original_access_quota_reserve_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/content_api_contract_harness.dart';

void main() {
  late ContentApiContractHarness harness;

  setUpAll(() async => harness = await ContentApiContractHarness.create());
  tearDownAll(() => harness.close());

  test(
    'production ReserveOriginalImageAccessGrant 返回可审计成功或 typed 拒绝',
    () async {
      final feed = await harness.feed.listDiscoveryFeedPage(
        category: 'photo',
        type: 'image',
        limit: 20,
      );
      final item = feed.items.firstWhere(
        (candidate) => (candidate.mediaAssetId?.trim() ?? '').isNotEmpty,
        orElse: () => throw StateError(
          'CONTENT_EXPERIENCE_BLOCK: image feed has no canonical mediaAssetId',
        ),
      );
      final mediaId = item.mediaAssetId!.trim();
      final key =
          'content-original-access-${DateTime.now().microsecondsSinceEpoch}';

      try {
        final grant = await harness.withIdempotencyKey(
          key,
          () => harness.originalAccess.requestOriginalAccess(
            RequestContentMediaOriginalAccessCommand(mediaId: mediaId),
          ),
        );
        expect(grant.mediaId, mediaId);
        expect(grant.status, 'granted');
        expect(grant.originalUrl.scheme, 'https');
        expect(grant.auditId, isNotEmpty);
        expect(grant.sizeBytes, greaterThan(0));
        expect(grant.ttlSeconds, greaterThan(0));
        expect(grant.expiresAt.isAfter(DateTime.now().toUtc()), isTrue);
      } on CloudException catch (error) {
        expect(error.statusCode, 403);
        expect(error.code, 'CONTENT.USER.original_access_denied');
        expect(error.sourceOperationId, 'ReserveOriginalImageAccessGrant');
      }
    },
  );
}
