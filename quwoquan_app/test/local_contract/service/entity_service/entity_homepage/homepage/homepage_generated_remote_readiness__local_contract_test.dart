// spec_ref: specs/feature-tree/shared-homepage-network/homepage-discovery-and-attach/homepage-entry-and-preview/spec.md#gwt-001
// spec_ref: specs/feature-tree/shared-homepage-network/homepage-review-and-content/homepage-overview-and-module-shell/spec.md#gwt-001
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/object-homepage-gamma-real-data-closure/spec.md#gwt-002
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/entity-homepage-intersection-redesign/spec.md#gwt-001
// spec_ref: specs/feature-tree/shared-homepage-network/homepage-review-and-content/homepage-review-read-and-score-summary/spec.md#gwt-001
// spec_ref: specs/feature-tree/shared-homepage-network/homepage-discovery-and-attach/missing-homepage-suggestion-and-review/spec.md#gwt-001
// spec_ref: specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline/claimed-homepage-basic-maintenance/spec.md#gwt-001
// readiness_case: homepage_get_entity_impact_app_local
// readiness_case: homepage_get_homepage_detail_app_local
// readiness_case: homepage_get_homepage_introduction_app_local
// readiness_case: homepage_get_homepage_related_groups_app_local
// readiness_case: homepage_get_homepage_review_summary_app_local
// readiness_case: homepage_get_homepage_shell_app_local
// readiness_case: homepage_get_object_page_bundle_app_local
// readiness_case: homepage_suggest_homepage_candidate_app_local
// readiness_case: homepage_update_claimed_homepage_basics_app_local

/// Homepage 对象 App local_contract readiness：production Remote composition
/// 必须经 GeneratedCloudOperationClient 发出 canonical HTTP wire，并对非成功
/// RuntimeError 及非法响应保持 fail-closed。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/di/entity_dependencies.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/entity/entity_request_page_ids.g.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/homepage_operation_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/remote_api_path_test_harness.dart';

typedef _HomepageRemoteFacets = ({
  HomepageQueryFacet query,
  HomepageIntroductionQuery introduction,
  HomepageCandidateCommandWriter command,
});

