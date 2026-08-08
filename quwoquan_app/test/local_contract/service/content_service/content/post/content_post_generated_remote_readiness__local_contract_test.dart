// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-005
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-005
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/post-create-update/spec.md#gwt-003
// readiness_case: post_get_author_impact_app_local
// readiness_case: post_get_entity_wishlist_state_app_local
// readiness_case: post_get_my_footprint_app_local
// readiness_case: post_list_author_impact_evidence_app_local
// readiness_case: post_submit_post_publication_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/author_impact_remote.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/footprint_query_remote.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/post_publication_remote.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/post_reader_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/remote_api_path_test_harness.dart';

const _personaId = 'persona-author-impact';
const _impactId = 'impact-decision-1';

http.Response _responseFor(http.Request request) {
  final path = request.url.path;
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.contentPostGetAuthorImpact,
            pathParameters: const <String, String>{'personaId': _personaId},
          )) {
    return remoteApiPathJsonResponse(<String, Object?>{
      'authorId': _personaId,
      'total': 1,
      'items': <Object?>[
        <String, Object?>{
          'helpType': 'decision',
          'action': 'wishlist',
          'intersectionDimension': 'entity',
          'tagRef': 'Place/中国/浙江/杭州/西湖',
          'source': 'content_behavior',
          'count': 2,
          'primaryText': '作品帮助两人做出决定',
          'subtitleText': '最近三十天',
          'impactId': _impactId,
          'primarySpans': <Object?>[
            <String, Object?>{'text': '作品帮助两人做出决定', 'role': 'plain'},
          ],
          'sampleVisuals': <Object?>[],
          'actionHints': <Object?>[],
          'evidenceSnapshotId': 'impact-snapshot-1',
          'countObjectKind': 'post',
          'iconKey': 'decision',
          'freshAt': '2026-08-08T08:00:00Z',
          'timeBucket': 'recent',
          'lifecycleState': 'active',
          'previousStrength': 1.0,
          'strengthDelta': 1.0,
        },
      ],
    });
  }
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.contentPostListAuthorImpactEvidence,
            pathParameters: const <String, String>{'personaId': _personaId},
          )) {
    return remoteApiPathJsonResponse(<String, Object?>{
      'impactId': _impactId,
      'evidenceSnapshotId': 'impact-snapshot-1',
      'totalCount': 1,
      'items': <Object?>[
        <String, Object?>{
          'evidenceId': 'impact-evidence-1',
          'impactId': _impactId,
          'helpType': 'decision',
          'action': 'wishlist',
          'intersectionDimension': 'entity',
          'occurredAt': '2026-08-08T07:30:00Z',
          'summaryText': '一位用户把目标加入想去清单',
          'actionHints': <Object?>[],
        },
      ],
      'nextCursor': 'impact-cursor-2',
      'hasMore': true,
    });
  }
  if (request.method == 'GET' && path == '/content/footprint') {
    return remoteApiPathJsonResponse(<String, Object?>{
      'items': <Object?>[
        <String, Object?>{
          'postId': 'post-footprint-1',
          'action': 'viewed',
          'occurredAt': '2026-08-08T07:00:00Z',
        },
      ],
      'nextCursor': 'footprint-cursor-2',
    });
  }
  if (request.method == 'GET' && path == '/content/entity-wishlist-state') {
    return remoteApiPathJsonResponse(<String, Object?>{
      'objectId': 'homepage-west-lake',
      'objectKind': 'homepage',
      'wishlisted': true,
    });
  }
  if (request.method == 'POST' && path == '/content/posts:publish') {
    return remoteApiPathJsonResponse(<String, Object?>{
      'publishIntentId': 'publish-intent-1',
      'localDraftId': 'draft-1',
      'postId': 'post-published-1',
      'state': 'published',
      'committedVersion': 1,
      'acceptedAt': '2026-08-08T08:30:00Z',
    });
  }
  throw StateError('unexpected ContentPost request: ${request.method} $path');
}

CloudOperationInvocationContext _context({
  required String surfaceId,
  required String routeId,
  required String clientPageId,
  String? idempotencyKey,
}) => CloudOperationInvocationContext(
  surfaceId: surfaceId,
  routeId: routeId,
  clientPageId: clientPageId,
  actor: const CloudOperationActorContext(
    accountId: 'account-content-post',
    personaId: 'persona-content-post',
    deviceActorId: 'device-content-post',
  ),
  idempotencyKey: idempotencyKey,
);

