import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('Circle generated query contracts', () {
    test('encodes list, search and object query parameters', () {
      expect(
        encodeCircleCircleListCirclesGeneratedRequest(
          const CircleListQuery(
            category: 'interest',
            cursor: 'next',
            limit: 50,
          ),
        ).queryParameters,
        <String, String>{
          'category': 'interest',
          'cursor': 'next',
          'limit': '50',
        },
      );
      expect(
        encodeCircleCircleSearchCirclesGeneratedRequest(
          const CircleSearchQuery(query: '露营', limit: 10),
        ).queryParameters,
        <String, String>{'query': '露营', 'limit': '10'},
      );
      expect(
        encodeCircleCircleGetCircleGeneratedRequest(
          const CircleDetailQuery(circleId: 'circle-1'),
        ).pathParameters,
        <String, String>{'circleId': 'circle-1'},
      );
      final personaCircles =
          encodeCircleCircleMembershipListPersonaCirclesGeneratedRequest(
            PersonaCircleListQuery(
              personaId: 'persona-1',
              query: ' 摄影 ',
              cursor: 'membership-20',
              limit: 20,
            ),
          );
      expect(personaCircles.pathParameters, <String, String>{
        'personaId': 'persona-1',
      });
      expect(personaCircles.queryParameters, <String, String>{
        'limit': '20',
        'cursor': 'membership-20',
        'query': '摄影',
      });
      expect(
        encodeCircleCircleListCircleDiscoveryFeedGeneratedRequest(
          const CircleDiscoveryFeedQuery(
            category: 'campus',
            subCategory: 'photography',
            scope: CircleDiscoveryFeedScope.mine,
            cursor: 'next',
            limit: 30,
          ),
        ).queryParameters,
        <String, String>{
          'category': 'campus',
          'subCategory': 'photography',
          'scope': 'mine',
          'cursor': 'next',
          'limit': '30',
          'sort': 'recommended',
        },
      );
    });

    test('decodes detail, search and stats into typed slices', () {
      final detail = decodeCircleProjection(<String, Object?>{
        'id': 'circle-1',
        'name': '城市露营',
        'ownerId': 'persona-1',
        'memberCount': 12,
        'tags': <Object?>['户外', '周末'],
        'status': 'active',
        'visibility': 'public',
        'joinPolicy': 'open',
        'kind': 'interest',
        'displaySubjectType': 'circle',
      });
      final search = decodeCircleSearchResultSlice(<String, Object?>{
        'items': <Object?>[
          <String, Object?>{
            'circleId': 'circle-1',
            'name': '城市露营',
            'memberCount': 12,
            'postCount': 3,
          },
        ],
        'facetBuckets': <Object?>[
          <String, Object?>{
            'facetKey': 'interest',
            'label': '兴趣',
            'facetCount': 1,
          },
        ],
        'cursor': 'next',
      });
      final stats = decodeCircleStatsSlice(<String, Object?>{
        'memberCount': 12,
        'postCount': 3,
        'weeklyActiveCount': 8,
      });

      expect(detail.circleId, 'circle-1');
      expect(detail.tags, <String>['户外', '周末']);
      expect(search.items.single.name, '城市露营');
      expect(search.facetBuckets.single.facetCount, 1);
      expect(search.nextCursor, 'next');
      expect(stats.weeklyActiveCount, 8);
    });

    test('decodes feed and impact without exposing dynamic maps', () {
      final feed = decodeCircleFeedPageSlice(<String, Object?>{
        'items': <Object?>[
          <String, Object?>{
            'circleId': 'circle-1',
            'placementId': 'placement-1',
            'postId': 'post-1',
            'contentType': 'video',
            'title': '周末营地',
            'featured': true,
          },
        ],
        'cursor': null,
      });
      final impact = decodeCircleImpactSlice(<String, Object?>{
        'circleId': 'circle-1',
        'total': 1,
        'items': <Object?>[
          <String, Object?>{
            'helpType': 'connection',
            'action': 'visit',
            'count': 1,
            'primaryText': '帮助一位同好找到营地',
            'impactId': 'impact-1',
          },
        ],
      });

      expect(feed.items.single.post.postId, 'post-1');
      expect(feed.items.single.post.contentType, 'video');
      expect(feed.items.single.circleId, 'circle-1');
      expect(feed.items.single.featured, isTrue);
      expect(impact.total, 1);
      expect(impact.items.single.impactId, 'impact-1');
    });

    test('decodes aggregate discovery feed into circles and typed posts', () {
      final feed = decodeCircleDiscoveryFeedPageSlice(<String, Object?>{
        'circles': <Object?>[
          <String, Object?>{
            'id': 'circle-1',
            'name': '城市露营',
            'ownerId': 'persona-1',
            'status': 'active',
            'visibility': 'public',
            'joinPolicy': 'open',
            'kind': 'interest',
            'displaySubjectType': 'circle',
          },
        ],
        'items': <Object?>[
          <String, Object?>{
            'circleId': 'circle-1',
            'placementId': 'placement-1',
            'postId': 'post-1',
            'contentType': 'image',
          },
        ],
        'cursor': 'next',
      });

      expect(feed.circles.single.circleId, 'circle-1');
      expect(feed.items.single.post.postId, 'post-1');
      expect(feed.nextCursor, 'next');
    });

    test('rejects feed items without required placementId', () {
      expect(
        () => decodeCircleFeedPageSlice(<String, Object?>{
          'items': <Object?>[
            <String, Object?>{
              'circleId': 'circle-1',
              'postId': 'post-1',
              'contentType': 'image',
            },
          ],
        }),
        throwsA(isA<FormatException>()),
      );
    });
  });
}
