/// L1a Entity/Homepage：Mock DTO 形状 + Remote review 请求体与 metadata writable_fields 对齐
library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/cloud/entity/generated/entity_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_introduction.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import '../../../../support/cloud_services/homepage_alpha_test_adapter.dart';

import '../../../../support/homepage_remote_test_support.dart';

void main() {
  test('HomepageRelatedGroupSummary 只接受 canonical circleId 与证据快照', () {
    final group = HomepageRelatedGroupSummary.fromMap(<String, dynamic>{
      'circleId': 'fixture_circle_photo',
      'name': '契约摄影社',
      'memberCount': 128,
      'ownerUserId': 'fixture_user_owner',
      'ownerDisplayNameSnapshot': '契约摄影社主理人',
      'ownerAvatarUrlSnapshot': '',
      'evidenceSnapshotId': 'circle:fixture_circle_photo:members:v1',
    });
    expect(group.circleId, 'fixture_circle_photo');
    expect(group.ownerUserId, 'fixture_user_owner');
    expect(group.ownerDisplayNameSnapshot, '契约摄影社主理人');
    expect(group.evidenceSnapshotId, isNotEmpty);

    final unscoped = HomepageRelatedGroupSummary.fromMap(<String, dynamic>{
      'id': 'unscoped_circle_alias',
      'name': '旧别名',
    });
    expect(unscoped.circleId, isEmpty);
  });

  test('HomepageIntroduction 只解码公开来源，不保留内部 sourceRefs', () {
    final introduction = HomepageIntroduction.fromMap(<String, dynamic>{
      'homepageId': 'homepage_sight_west_lake',
      'displayName': '西湖',
      'homepageType': 'sight',
      'summary': '摘要',
      'sections': <dynamic>[],
      'relatedObjects': <dynamic>[],
      'primarySource': <String, dynamic>{
        'sourceKind': 'wikipedia',
        'sourceUrl': 'https://zh.wikipedia.org/wiki/西湖',
        'title': '西湖',
        'policyRevision': 'encyclopedia-primary',
      },
      'sourceUrls': <String>['https://zh.wikipedia.org/wiki/西湖'],
      'sourceRefs': <String>['internal/source/unit-1'],
    });
    expect(introduction.primarySource?.sourceKind, 'wikipedia');
    expect(introduction.sourceUrls, <String>[
      'https://zh.wikipedia.org/wiki/西湖',
    ]);
    expect(introduction.toMap().containsKey('sourceRefs'), isFalse);
  });

  test('CloudResponseDecoder.mapList 读取 groups 列表', () {
    final obj = <String, dynamic>{
      'groups': [
        {'circleId': 'g', 'name': 'FromGroups'},
      ],
      'relatedGroups': [
        {'circleId': 'r', 'name': 'FromRelated'},
      ],
    };
    final rows = CloudResponseDecoder.mapList(obj, 'groups');
    expect(rows, hasLength(1));
    expect(rows.single['circleId'], 'g');
  });

  group('AlphaHomepageFacet projection adapter', () {
    late MockHomepageRepository repo;

    setUp(() {
      repo = MockHomepageRepository();
    });

    test('searchHomepages 过滤 sight + 城市', () async {
      final rows = await repo.searchHomepages(
        query: '西湖',
        homepageType: 'sight',
        city: '杭州',
        status: 'published',
        limit: 10,
      );
      expect(rows, isNotEmpty);
      for (final h in rows) {
        expect(h.homepageType, 'sight');
        expect(h.city, '杭州');
        expect(h.status, 'published');
        expect(h.canonicalEntityId, isNotEmpty);
      }
      expect(rows.any((h) => h.id == 'homepage_sight_west_lake'), isTrue);
      expect(
        rows.any((h) => h.canonicalEntityId == 'entity:sight:west_lake'),
        isTrue,
      );
    });

    test('getHomepageDetail / Shell / ReviewSummary / RelatedGroups', () async {
      const id = 'homepage_sight_west_lake';
      final detail = await repo.getHomepageDetail(id);
      expect(detail.id, id);
      expect(detail.title, '西湖景区');
      expect(detail.reviewSummary?.averageRating, 4.7);
      expect(detail.reviewSummary?.highlightTags, isNotEmpty);

      final shell = await repo.getHomepageShell(id);
      expect(shell.homepage.id, id);
      expect(shell.relatedGroups, isNotEmpty);

      final review = await repo.getHomepageReviewSummary(id);
      expect(review.ratingCount, 328);
      expect(review.highlightTags, isNotEmpty);

      final groups = await repo.getHomepageRelatedGroups(id);
      expect(groups, isNotEmpty);
      expect(groups.first.circleId, isNotEmpty);
      expect(groups.first.name, isNotEmpty);
    });

    test('getObjectPageBundle 返回统一对象页网络契约', () async {
      const id = 'homepage_sight_west_lake';
      final bundle = await repo.getObjectPageBundle(
        id,
        referralSource: 'entity_page',
        feedRequestId: 'feed-1',
        recommendationTraceId: 'trace-1',
        experimentBucket: 'A',
        rolloutCohort: 'city-hz',
      );

      expect(bundle.objectType, 'homepage');
      expect(bundle.objectId, id);
      expect(bundle.canonicalEntityId, 'entity:sight:west_lake');
      expect(bundle.objectPageTemplate, isNotEmpty);
      expect(bundle.tagRefs, isNotEmpty);
      expect(bundle.intersectionReasons, isEmpty);
      expect(bundle.highlightItems, isNotEmpty);
      expect(bundle.relatedObjects, isNotEmpty);
      expect(bundle.relationEdges, isEmpty);
      expect(bundle.assistantContext?.referralSource, 'entity_page');
      expect(bundle.assistantContext?.feedRequestId, 'feed-1');
      expect(bundle.assistantContext?.relationEdgeIds, isEmpty);
      expect(bundle.rolloutContext?.cohort, 'city-hz');
      expect(bundle.rolloutContext?.relationEvidenceEnabled, isFalse);
    });

    test(
      'getHomepageDetail 支持 metadata 声明的 homepageId 与 canonicalEntityId',
      () async {
        const homepageId = 'homepage_sight_emeishan';
        final byHomepageId = await repo.getHomepageDetail(homepageId);
        expect(byHomepageId.title, '峨眉山');

        final byCanonical = await repo.getHomepageDetail(
          'entity:sight:emeishan',
        );
        expect(byCanonical.id, homepageId);

        final bundle = await repo.getObjectPageBundle('entity:sight:emeishan');
        expect(bundle.objectId, homepageId);
        expect(bundle.canonicalEntityId, 'entity:sight:emeishan');
      },
    );

    test('getHomepageRelatedGroups 缺省 groups 时返回空列表', () async {
      final r = MockHomepageRepository();
      final created = await r.suggestHomepageCandidate(
        draft: const HomepageSuggestionDraft(
          title: '仅测相关群空',
          homepageType: 'storefront',
          city: '上海',
        ),
      );
      final emptyGroups = await r.getHomepageRelatedGroups(created.id);
      expect(emptyGroups, isEmpty);
    });

    test('fixture 缺少主页时映射为 metadata 生成的 not-found 语义', () async {
      await expectLater(
        repo.getHomepageDetail('missing-homepage-id'),
        throwsA(
          isA<CloudException>()
              .having(
                (error) => error.code,
                'code',
                EntityErrorCode.homepageNotFound.code,
              )
              .having(
                (error) => error.userMessage,
                'userMessage',
                EntityErrorCode.homepageNotFound.defaultMessage,
              ),
        ),
      );
    });

    test(
      'contract seed includes campus and travel photography homepage templates',
      () async {
        final campus = await repo.searchHomepages(
          query: '北京大学',
          homepageType: 'university',
          status: 'published',
          limit: 10,
        );
        expect(
          campus.map((h) => h.id),
          contains('fixture_homepage_university_pku'),
        );

        final travelPhoto = await repo.searchHomepages(
          query: '旅行摄影',
          homepageType: 'travel_photo',
          status: 'published',
          limit: 10,
        );
        expect(
          travelPhoto.map((h) => h.id),
          contains('fixture_homepage_travel_photo_west_lake'),
        );

        final newOriental = await repo.searchHomepages(
          query: '新东方',
          homepageType: 'school',
          status: 'published',
          limit: 10,
        );
        expect(
          newOriental.map((h) => h.id),
          contains('fixture_homepage_school_neworiental'),
        );
        final newOrientalDetail = await repo.getHomepageDetail(
          'fixture_homepage_school_neworiental',
        );
        expect(newOrientalDetail.coverUrl, isNotEmpty);

        final photoSpot = await repo.searchHomepages(
          query: '横竖影像馆取景地',
          homepageType: 'photo_spot',
          status: 'published',
          limit: 10,
        );
        expect(
          photoSpot.map((h) => h.id),
          contains('fixture_homepage_photo_spot_hengshu_studio'),
        );
        final photoSpotDetail = await repo.getHomepageDetail(
          'fixture_homepage_photo_spot_hengshu_studio',
        );
        expect(photoSpotDetail.coverUrl, isNotEmpty);
      },
    );
  });

  group('Alpha fixture typed adapter', () {
    test('每个 adapter 只读取不可变 fixture，不共享可变 command 状态', () async {
      final first = MockHomepageRepository();
      final second = MockHomepageRepository();
      final a = await first.getHomepageDetail('homepage_sight_west_lake');
      final b = await second.getHomepageDetail('homepage_sight_west_lake');

      expect(identical(a, b), isFalse);
      expect(a.canonicalEntityId, 'entity:sight:west_lake');
    });
  });

  group('治理动作归属 Ops portal（B6 裁决）', () {
    test('App HomepageQuery / HomepageCommandWriter 均不超过 10 方法', () {
      // 治理动作（intake/publish/claim review/report review）归 platform-ops；
      // 关注关系唯一归属 user.SubjectFollow 聚合。
      const queryMethods = <String>[
        'searchHomepages',
        'getHomepageDetail',
        'getHomepageShell',
        'getObjectPageBundle',
        'getHomepageReviewSummary',
        'getEntityImpact',
        'getHomepageRelatedGroups',
      ];
      const commandMethods = <String>[
        'suggestHomepageCandidate',
        'createHomepageClaimRequest',
        'updateClaimedHomepageBasics',
        'createHomepageStatusReport',
      ];
      expect(queryMethods, hasLength(7));
      expect(commandMethods, hasLength(4));
      expect(queryMethods.length, lessThanOrEqualTo(10));
      expect(commandMethods.length, lessThanOrEqualTo(10));
    });
  });

  group('RemoteHomepageRepository — related groups & detail JSON', () {
    test('getHomepageRelatedGroups 只解析服务合同 groups 键', () async {
      final client = MockClient((request) async {
        if (request.url.path.endsWith('/related-groups')) {
          return http.Response(
            json.encode({
              'groups': [
                {'circleId': 'c2', 'name': 'RG', 'memberCount': 1},
              ],
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('not found', 404);
      });
      final repo = buildRemoteHomepageRepositoryForTest(
        httpClient: CloudHttpClient(client: client),
        baseUrl: 'https://gw.test',
      );
      final groups = await repo.getHomepageRelatedGroups('h1');
      expect(groups, hasLength(1));
      expect(groups.single.circleId, 'c2');
      expect(groups.single.name, 'RG');
    });

    test('getHomepageRelatedGroups 遇到坏 groups 元素必须失败关闭', () async {
      final client = MockClient((request) async {
        if (request.url.path.endsWith('/related-groups')) {
          return http.Response(
            json.encode({
              'groups': [
                {'circleId': 'c1', 'name': 'G1', 'memberCount': 3},
                'skip-me',
              ],
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('not found', 404);
      });
      final repo = buildRemoteHomepageRepositoryForTest(
        httpClient: CloudHttpClient(client: client),
        baseUrl: 'https://gw.test',
      );
      await expectLater(
        repo.getHomepageRelatedGroups('h1'),
        throwsA(
          isA<CloudException>().having(
            (error) => error.runtimeFailure.code,
            'runtimeFailure.code',
            'APP.CONTRACT.invalid_json',
          ),
        ),
      );
    });

    test('getHomepageRelatedGroups 缺省或空 groups 返回空列表', () async {
      Future<http.Response> respondMissingGroups(
        http.BaseRequest request,
      ) async {
        if (request.url.path.endsWith('/related-groups')) {
          return http.Response(
            '{}',
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('not found', 404);
      }

      Future<http.Response> respondEmptyGroups(http.BaseRequest request) async {
        if (request.url.path.endsWith('/related-groups')) {
          return http.Response(
            '{"groups":[]}',
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('not found', 404);
      }

      for (final handler in <Future<http.Response> Function(http.BaseRequest)>[
        respondMissingGroups,
        respondEmptyGroups,
      ]) {
        final repo = buildRemoteHomepageRepositoryForTest(
          httpClient: CloudHttpClient(client: MockClient(handler)),
          baseUrl: 'https://gw.test',
        );
        final groups = await repo.getHomepageRelatedGroups('h-x');
        expect(groups, isEmpty);
      }
    });

    test('getHomepageDetail 最小 JSON', () async {
      final client = MockClient((request) async {
        final detailPath = EntityApiMetadata.getHomepageDetailPath(
          homepageId: 'h-min',
        );
        if (request.url.path == Uri.parse(detailPath).path) {
          return http.Response(
            json.encode({
              'homepageId': 'h-min',
              'homepageType': 'sight',
              'title': 'Minimal',
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('not found', 404);
      });
      final repo = buildRemoteHomepageRepositoryForTest(
        httpClient: CloudHttpClient(client: client),
        baseUrl: 'https://gw.test',
      );
      final detail = await repo.getHomepageDetail('h-min');
      expect(detail.id, 'h-min');
      expect(detail.homepageType, 'sight');
      expect(detail.title, 'Minimal');
    });

    test('getObjectPageBundle 解析 query 上下文和嵌套 projection', () async {
      Uri? capturedUri;
      final client = MockClient((request) async {
        capturedUri = request.url;
        return http.Response(
          json.encode({
            'objectType': 'homepage',
            'objectId': 'h-bundle',
            'canonicalEntityId': 'entity:h-bundle',
            'title': 'Bundle',
            'objectPageTemplate': 'campus',
            'tagRefs': ['publish/tags/campus'],
            'intersectionReasons': [
              {
                'dimension': 'interest',
                'primaryText': '你们都关注校园摄影',
                'confidenceLabel': '公开资料',
                'tagRefs': ['publish/tags/campus'],
                'totalPointCount': 1,
                'intersectionPoints': [
                  {
                    'pointId': 'ev1',
                    'pointClass': 'fact',
                    'dimension': 'interest',
                    'sourceRef': 'tag',
                    'label': '校园摄影',
                    'displayText': '校园摄影',
                    'visibility': 'public',
                    'count': 1,
                  },
                ],
              },
            ],
            'highlightItems': [
              {'postId': 'p1', 'title': '校园看点'},
            ],
            'relatedObjects': [
              {'circleId': 'c1', 'name': '摄影圈', 'memberCount': 8},
            ],
            'relationEdges': [
              {
                'edgeId': 'e1',
                'edgeType': 'circle_under_entity',
                'sourceObjectType': 'circle',
                'sourceObjectId': 'c1',
                'targetObjectType': 'homepage',
                'targetObjectId': 'h-bundle',
                'canonicalEntityId': 'entity:h-bundle',
                'confidence': 0.9,
              },
            ],
            'assistantContext': {
              'objectType': 'homepage',
              'objectId': 'h-bundle',
              'canonicalEntityId': 'entity:h-bundle',
              'referralSource': 'entity_page',
              'feedRequestId': 'feed-1',
            },
            'rolloutContext': {
              'enabled': true,
              'cohort': 'cohort-a',
              'relationEvidenceEnabled': true,
            },
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });
      final repo = buildRemoteHomepageRepositoryForTest(
        httpClient: CloudHttpClient(client: client),
        baseUrl: 'https://gw.test',
      );

      final bundle = await repo.getObjectPageBundle(
        'h-bundle',
        referralSource: 'entity_page',
        feedRequestId: 'feed-1',
        recommendationTraceId: 'trace-1',
        experimentBucket: 'A',
        rolloutCohort: 'cohort-a',
      );

      expect(capturedUri?.path, '/homepages/h-bundle/object-page-bundle');
      expect(capturedUri?.queryParameters['referralSource'], 'entity_page');
      expect(capturedUri?.queryParameters['feedRequestId'], 'feed-1');
      expect(capturedUri?.queryParameters['recommendationTraceId'], 'trace-1');
      expect(capturedUri?.queryParameters['experimentBucket'], 'A');
      expect(capturedUri?.queryParameters['rolloutCohort'], 'cohort-a');
      expect(bundle.canonicalEntityId, 'entity:h-bundle');
      expect(bundle.intersectionReasons.single.primaryText, '你们都关注校园摄影');
      expect(
        bundle.intersectionReasons.single.intersectionPoints.single.sourceRef,
        'tag',
      );
      expect(bundle.intersectionReasons.single.confidenceLabel, '公开资料');
      expect(bundle.relationEdges.single.edgeType, 'circle_under_entity');
      expect(bundle.assistantContext?.feedRequestId, 'feed-1');
      expect(bundle.rolloutContext?.relationEvidenceEnabled, isTrue);
    });
  });
}