void main() {
  group('entity.homepage production Remote generated contract', () {
    late List<CapturedRemoteApiPathRequest> log;
    late _HomepageRemoteFacets facets;

    setUp(() {
      log = <CapturedRemoteApiPathRequest>[];
      facets = _buildFacets(log, responseFor: _responseFor);
    });

    test('GetHomepageDetail exact public GET and typed detail', () async {
      final result = await facets.query.getHomepageDetail('homepage-1');

      expect(result.homepageId, 'homepage-1');
      expect(result.title, '西湖景区');
      expect(result.categoryTags, <String>['travel', 'photography']);
      _expectQuery(
        log,
        operationId: AppCloudOperationIds.entityHomepageGetHomepageDetail,
        clientPageId: EntityRequestPageIds.getHomepageDetail,
        surface: AppUiSurfaces.homepageDetail,
      );
    });

    test('GetHomepageShell exact public GET and typed named slices', () async {
      final result = await facets.query.getHomepageShell('homepage-1');

      expect(result.homepage.homepageId, 'homepage-1');
      expect(result.reviewSummary?.averageRating, 4.8);
      expect(result.contentPreview?.single.postId, 'post-1');
      expect(result.relatedGroups?.single.circleId, 'circle-1');
      _expectQuery(
        log,
        operationId: AppCloudOperationIds.entityHomepageGetHomepageShell,
        clientPageId: EntityRequestPageIds.getHomepageShell,
        surface: AppUiSurfaces.homepageDetail,
      );
    });

    test(
      'GetHomepageIntroduction exact public GET and typed sections',
      () async {
        final result = await facets.introduction.getHomepageIntroduction(
          'homepage-1',
        );

        expect(result.homepageId, 'homepage-1');
        expect(result.summary, '湖山相映的公共景区');
        expect(result.sections.single.kind, 'overview');
        expect(result.sections.single.assets.single.assetId, 'asset-1');
        _expectQuery(
          log,
          operationId:
              AppCloudOperationIds.entityHomepageGetHomepageIntroduction,
          clientPageId: EntityRequestPageIds.getHomepageIntroduction,
          surface: AppUiSurfaces.homepageIntroduction,
        );
      },
    );

    test(
      'GetObjectPageBundle exact query wire and populated typed bundle',
      () async {
        final result = await facets.query.getObjectPageBundle(
          HomepageObjectPageBundleQuery(
            homepageId: 'homepage-1',
            referralSource: 'search',
            feedRequestId: 'feed-1',
            recommendationTraceId: 'trace-1',
            experimentBucket: 'bucket-a',
            rolloutCohort: 'hangzhou',
          ),
        );

        expect(result.objectId, 'homepage-1');
        expect(result.tagRefs, <String>['travel', 'photography']);
        expect(result.stats['followers'], 128);
        expect(result.highlightItems.single.postId, 'post-1');
        expect(result.relatedObjects.single.circleId, 'circle-1');
        _expectQuery(
          log,
          operationId: AppCloudOperationIds.entityHomepageGetObjectPageBundle,
          clientPageId: EntityRequestPageIds.getObjectPageBundle,
          surface: AppUiSurfaces.homepageDetail,
          query: const <String, String>{
            'referralSource': 'search',
            'feedRequestId': 'feed-1',
            'recommendationTraceId': 'trace-1',
            'experimentBucket': 'bucket-a',
            'rolloutCohort': 'hangzhou',
          },
        );
      },
    );

    test(
      'GetEntityImpact exact authenticated GET and typed fact row',
      () async {
        final result = await facets.query.getEntityImpact('homepage-1');

        expect(result.homepageId, 'homepage-1');
        expect(result.total, 1);
        expect(result.items.single.impactId, 'impact-1');
        expect(result.items.single.primaryText, '12 位摄影爱好者在这里留下记录');
        _expectQuery(
          log,
          operationId: AppCloudOperationIds.entityHomepageGetEntityImpact,
          clientPageId: EntityRequestPageIds.getEntityImpact,
          surface: AppUiSurfaces.homepageDetail,
        );
      },
    );

    test('GetHomepageReviewSummary exact GET and typed aggregation', () async {
      final result = await facets.query.getHomepageReviewSummary('homepage-1');

      expect(result.averageRating, 4.8);
      expect(result.ratingCount, 32);
      expect(result.highlightTags, <String>['摄影友好', '风景优美']);
      _expectQuery(
        log,
        operationId:
            AppCloudOperationIds.entityHomepageGetHomepageReviewSummary,
        clientPageId: EntityRequestPageIds.getHomepageReviewSummary,
        surface: AppUiSurfaces.homepageDetail,
      );
    });

    test('GetHomepageRelatedGroups exact GET and typed groups', () async {
      final result = await facets.query.getHomepageRelatedGroups('homepage-1');

      expect(result.groups?.single.circleId, 'circle-1');
      expect(result.groups?.single.name, '杭州摄影圈');
      expect(result.groups?.single.memberCount, 256);
      _expectQuery(
        log,
        operationId:
            AppCloudOperationIds.entityHomepageGetHomepageRelatedGroups,
        clientPageId: EntityRequestPageIds.getHomepageRelatedGroups,
        surface: AppUiSurfaces.homepageDetail,
      );
    });

    test('SuggestHomepageCandidate exact POST body and idempotency', () async {
      final result = await facets.command.suggest(
        SuggestHomepageCandidateCommand(
          title: '西湖摄影地',
          homepageType: 'sight',
          subtitle: '湖边日出机位',
          categoryTags: const <String>['travel', 'photography'],
          city: '杭州',
          sourcePlaceId: 'place-west-lake',
          location: const HomepageGeoPointInput(lat: 30.25, lng: 120.15),
        ),
      );

      expect(result.homepageId, 'candidate-1');
      expect(result.status, 'candidate');
      expect(result.title, '西湖摄影地');
      _expectCommand(
        log,
        operationId:
            AppCloudOperationIds.entityHomepageSuggestHomepageCandidate,
        clientPageId: EntityRequestPageIds.suggestHomepageCandidate,
        surface: AppUiSurfaces.suggestHomepage,
        method: 'POST',
        body: const <String, Object?>{
          'title': '西湖摄影地',
          'homepageType': 'sight',
          'subtitle': '湖边日出机位',
          'categoryTags': <String>['travel', 'photography'],
          'city': '杭州',
          'sourcePlaceId': 'place-west-lake',
          'location': <String, Object?>{'lat': 30.25, 'lng': 120.15},
        },
      );
    });

    test(
      'UpdateClaimedHomepageBasics exact PATCH wire and typed detail',
      () async {
        final result = await facets.command.updateClaimedBasics(
          UpdateClaimedHomepageBasicsCommand(
            homepageId: 'homepage-1',
            title: '西湖景区',
            subtitle: '更新后的公共简介',
            categoryTags: const <String>['travel', 'photography'],
            address: '杭州市西湖区',
            city: '杭州',
            location: const HomepageGeoPointInput(lat: 30.25, lng: 120.15),
          ),
        );

        expect(result.homepageId, 'homepage-1');
        expect(result.claimStatus, 'claimed');
        expect(result.subtitle, '更新后的公共简介');
        _expectCommand(
          log,
          operationId:
              AppCloudOperationIds.entityHomepageUpdateClaimedHomepageBasics,
          clientPageId: EntityRequestPageIds.updateClaimedHomepageBasics,
          surface: AppUiSurfaces.homepageMaintenance,
          method: 'PATCH',
          body: const <String, Object?>{
            'title': '西湖景区',
            'subtitle': '更新后的公共简介',
            'categoryTags': <String>['travel', 'photography'],
            'address': '杭州市西湖区',
            'city': '杭州',
            'location': <String, Object?>{'lat': 30.25, 'lng': 120.15},
          },
        );
      },
    );

    final failureCases =
        <
          ({
            String operationId,
            Future<Object?> Function(_HomepageRemoteFacets) invoke,
          })
        >[
          (
            operationId: AppCloudOperationIds.entityHomepageGetHomepageDetail,
            invoke: (target) => target.query.getHomepageDetail('homepage-1'),
          ),
          (
            operationId: AppCloudOperationIds.entityHomepageGetHomepageShell,
            invoke: (target) => target.query.getHomepageShell('homepage-1'),
          ),
          (
            operationId:
                AppCloudOperationIds.entityHomepageGetHomepageIntroduction,
            invoke: (target) =>
                target.introduction.getHomepageIntroduction('homepage-1'),
          ),
          (
            operationId: AppCloudOperationIds.entityHomepageGetObjectPageBundle,
            invoke: (target) => target.query.getObjectPageBundle(
              HomepageObjectPageBundleQuery(homepageId: 'homepage-1'),
            ),
          ),
          (
            operationId: AppCloudOperationIds.entityHomepageGetEntityImpact,
            invoke: (target) => target.query.getEntityImpact('homepage-1'),
          ),
          (
            operationId:
                AppCloudOperationIds.entityHomepageGetHomepageReviewSummary,
            invoke: (target) =>
                target.query.getHomepageReviewSummary('homepage-1'),
          ),
          (
            operationId:
                AppCloudOperationIds.entityHomepageGetHomepageRelatedGroups,
            invoke: (target) =>
                target.query.getHomepageRelatedGroups('homepage-1'),
          ),
          (
            operationId:
                AppCloudOperationIds.entityHomepageSuggestHomepageCandidate,
            invoke: (target) => target.command.suggest(
              SuggestHomepageCandidateCommand(
                title: '西湖摄影地',
                homepageType: 'sight',
              ),
            ),
          ),
          (
            operationId:
                AppCloudOperationIds.entityHomepageUpdateClaimedHomepageBasics,
            invoke: (target) => target.command.updateClaimedBasics(
              UpdateClaimedHomepageBasicsCommand(
                homepageId: 'homepage-1',
                title: '西湖景区',
              ),
            ),
          ),
        ];

    for (final failureCase in failureCases) {
      test(
        '${failureCase.operationId} canonical failure is not swallowed',
        () async {
          final failureLog = <CapturedRemoteApiPathRequest>[];
          final failingFacets = _buildFacets(
            failureLog,
            responseFor: (_) =>
                remoteApiPathJsonResponse(const <String, Object?>{
                  'code': 'ENTITY.SYSTEM.internal_error',
                  'message': 'entity homepage dependency unavailable',
                }, statusCode: 503),
          );

          await expectLater(
            failureCase.invoke(failingFacets),
            throwsA(isA<CloudException>()),
          );
          expect(failureLog, isNotEmpty);
          expect(
            failureLog.last.headers['X-Client-Operation-Id'],
            failureCase.operationId,
          );
        },
      );
    }
  });
}

