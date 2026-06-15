/// L1a Entity/Homepage：Mock DTO 形状 + Remote review 请求体与 metadata writable_fields 对齐
library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_homepage_mutation_wires.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import 'package:quwoquan_app/cloud/services/entity/mock/homepage_mock_data.dart';

void main() {
  test(
    'CloudResponseDecoder.mapListFirstPresent 优先使用 groups 而非 relatedGroups',
    () {
      final obj = <String, dynamic>{
        'groups': [
          {'circleId': 'g', 'name': 'FromGroups'},
        ],
        'relatedGroups': [
          {'circleId': 'r', 'name': 'FromRelated'},
        ],
      };
      final rows = CloudResponseDecoder.mapListFirstPresent(obj, const <String>[
        'groups',
        'relatedGroups',
      ]);
      expect(rows, hasLength(1));
      expect(rows.single['circleId'], 'g');
    },
  );

  group('MockHomepageRepository', () {
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
      expect(detail.reviewSummary?.dimensionScores, isNotEmpty);

      final shell = await repo.getHomepageShell(id);
      expect(shell.homepage.id, id);
      expect(shell.relatedGroups, isNotEmpty);

      final review = await repo.getHomepageReviewSummary(id);
      expect(review.ratingCount, greaterThan(0));
      expect(review.dimensionScores, isNotEmpty);

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
      expect(bundle.intersectionReasons, isNotEmpty);
      expect(bundle.intersections, isNotEmpty);
      expect(bundle.intersections.first.evidenceItems, isNotEmpty);
      expect(bundle.intersections.first.confidenceLabel, isNotEmpty);
      expect(bundle.highlightItems, isNotEmpty);
      expect(bundle.relatedObjects, isNotEmpty);
      expect(bundle.relationEdges, isNotEmpty);
      expect(bundle.assistantContext?.referralSource, 'entity_page');
      expect(bundle.assistantContext?.feedRequestId, 'feed-1');
      expect(bundle.assistantContext?.relationEdgeIds, isNotEmpty);
      expect(bundle.rolloutContext?.cohort, 'city-hz');
      expect(bundle.rolloutContext?.relationEvidenceEnabled, isTrue);
    });

    test(
      'getHomepageDetail 支持 homepageId / canonicalEntityId / 数据工程 entityRef',
      () async {
        const homepageId = 'homepage_sight_emeishan';
        final byHomepageId = await repo.getHomepageDetail(homepageId);
        expect(byHomepageId.title, '峨眉山');

        final byCanonical = await repo.getHomepageDetail(
          'entity:sight:homepage_sight_emeishan',
        );
        expect(byCanonical.id, homepageId);

        final byEntityRef = await repo.getHomepageDetail('Entity/旅行/景区/峨眉山');
        expect(byEntityRef.id, homepageId);

        final bundle = await repo.getObjectPageBundle('Entity/旅行/景区/峨眉山');
        expect(bundle.objectId, homepageId);
        expect(bundle.highlightItems, isNotEmpty);
        expect(bundle.relatedObjects, isNotEmpty);
      },
    );

    test('getHomepageRelatedGroups 缺省 groups 时返回空列表', () async {
      final r = MockHomepageRepository();
      final created = await r.intakeHomepageCandidate(
        draft: const HomepageSuggestionDraft(
          title: '仅测相关群空',
          homepageType: 'storefront',
          city: '上海',
        ),
      );
      final emptyGroups = await r.getHomepageRelatedGroups(created.id);
      expect(emptyGroups, isEmpty);
    });

    test('followHomepage / unfollowHomepage 更新关注态与计数', () async {
      const id = 'homepage_sight_west_lake';
      final before = await repo.getHomepageDetail(id);
      final followed = await repo.followHomepage(id);
      expect(followed.viewerFollowsHomepage, isTrue);
      expect(followed.followerCount, before.followerCount + 1);

      final unfollowed = await repo.unfollowHomepage(id);
      expect(unfollowed.viewerFollowsHomepage, isFalse);
      expect(unfollowed.followerCount, before.followerCount);
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
      },
    );
  });

  group('HomepageMockData 强类型种子', () {
    test('cloneHomepageSeeds 深拷贝与静态模板隔离', () {
      final a = HomepageMockData.cloneHomepageSeeds();
      final b = HomepageMockData.cloneHomepageSeeds();
      expect(
        identical(a.first, HomepageMockData.homepageDetailTemplates.first),
        isFalse,
      );
      expect(identical(a.first.categoryTags, b.first.categoryTags), isFalse);
    });
  });

  group('RemoteHomepageRepository — review 请求体键', () {
    test('reviewHomepageClaimRequest body 仅含 status 与可选 reviewNote', () async {
      String? capturedBody;
      final client = MockClient((request) async {
        capturedBody = request.body;
        return http.Response(
          '{"_id":"c1","homepageId":"h1","requesterUserId":"u","claimTier":"basic","status":"approved"}',
          200,
          headers: {'content-type': 'application/json'},
        );
      });
      final repo = RemoteHomepageRepository(
        httpClient: CloudHttpClient(client: client),
        baseUrl: 'https://gw.test',
      );
      await repo.reviewHomepageClaimRequest(
        homepageId: 'h1',
        claimRequestId: 'c1',
        status: 'approved',
        reviewNote: 'ok',
      );
      expect(capturedBody, isNotNull);
      final map = json.decode(capturedBody!) as Map<String, dynamic>;
      expect(map.keys.toSet(), containsAll(<String>['status', 'reviewNote']));
      expect(map['status'], 'approved');
      expect(map['reviewNote'], 'ok');

      final wire = ReviewHomepageClaimRequestWire.fromMap(map);
      expect(wire.toWire(), equals(map));
    });

    test('reviewHomepageStatusReport body 无 reviewNote 时不含该键', () async {
      String? capturedBody;
      final client = MockClient((request) async {
        capturedBody = request.body;
        return http.Response(
          '{"_id":"r1","homepageId":"h1","reason":"x","status":"dismissed"}',
          200,
          headers: {'content-type': 'application/json'},
        );
      });
      final repo = RemoteHomepageRepository(
        httpClient: CloudHttpClient(client: client),
        baseUrl: 'https://gw.test',
      );
      await repo.reviewHomepageStatusReport(
        homepageId: 'h1',
        reportId: 'r1',
        status: 'dismissed',
      );
      final map = json.decode(capturedBody!) as Map<String, dynamic>;
      expect(map.keys.toList(), equals(<String>['status']));
      expect(
        ReviewHomepageStatusReportWire(status: 'dismissed').toWire(),
        equals(<String, dynamic>{'status': 'dismissed'}),
      );
    });
  });

  group('RemoteHomepageRepository — related groups & detail JSON', () {
    test(
      'getHomepageRelatedGroups 解析 relatedGroups 键（与 groups 等价优先级）',
      () async {
        final client = MockClient((request) async {
          if (request.url.path.endsWith('/related-groups')) {
            return http.Response(
              json.encode({
                'relatedGroups': [
                  {'circleId': 'c2', 'name': 'RG', 'memberCount': 1},
                ],
              }),
              200,
              headers: {'content-type': 'application/json'},
            );
          }
          return http.Response('not found', 404);
        });
        final repo = RemoteHomepageRepository(
          httpClient: CloudHttpClient(client: client),
          baseUrl: 'https://gw.test',
        );
        final groups = await repo.getHomepageRelatedGroups('h1');
        expect(groups, hasLength(1));
        expect(groups.single.circleId, 'c2');
        expect(groups.single.name, 'RG');
      },
    );

    test('getHomepageRelatedGroups 解析 groups 并跳过非 Map 元素', () async {
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
      final repo = RemoteHomepageRepository(
        httpClient: CloudHttpClient(client: client),
        baseUrl: 'https://gw.test',
      );
      final groups = await repo.getHomepageRelatedGroups('h1');
      expect(groups, hasLength(1));
      expect(groups.single.circleId, 'c1');
      expect(groups.single.name, 'G1');
      expect(groups.single.memberCount, 3);
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
        final repo = RemoteHomepageRepository(
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
      final repo = RemoteHomepageRepository(
        httpClient: CloudHttpClient(client: client),
        baseUrl: 'https://gw.test',
      );
      final detail = await repo.getHomepageDetail('h-min');
      expect(detail.id, 'h-min');
      expect(detail.homepageType, 'sight');
      expect(detail.title, 'Minimal');
    });

    test('followHomepage / unfollowHomepage 使用 metadata 路径并解析关注态', () async {
      final methods = <String>[];
      final paths = <String>[];
      final client = MockClient((request) async {
        methods.add(request.method);
        paths.add(request.url.path);
        return http.Response(
          json.encode({
            'homepageId': 'h-follow',
            'homepageType': 'sight',
            'title': 'Followable',
            'viewerFollowsHomepage': request.method == 'POST',
            'followerCount': request.method == 'POST' ? 12 : 11,
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });
      final repo = RemoteHomepageRepository(
        httpClient: CloudHttpClient(client: client),
        baseUrl: 'https://gw.test',
      );

      final followed = await repo.followHomepage('h-follow');
      final unfollowed = await repo.unfollowHomepage('h-follow');

      expect(methods, <String>['POST', 'DELETE']);
      expect(paths, <String>[
        EntityApiMetadata.followHomepagePath(homepageId: 'h-follow'),
        EntityApiMetadata.unfollowHomepagePath(homepageId: 'h-follow'),
      ]);
      expect(followed.viewerFollowsHomepage, isTrue);
      expect(followed.followerCount, 12);
      expect(unfollowed.viewerFollowsHomepage, isFalse);
      expect(unfollowed.followerCount, 11);
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
            'tagRefs': ['publish/v1/tags/campus'],
            'intersectionReasons': [
              {
                'dimension': 'interest',
                'displayText': '你们都关注校园摄影',
                'tagRefs': ['publish/v1/tags/campus'],
                'sharedCount': 1,
              },
            ],
            'intersections': [
              {
                'intersectionId': 'i1',
                'dimension': 'interest',
                'objectKind': 'homepage',
                'objectId': 'h-bundle',
                'shortLabel': '共同关注',
                'evidenceLabel': '校园摄影',
                'confidenceLabel': '公开资料',
                'tagRefs': ['publish/v1/tags/campus'],
                'evidenceItems': [
                  {
                    'evidenceId': 'ev1',
                    'evidenceType': 'tag',
                    'evidenceObjectId': 'publish/v1/tags/campus',
                    'evidenceLabel': '校园摄影',
                    'source': 'tagRef',
                    'visibility': 'public',
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
      final repo = RemoteHomepageRepository(
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

      expect(capturedUri?.path, '/v1/homepages/h-bundle/object-page-bundle');
      expect(capturedUri?.queryParameters['referralSource'], 'entity_page');
      expect(capturedUri?.queryParameters['feedRequestId'], 'feed-1');
      expect(capturedUri?.queryParameters['recommendationTraceId'], 'trace-1');
      expect(capturedUri?.queryParameters['experimentBucket'], 'A');
      expect(capturedUri?.queryParameters['rolloutCohort'], 'cohort-a');
      expect(bundle.canonicalEntityId, 'entity:h-bundle');
      expect(bundle.intersectionReasons.single.displayText, '你们都关注校园摄影');
      expect(
        bundle.intersections.single.evidenceItems.single.evidenceType,
        'tag',
      );
      expect(bundle.intersections.single.confidenceLabel, '公开资料');
      expect(bundle.relationEdges.single.edgeType, 'circle_under_entity');
      expect(bundle.assistantContext?.feedRequestId, 'feed-1');
      expect(bundle.rolloutContext?.relationEvidenceEnabled, isTrue);
    });
  });
}
