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
      final detail = Circle.fromWire(_circleWire());
      final search = CircleSearchResultView.fromWire(<String, Object?>{
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
      final stats = CircleStatsWire.fromWire(<String, Object?>{
        'circleId': 'circle-1',
        'memberCount': 12,
        'postCount': 3,
        'discussionCount': 2,
        'weeklyActiveCount': 8,
        'likeCount': 5,
        'storageUsedBytes': 1024,
        'storageQuotaBytes': 4096,
      });

      expect(detail.id, 'circle-1');
      expect(detail.tags, <String>['户外', '周末']);
      expect(search.items!.single.name, '城市露营');
      expect(search.facetBuckets!.single.facetCount, 1);
      expect(search.cursor, 'next');
      expect(stats.weeklyActiveCount, 8);
    });

    test('decodes feed and impact without exposing dynamic maps', () {
      final feed = decodeCircleFeedPageSlice(<String, Object?>{
        'items': <Object?>[
          <String, Object?>{
            ..._feedItemWire(contentType: 'video'),
            'title': '周末营地',
            'featured': true,
          },
        ],
        'cursor': null,
      });
      final impact = CircleImpactSummary.fromWire(<String, Object?>{
        'circleId': 'circle-1',
        'total': 1,
        'items': <Object?>[
          <String, Object?>{
            ..._impactItemWire(),
          },
        ],
      });

      expect(feed.items.single.postId, 'post-1');
      expect(feed.items.single.contentType, 'video');
      expect(feed.items.single.circleId, 'circle-1');
      expect(feed.items.single.featured, isTrue);
      expect(impact.total, 1);
      expect(impact.items.single.impactId, 'impact-1');
    });

    test('decodes aggregate discovery feed into circles and typed posts', () {
      final feed = decodeCircleDiscoveryFeedPageSlice(<String, Object?>{
        'circles': <Object?>[
          _circleWire(),
        ],
        'items': <Object?>[
          _feedItemWire(contentType: 'image'),
        ],
        'cursor': 'next',
      });

      expect(feed.circles.single.id, 'circle-1');
      expect(feed.items.single.postId, 'post-1');
      expect(feed.cursor, 'next');
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

Map<String, Object?> _circleWire() => <String, Object?>{
  'id': 'circle-1',
  'name': '城市露营',
  'ownerId': 'persona-1',
  'memberCount': 12,
  'postCount': 3,
  'weeklyActiveCount': 8,
  'version': 1,
  'tags': <Object?>['户外', '周末'],
  'status': 'active',
  'visibility': 'public',
  'joinPolicy': 'open',
  'kind': 'interest',
  'displaySubjectType': 'circle',
  'followEnabled': true,
  'autoSyncChat': true,
  'storageUsedBytes': 1024,
  'storageQuotaBytes': 4096,
  'createdAt': '2026-08-01T00:00:00Z',
  'updatedAt': '2026-08-01T00:00:00Z',
};

Map<String, Object?> _feedItemWire({required String contentType}) =>
    <String, Object?>{
      'circleId': 'circle-1',
      'placementId': 'placement-1',
      'postId': 'post-1',
      'contentType': contentType,
      'authorVerified': false,
      'likeCount': 0,
      'commentCount': 0,
      'shareCount': 0,
      'pinned': false,
      'featured': false,
    };

Map<String, Object?> _impactItemWire() => <String, Object?>{
  'helpType': 'connection',
  'action': 'visit',
  'intersectionDimension': 'interest',
  'tagRef': 'tag:camping',
  'source': 'circle_activity',
  'count': 1,
  'primaryText': '帮助一位同好找到营地',
  'subtitleText': '城市露营',
  'impactId': 'impact-1',
  'primarySpans': <Object?>[],
  'sampleVisuals': <Object?>[],
  'actionHints': <Object?>[],
  'evidenceSnapshotId': 'evidence-1',
  'countObjectKind': 'circle',
  'iconKey': 'connection',
};