_HomepageRemoteFacets _buildFacets(
  List<CapturedRemoteApiPathRequest> log, {
  required RemoteApiPathResponseFactory responseFor,
}) {
  final client = buildRemoteApiPathOperationClient(
    log,
    responseFor: responseFor,
  );
  final queries = EntityProductionComposition.homepageQueryFacets(
    client: client,
    detailInvocationContext: (clientPageId, {cancellation, deadlineAt}) =>
        _queryContext(
          clientPageId,
          AppUiSurfaces.homepageDetail,
          cancellation: cancellation,
          deadlineAt: deadlineAt,
        ),
    introductionInvocationContext: (clientPageId, {cancellation, deadlineAt}) =>
        _queryContext(
          clientPageId,
          AppUiSurfaces.homepageIntroduction,
          cancellation: cancellation,
          deadlineAt: deadlineAt,
        ),
    searchInvocationContext: (clientPageId, {cancellation, deadlineAt}) =>
        _queryContext(
          clientPageId,
          AppUiSurfaces.homepagePicker,
          cancellation: cancellation,
          deadlineAt: deadlineAt,
        ),
  );
  final commands = EntityProductionComposition.homepageCommandFacets(
    client: client,
    invocationContext: (clientPageId, surface) =>
        CloudOperationInvocationContext(
          surfaceId: surface.id,
          routeId: surface.routeId,
          clientPageId: clientPageId,
          idempotencyKey: _idempotencyKey,
          actor: _actor,
        ),
    claimRequestInvocationContext: (clientPageId, surface, {idempotencyKey}) =>
        CloudOperationInvocationContext(
          surfaceId: surface.id,
          routeId: surface.routeId,
          clientPageId: clientPageId,
          idempotencyKey: idempotencyKey ?? _idempotencyKey,
          actor: _actor,
        ),
    statusReportInvocationContext: (clientPageId, surface, {idempotencyKey}) =>
        CloudOperationInvocationContext(
          surfaceId: surface.id,
          routeId: surface.routeId,
          clientPageId: clientPageId,
          idempotencyKey: idempotencyKey ?? _idempotencyKey,
          actor: _actor,
        ),
  );
  return (
    query: queries.query,
    introduction: queries.introduction,
    command: commands.candidateWriter,
  );
}