void main() {
  group('ContentPost generated Remote readiness', () {
    test(
      'GetAuthorImpact 与 ListAuthorImpactEvidence 严格读取非空 typed 投影',
      () async {
        final requests = <CapturedRemoteApiPathRequest>[];
        final query = RemoteAuthorImpactQuery(
          client: buildRemoteApiPathOperationClient(
            requests,
            responseFor: _responseFor,
          ),
          invocationContext: (clientPageId) => _context(
            surfaceId: AppUiSurfaces.userProfile.id,
            routeId: AppUiSurfaces.userProfile.routeId,
            clientPageId: clientPageId,
          ),
        );

        final summary = await query.getAuthorImpact(_personaId);
        final evidence = await query.listAuthorImpactEvidence(
          personaId: _personaId,
          impactId: _impactId,
          evidenceSnapshotId: 'impact-snapshot-1',
          cursor: 'impact-cursor-1',
          limit: 20,
        );

        expect(summary.authorId, _personaId);
        expect(summary.total, 1);
        expect(summary.items.single.impactId, _impactId);
        expect(evidence.items.single.evidenceId, 'impact-evidence-1');
        expect(evidence.nextCursor, 'impact-cursor-2');
        expect(evidence.hasMore, isTrue);

        expect(requests, hasLength(2));
        expect(requests[0].method, 'GET');
        expect(
          requests[0].path,
          canonicalRemoteApiPath(
            AppCloudOperationIds.contentPostGetAuthorImpact,
            pathParameters: const <String, String>{'personaId': _personaId},
          ),
        );
        expect(requests[0].query, const <String, String>{'limit': '12'});
        expect(requests[0].body, isEmpty);
        expectRemoteApiPathHeaders(
          requests[0].headers,
          clientPageId: ContentRequestPageIds.getAuthorImpact,
          surfaceId: AppUiSurfaces.userProfile.id,
          operationId: AppCloudOperationIds.contentPostGetAuthorImpact,
        );

        expect(requests[1].method, 'GET');
        expect(
          requests[1].path,
          canonicalRemoteApiPath(
            AppCloudOperationIds.contentPostListAuthorImpactEvidence,
            pathParameters: const <String, String>{'personaId': _personaId},
          ),
        );
        expect(requests[1].query, const <String, String>{
          'impactId': _impactId,
          'evidenceSnapshotId': 'impact-snapshot-1',
          'cursor': 'impact-cursor-1',
          'limit': '20',
        });
        expect(requests[1].body, isEmpty);
        expectRemoteApiPathHeaders(
          requests[1].headers,
          clientPageId: ContentRequestPageIds.listAuthorImpactEvidence,
          surfaceId: AppUiSurfaces.userProfile.id,
          operationId: AppCloudOperationIds.contentPostListAuthorImpactEvidence,
        );
        for (final request in requests) {
          _expectAuthorization(request.headers);
        }
      },
    );

    test('GetMyFootprint 透传私有分页查询并解码非空结果', () async {
      final requests = <CapturedRemoteApiPathRequest>[];
      final repository = RemoteFootprintRepository(
        client: buildRemoteApiPathOperationClient(
          requests,
          responseFor: _responseFor,
        ),
        invocationContext: (clientPageId) => _context(
          surfaceId: AppUiSurfaces.myFootprint.id,
          routeId: AppUiSurfaces.myFootprint.routeId,
          clientPageId: clientPageId,
        ),
      );

      final page = await repository.getMyFootprint(
        type: 'viewed',
        cursor: 'footprint-cursor-1',
        limit: 9,
      );

      expect(page.items.single.postId, 'post-footprint-1');
      expect(page.items.single.action, 'viewed');
      expect(page.nextCursor, 'footprint-cursor-2');
      expect(requests.single.method, 'GET');
      expect(
        requests.single.path,
        canonicalRemoteApiPath(AppCloudOperationIds.contentPostGetMyFootprint),
      );
      expect(requests.single.query, const <String, String>{
        'type': 'viewed',
        'cursor': 'footprint-cursor-1',
        'limit': '9',
      });
      expect(requests.single.body, isEmpty);
      expectRemoteApiPathHeaders(
        requests.single.headers,
        clientPageId: ContentRequestPageIds.getMyFootprint,
        surfaceId: AppUiSurfaces.myFootprint.id,
        operationId: AppCloudOperationIds.contentPostGetMyFootprint,
      );
      _expectAuthorization(requests.single.headers);
    });

    test('GetEntityWishlistState 只发送 canonical query 并解码真实状态', () async {
      final requests = <CapturedRemoteApiPathRequest>[];
      final reader = RemoteContentPostReaderAdapter(
        client: buildRemoteApiPathOperationClient(
          requests,
          responseFor: _responseFor,
        ),
        invocationContext: (clientPageId) => _context(
          surfaceId: AppUiSurfaces.homepageDetail.id,
          routeId: AppUiSurfaces.homepageDetail.routeId,
          clientPageId: clientPageId,
        ),
      );

      final state = await reader.getEntityWishlistState(
        objectId: 'homepage-west-lake',
        objectKind: 'homepage',
      );

      expect(state.objectId, 'homepage-west-lake');
      expect(state.objectKind, 'homepage');
      expect(state.wishlisted, isTrue);
      expect(requests.single.method, 'GET');
      expect(requests.single.path, '/content/entity-wishlist-state');
      expect(requests.single.query, const <String, String>{
        'objectId': 'homepage-west-lake',
        'objectKind': 'homepage',
      });
      expect(requests.single.body, isEmpty);
      expectRemoteApiPathHeaders(
        requests.single.headers,
        clientPageId: ContentRequestPageIds.getEntityWishlistState,
        surfaceId: AppUiSurfaces.homepageDetail.id,
        operationId: AppCloudOperationIds.contentPostGetEntityWishlistState,
      );
      _expectAuthorization(requests.single.headers);
    });

    test('SubmitPostPublication 以同一图片 intent/key 重放同一 typed receipt', () async {
      final requests = <CapturedRemoteApiPathRequest>[];
      final writer = RemoteContentPostPublicationWriter(
        client: buildRemoteApiPathOperationClient(
          requests,
          responseFor: _responseFor,
        ),
        invocationContext: (clientPageId, idempotencyKey) => _context(
          surfaceId: AppUiSurfaces.createWorkspace.id,
          routeId: AppUiSurfaces.createWorkspace.routeId,
          clientPageId: clientPageId,
          idempotencyKey: idempotencyKey,
        ),
      );
      final command = SubmitContentPostPublicationCommand(
        publishIntentId: 'publish-intent-1',
        localDraftId: 'draft-1',
        contentType: ContentType.image,
        contentIdentity: ContentIdentity.work,
        title: '图片发布单轨',
        mediaAssetIds: const <String>['image-asset-1'],
        visibility: Visibility.public,
      );

      final first = await writer.submitPostPublication(command);
      final replay = await writer.submitPostPublication(command);

      expect(first.postId, 'post-published-1');
      expect(first.state, 'published');
      expect(first.committedVersion, 1);
      expect(replay.toWire(), first.toWire());
      expect(requests, hasLength(2));
      for (final request in requests) {
        expect(request.method, 'POST');
        expect(request.path, '/content/posts:publish');
        expect(request.query, isEmpty);
        expect(request.body['publishIntentId'], 'publish-intent-1');
        expect(request.body['localDraftId'], 'draft-1');
        expect(request.body['contentType'], 'image');
        expect(request.body['contentIdentity'], 'work');
        expect(request.body['title'], '图片发布单轨');
        expect(request.body['mediaAssetIds'], const <Object?>['image-asset-1']);
        expect(request.body, isNot(contains('articleMarkdown')));
        expect(request.body['visibility'], 'public');
        expect(request.body, isNot(contains('circleIds')));
        expectRemoteApiPathHeaders(
          request.headers,
          clientPageId: ContentRequestPageIds.submitPostPublication,
          surfaceId: AppUiSurfaces.createWorkspace.id,
          operationId: AppCloudOperationIds.contentPostSubmitPostPublication,
        );
        expect(request.headers['Idempotency-Key'], 'publish-intent-1');
        _expectAuthorization(request.headers);
      }
      expect(requests[1].body, requests[0].body);
    });

    test('malformed wishlist projection fail-closed，不合成状态', () async {
      final reader = RemoteContentPostReaderAdapter(
        client: buildRemoteApiPathOperationClient(
          <CapturedRemoteApiPathRequest>[],
          responseFor: (_) => remoteApiPathJsonResponse(<String, Object?>{
            'objectId': 'homepage-west-lake',
            'objectKind': 'homepage',
            'wishlisted': 'yes',
          }),
        ),
        invocationContext: (clientPageId) => _context(
          surfaceId: AppUiSurfaces.homepageDetail.id,
          routeId: AppUiSurfaces.homepageDetail.routeId,
          clientPageId: clientPageId,
        ),
      );

      await expectLater(
        reader.getEntityWishlistState(
          objectId: 'homepage-west-lake',
          objectKind: 'homepage',
        ),
        throwsA(
          isA<CloudException>()
              .having(
                (error) => error.type,
                'type',
                CloudErrorType.invalidResponse,
              )
              .having(
                (error) => error.code,
                'code',
                'APP.CONTRACT.invalid_json',
              )
              .having(
                (error) => error.sourceOperationId,
                'sourceOperationId',
                AppCloudOperationIds.contentPostGetEntityWishlistState,
              ),
        ),
      );
    });
  });
}

void _expectAuthorization(Map<String, String> headers) {
  final authorization = headers.entries
      .where((entry) => entry.key.toLowerCase() == 'authorization')
      .map((entry) => entry.value)
      .single;
  expect(authorization, 'Bearer integration-contract-token');
}
