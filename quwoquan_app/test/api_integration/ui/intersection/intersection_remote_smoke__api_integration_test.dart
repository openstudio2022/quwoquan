import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_repository.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_statement_synthesizer.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_visit_writer.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

const _runSmoke = bool.fromEnvironment('RUN_LOCAL_GAMMA_REMOTE_SMOKE');
const _baseUrl = String.fromEnvironment('LOCAL_GAMMA_CONTENT_BASE_URL');
const _viewerId = String.fromEnvironment(
  'APP_CURRENT_USER_ID',
  defaultValue: 'fixture_user_current',
);

/// canonical acceptance JWT（`quwoquan_ops/cli/lib/local_environment_auth.py`
/// 本地签发通道），由包装脚本 `quwoquan_app/scripts/gamma/run_intersection_remote_smoke.py`
/// 仅通过测试子进程环境注入，禁止写入 flutter argv / dart-define / 报告。
/// content-service 强制 verified principal，无 token 的 smoke 恒 401（R-IX08）。
final _acceptanceToken =
    Platform.environment['LOCAL_GAMMA_ACCEPTANCE_TOKEN'] ?? '';
const _personObjectId = 'sys_travel_9003_sub_01';

class _StaticTokenProvider implements CloudAuthTokenProvider {
  const _StaticTokenProvider(this._token);

  final String _token;

  @override
  Future<String?> getAccessToken() async =>
      _token.trim().isEmpty ? null : _token;
}

CloudHttpClient _authedClient() =>
    CloudHttpClient(authTokenProvider: _StaticTokenProvider(_acceptanceToken));

IntersectionReason _expectDisplayReady(
  IntersectionReason reason,
  String label, {
  IntersectionTarget? contextObjectTarget,
}) {
  final displayReason = displayReadyIntersectionReason(
    reason,
    contextObjectTarget: contextObjectTarget,
  );
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
  test('RemoteIntersectionRepository without bearer fails closed', () async {
    if (!_runSmoke) {
      return markTestSkipped('Set RUN_LOCAL_GAMMA_REMOTE_SMOKE=true.');
    }

    final repo = RemoteIntersectionRepository(
      httpClient: CloudHttpClient(),
      baseUrl: _baseUrl,
      currentUserId: _viewerId,
    );

    await expectLater(
      repo.getMyIntersectionSummary(),
      throwsA(
        isA<CloudException>()
            .having((error) => error.statusCode, 'statusCode', 401)
            .having(
              (error) => error.runtimeFailure.kind,
              'runtimeFailure.kind',
              RuntimeFailureKind.auth,
            ),
      ),
    );
  });

  test(
    'RemoteIntersectionRepository reads seeded gamma intersections',
    () async {
      if (!_runSmoke) {
        return markTestSkipped('Set RUN_LOCAL_GAMMA_REMOTE_SMOKE=true.');
      }

      final repo = RemoteIntersectionRepository(
        httpClient: _authedClient(),
        baseUrl: _baseUrl,
        currentUserId: _viewerId,
      );
      final visitWriter = RemoteIntersectionVisitWriter(
        httpClient: _authedClient(),
        baseUrl: _baseUrl,
      );

      final summary = await repo.getMyIntersectionSummary();
      expect(summary.totalCount, greaterThan(0));
      expect(summary.dimensions, isNotEmpty);
      expect(
        summary.dimensions.every((item) => item.dimension.trim().isNotEmpty),
        isTrue,
      );
      expect(
        summary.dimensions.any((item) => item.dimension == 'relationship'),
        isTrue,
      );

      await visitWriter.markIntersectionsVisited();
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
      expect(renderableInbox, isNotEmpty);
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
      final objectContext = IntersectionTarget(
        objectType: 'user',
        objectId: _personObjectId,
        objectKind: 'person',
        routeId: 'userProfile',
      );
      expect(objectReasons, isNotEmpty);
      expect(objectReasons.first.actionTargetId, _personObjectId);
      _expectDisplayReady(
        objectReasons.first,
        'objectReasons.first',
        contextObjectTarget: objectContext,
      );
      final wishlistReason = objectReasons.firstWhere(
        (reason) => reason.kind == 'coWishlistedEntity',
      );
      _expectDisplayReady(
        wishlistReason,
        'coWishlistedEntity',
        contextObjectTarget: objectContext,
      );
      expect(
        wishlistReason.intersectionPoints.map((point) => point.sourceRef),
        contains('coWishlistedEntity'),
      );
      expect(wishlistReason.actionHints.first.actionKey, 'start_gathering');
      expect(wishlistReason.actionHints.first.dispatch, 'gathering');
      expect(
        wishlistReason.actionHints.first.target?.objectId,
        wishlistReason.actionTargetId,
      );
    },
  );

  test('CloudHttpClient feed smoke keeps recommendation attribution', () async {
    if (!_runSmoke) {
      return markTestSkipped('Set RUN_LOCAL_GAMMA_REMOTE_SMOKE=true.');
    }

    final client = _authedClient();
    final decoded = await client.getJson(
      Uri.parse(
        '$_baseUrl${ContentApiMetadata.getFeedPath}'
        '?sort=recommend&channelId=recommend&limit=5',
      ),
      headers: CloudRequestHeaders.withOwnerPersonaContext(
        CloudRequestHeaders.forPage(ContentRequestPageIds.getFeed),
        ownerUserId: _viewerId,
        personaId: _viewerId,
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
    expect(body['policyDigest'], isA<String>());
    expect(CloudResponseDecoder.mapList(body, 'items'), isNotEmpty);
  });
}