CloudOperationInvocationContext _queryContext(
  String clientPageId,
  AppUiSurface surface, {
  CloudOperationCancellationSignal? cancellation,
  DateTime? deadlineAt,
}) => CloudOperationInvocationContext(
  surfaceId: surface.id,
  routeId: surface.routeId,
  clientPageId: clientPageId,
  cancellation: cancellation,
  deadlineAt: deadlineAt,
  actor: _actor,
);

const _actor = CloudOperationActorContext(
  accountId: 'account-1',
  personaId: 'persona-1',
);
const _idempotencyKey = 'homepage-readiness-intent-1';

void _expectQuery(
  List<CapturedRemoteApiPathRequest> log, {
  required String operationId,
  required String clientPageId,
  required AppUiSurface surface,
  Map<String, String> query = const <String, String>{},
}) {
  final request = log.last;
  expect(request.method, 'GET');
  expect(
    request.path,
    canonicalRemoteApiPath(
      operationId,
      pathParameters: const <String, String>{'homepageId': 'homepage-1'},
    ),
  );
  expect(request.query, query);
  expect(request.body, isEmpty);
  expect(request.headers['Authorization'], 'Bearer integration-contract-token');
  expect(request.headers.containsKey('Idempotency-Key'), isFalse);
  expectRemoteApiPathHeaders(
    request.headers,
    clientPageId: clientPageId,
    surfaceId: surface.id,
    operationId: operationId,
  );
}

