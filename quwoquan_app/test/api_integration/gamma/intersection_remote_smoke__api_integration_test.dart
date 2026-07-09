import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_repository.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_statement_synthesizer.dart';

const _runSmoke = bool.fromEnvironment('RUN_LOCAL_GAMMA_REMOTE_SMOKE');
const _baseUrl = String.fromEnvironment(
  'LOCAL_GAMMA_CONTENT_BASE_URL',
  defaultValue: 'http://127.0.0.1:19220',
);
const _viewerId = String.fromEnvironment(
  'APP_CURRENT_USER_ID',
  defaultValue: 'fixture_user_current',
);
const _personObjectId = 'sys_travel_9003_sub_01';

IntersectionReason _expectDisplayReady(IntersectionReason reason, String label) {
  final displayReason = displayReadyIntersectionReason(reason);
  expect(displayReason, isNotNull, reason: label);
  expect(displayReason!.primaryText, reason.primaryText, reason: label);
  expect(
    displayReason.primarySpans.map((span) => span.text).join(),
    displayReason.primaryText,
    reason: '$label primarySpans must join primaryText',
  );
  return displayReason;
}

void main() {
  test(
    'RemoteIntersectionRepository reads seeded gamma intersections',
    () async {
      if (!_runSmoke) {
        return markTestSkipped('Set RUN_LOCAL_GAMMA_REMOTE_SMOKE=true.');
      }

      final repo = RemoteIntersectionRepository(
        baseUrl: _baseUrl,
        currentUserId: _viewerId,
      );

      final summary = await repo.getMyIntersectionSummary();
      expect(summary.totalCount, greaterThan(0));
      expect(
        summary.dimensions,
        isNotEmpty,
      );
      expect(
        summary.dimensions.every((item) => item.dimension.trim().isNotEmpty),
        isTrue,
      );
      expect(
        summary.dimensions.any((item) => item.dimension == 'relationship'),
        isTrue,
      );

      await repo.markIntersectionsVisited();
      final visitedSummary = await repo.getMyIntersectionSummary();
      expect(visitedSummary.totalCount, summary.totalCount);
      expect(visitedSummary.totalNewCount, 0);
      expect(
        visitedSummary.dimensions.every((item) => item.newCount == 0),
        isTrue,
      );

      final inbox = await repo.listMyIntersections(filter: 'fact');
      expect(inbox, isNotEmpty);
      final renderableInbox = inbox
          .map(displayReadyIntersectionReason)
          .whereType<IntersectionReason>()
          .toList(growable: false);
      expect(
        renderableInbox,
        isNotEmpty,
      );
      expect(
        renderableInbox.any((reason) => reason.intersectionPoints.isNotEmpty),
        isTrue,
      );
      expect(
        renderableInbox.any(
          (reason) => reason.intersectionPoints.any(
            (point) => point.sourceRef.trim().isNotEmpty,
          ),
        ),
        isTrue,
      );

      final objectReasons = await repo.getObjectIntersections(
        objectId: _personObjectId,
        objectType: 'user',
      );
      expect(objectReasons, isNotEmpty);
      expect(objectReasons.first.actionTargetId, _personObjectId);
      _expectDisplayReady(objectReasons.first, 'objectReasons.first');
      final wishlistReason = objectReasons.firstWhere(
        (reason) => reason.kind == 'coWishlistedEntity',
      );
      _expectDisplayReady(wishlistReason, 'coWishlistedEntity');
      expect(
        wishlistReason.intersectionPoints.map((point) => point.sourceRef),
        contains('coWishlistedEntity'),
      );
      expect(wishlistReason.actionHints.first.actionKey, 'start_companion');
      expect(wishlistReason.actionHints.first.dispatch, 'companion');
      expect(wishlistReason.actionHints.first.target?.objectId, wishlistReason.actionTargetId);
    },
  );

  test('CloudHttpClient feed smoke keeps recommendation attribution', () async {
    if (!_runSmoke) {
      return markTestSkipped('Set RUN_LOCAL_GAMMA_REMOTE_SMOKE=true.');
    }

    final client = CloudHttpClient();
    final decoded = await client.getJson(
      Uri.parse(
        '$_baseUrl${ContentApiMetadata.getFeedPath}?channel=home&limit=5',
      ),
      headers: CloudRequestHeaders.withOwnerSubAccountContext(
        CloudRequestHeaders.forPage(ContentRequestPageIds.getFeed),
        ownerUserId: _viewerId,
        subAccountId: _viewerId,
      ),
    );
    final body = CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.getFeed,
    );
    expect(
      body['feedRequestId'],
      isA<String>().having((v) => v, 'value', isNotEmpty),
    );
    expect(body['rankingVersion'], isA<String>());
    expect(body['reasonVersion'], isA<String>());
    expect(CloudResponseDecoder.mapList(body, 'items'), isNotEmpty);
  });
}