void _expectCommand(
  List<CapturedRemoteApiPathRequest> log, {
  required String operationId,
  required String clientPageId,
  required AppUiSurface surface,
  required String method,
  required Map<String, Object?> body,
}) {
  final request = log.last;
  final pathParameters =
      operationId ==
          AppCloudOperationIds.entityHomepageUpdateClaimedHomepageBasics
      ? const <String, String>{'homepageId': 'homepage-1'}
      : const <String, String>{};
  expect(request.method, method);
  expect(
    request.path,
    canonicalRemoteApiPath(operationId, pathParameters: pathParameters),
  );
  expect(request.query, isEmpty);
  expect(request.body, body);
  expect(request.headers['Authorization'], 'Bearer integration-contract-token');
  expect(request.headers['Idempotency-Key'], _idempotencyKey);
  expectRemoteApiPathHeaders(
    request.headers,
    clientPageId: clientPageId,
    surfaceId: surface.id,
    operationId: operationId,
  );
}

http.Response _responseFor(http.Request request) {
  final path = request.url.path;
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.entityHomepageGetHomepageDetail,
            pathParameters: const <String, String>{'homepageId': 'homepage-1'},
          )) {
    return remoteApiPathJsonResponse(_homepageDetail());
  }
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.entityHomepageGetHomepageShell,
            pathParameters: const <String, String>{'homepageId': 'homepage-1'},
          )) {
    return remoteApiPathJsonResponse(<String, Object?>{
      'homepage': _homepageDetail(),
      'reviewSummary': _reviewSummary,
      'contentPreview': <Object?>[_contentPreview],
      'questionPreview': <Object?>[_questionPreview],
      'relatedGroups': <Object?>[_relatedGroup],
    });
  }
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.entityHomepageGetHomepageIntroduction,
            pathParameters: const <String, String>{'homepageId': 'homepage-1'},
          )) {
    return remoteApiPathJsonResponse(_introduction);
  }
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.entityHomepageGetObjectPageBundle,
            pathParameters: const <String, String>{'homepageId': 'homepage-1'},
          )) {
    return remoteApiPathJsonResponse(_objectPageBundle);
  }
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.entityHomepageGetEntityImpact,
            pathParameters: const <String, String>{'homepageId': 'homepage-1'},
          )) {
    return remoteApiPathJsonResponse(_entityImpact);
  }
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.entityHomepageGetHomepageReviewSummary,
            pathParameters: const <String, String>{'homepageId': 'homepage-1'},
          )) {
    return remoteApiPathJsonResponse(_reviewSummary);
  }
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.entityHomepageGetHomepageRelatedGroups,
            pathParameters: const <String, String>{'homepageId': 'homepage-1'},
          )) {
    return remoteApiPathJsonResponse(<String, Object?>{
      'groups': <Object?>[_relatedGroup],
    });
  }
  if (request.method == 'POST' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.entityHomepageSuggestHomepageCandidate,
          )) {
    return remoteApiPathJsonResponse(
      _homepageDetail(
        homepageId: 'candidate-1',
        title: '西湖摄影地',
        status: 'candidate',
      ),
    );
  }
  if (request.method == 'PATCH' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.entityHomepageUpdateClaimedHomepageBasics,
            pathParameters: const <String, String>{'homepageId': 'homepage-1'},
          )) {
    return remoteApiPathJsonResponse(
      _homepageDetail(subtitle: '更新后的公共简介', claimStatus: 'claimed'),
    );
  }
  return remoteApiPathJsonResponse(const <String, Object?>{
    'code': 'ENTITY.SYSTEM.internal_error',
    'message': 'unexpected entity homepage local contract request',
  }, statusCode: 500);
}

Map<String, Object?> _homepageDetail({
  String homepageId = 'homepage-1',
  String title = '西湖景区',
  String? subtitle = '湖山相映的公共景区',
  String status = 'published',
  String claimStatus = 'unclaimed',
}) => <String, Object?>{
  'homepageId': homepageId,
  'title': title,
  'subtitle': subtitle,
  'homepageType': 'sight',
  'status': status,
  'claimStatus': claimStatus,
  'categoryTags': <String>['travel', 'photography'],
  'city': '杭州',
  'viewerFollow': <String, Object?>{
    'viewerFollowsHomepage': true,
    'followerCount': 128,
  },
  'verified': true,
  'averageRating': 4.8,
  'ratingCount': 32,
  'contentPreview': <Object?>[_contentPreview],
  'questionPreview': <Object?>[_questionPreview],
  'relatedGroups': <Object?>[_relatedGroup],
  'relationEdges': <Object?>[],
  'introductionAssets': <Object?>[],
  'sourceUrls': <String>['https://zh.wikipedia.org/wiki/西湖'],
  'createdAt': '2026-07-20T00:00:00Z',
  'updatedAt': '2026-08-08T00:00:00Z',
};

const Map<String, Object?> _contentPreview = <String, Object?>{
  'postId': 'post-1',
  'title': '清晨的西湖',
  'summary': '断桥晨雾摄影记录',
  'contentType': 'image',
  'authorName': '摄影者',
  'likeCount': 18,
  'intersectionReasons': <Object?>[],
};

const Map<String, Object?> _questionPreview = <String, Object?>{
  'postId': 'question-1',
  'title': '日出机位在哪里？',
  'summary': '断桥附近的拍摄建议',
};

const Map<String, Object?> _relatedGroup = <String, Object?>{
  'circleId': 'circle-1',
  'name': '杭州摄影圈',
  'memberCount': 256,
  'linkedHomepageId': 'homepage-1',
  'linkedHomepageTitle': '西湖景区',
  'ownerUserId': 'account-owner-1',
  'ownerDisplayNameSnapshot': '杭州摄影主理人',
  'ownerAvatarUrlSnapshot': 'https://media.example/owner.jpg',
  'evidenceSnapshotId': 'circle:circle-1:members',
};

const Map<String, Object?> _reviewSummary = <String, Object?>{
  'averageRating': 4.8,
  'ratingCount': 32,
  'highlightTags': <String>['摄影友好', '风景优美'],
};

const Map<String, Object?> _introduction = <String, Object?>{
  'homepageId': 'homepage-1',
  'displayName': '西湖景区',
  'homepageType': 'sight',
  'summary': '湖山相映的公共景区',
  'sections': <Object?>[
    <String, Object?>{
      'kind': 'overview',
      'title': '认识西湖',
      'bodyMarkdown': '西湖由湖面、群山与历史景观共同构成。',
      'assets': <Object?>[
        <String, Object?>{
          'assetId': 'asset-1',
          'url': 'https://media.example/west-lake.jpg',
          'caption': '西湖晨景',
          'role': 'hero',
        },
      ],
      'timelineItems': <Object?>[],
    },
  ],
  'relatedObjects': <Object?>[_relatedGroup],
  'sourceUrls': <String>['https://zh.wikipedia.org/wiki/西湖'],
  'updatedAt': '2026-08-08T00:00:00Z',
};

const Map<String, Object?> _objectPageBundle = <String, Object?>{
  'objectType': 'homepage',
  'objectId': 'homepage-1',
  'canonicalEntityId': 'entity:west-lake',
  'title': '西湖景区',
  'subtitle': '湖山相映的公共景区',
  'objectPageTemplate': 'homepage-default',
  'tagRefs': <String>['travel', 'photography'],
  'stats': <String, Object?>{'followers': 128, 'reviews': 32},
  'intersectionReasons': <Object?>[],
  'highlightItems': <Object?>[_contentPreview],
  'contentSections': <String, Object?>{'records': 1, 'questions': 1},
  'relatedObjects': <Object?>[_relatedGroup],
  'relationEdges': <Object?>[],
};

const Map<String, Object?> _entityImpact = <String, Object?>{
  'homepageId': 'homepage-1',
  'total': 1,
  'items': <Object?>[
    <String, Object?>{
      'helpType': 'shared_interest',
      'action': 'view_records',
      'intersectionDimension': 'photography',
      'tagRef': 'photography',
      'source': 'canonical_projection',
      'count': 12,
      'primaryText': '12 位摄影爱好者在这里留下记录',
      'subtitleText': '查看他们的摄影记录',
      'impactId': 'impact-1',
      'primarySpans': <Object?>[],
      'sampleVisuals': <Object?>[],
      'actionHints': <Object?>[],
      'evidenceSnapshotId': 'impact:homepage-1:photography',
      'countObjectKind': 'persona',
      'iconKey': 'camera',
    },
  ],
};
