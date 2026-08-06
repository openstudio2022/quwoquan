import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('实体主页 generated operation ABI', () {
    test('查询编码只输出 metadata 声明的 path 与 query', () {
      final search = encodeEntityHomepageSearchHomepagesGeneratedRequest(
        HomepageSearchQuery(
          query: '普陀山',
          homepageType: 'sight',
          city: '舟山',
          limit: 20,
        ),
      );
      expect(search.pathParameters, isEmpty);
      expect(search.queryParameters, <String, String>{
        'query': '普陀山',
        'homepageType': 'sight',
        'city': '舟山',
        'limit': '20',
      });

      final bundle = encodeEntityHomepageGetObjectPageBundleGeneratedRequest(
        HomepageObjectPageBundleQuery(
          homepageId: 'homepage-1',
          referralSource: 'search',
          recommendationTraceId: 'trace-1',
        ),
      );
      expect(bundle.pathParameters, <String, String>{
        'homepageId': 'homepage-1',
      });
      expect(bundle.queryParameters, <String, String>{
        'referralSource': 'search',
        'recommendationTraceId': 'trace-1',
      });
    });

    test('地点提升候选将 canonical source place identity 送到命令', () {
      final request =
          encodeEntityHomepageSuggestHomepageCandidateGeneratedRequest(
            SuggestHomepageCandidateCommand(
              title: '断桥残雪',
              homepageType: 'sight',
              sourcePlaceId: 'place_0123456789abcdef',
            ),
          );

      expect(request.body, <String, Object?>{
        'title': '断桥残雪',
        'homepageType': 'sight',
        'sourcePlaceId': 'place_0123456789abcdef',
      });
    });

    test('主页详情仅以 homepageId 为唯一主页身份并严格解码', () {
      final detail = decodeHomepageDetailView(<String, Object?>{
        'homepageId': 'homepage-1',
        'homepageType': 'sight',
        'title': '普陀山',
        'status': 'published',
        'claimStatus': 'unclaimed',
        'categoryTags': <String>['travel', 'sight'],
        'viewerFollow': <String, Object?>{
          'viewerFollowsHomepage': false,
          'followerCount': 12,
        },
        'verified': false,
        'ratingCount': 0,
        'contentPreview': <Object?>[],
        'questionPreview': <Object?>[],
        'relatedGroups': <Object?>[],
        'relationEdges': <Object?>[],
        'introductionAssets': <Object?>[],
        'sourceUrls': <String>[],
        'createdAt': '2026-07-17T00:00:00Z',
        'updatedAt': '2026-07-17T00:00:00Z',
      });

      expect(detail.homepageId, 'homepage-1');
      expect(detail.title, '普陀山');
      expect(detail.categoryTags, <String>['travel', 'sight']);
      expect(detail.updatedAt, DateTime.utc(2026, 7, 17));
      expect(
        () => decodeHomepageDetailView(<String, Object?>{
          'id': 'homepage-by-id',
          'homepageType': 'sight',
          'title': '拒绝 id',
        }),
        throwsFormatException,
      );
      expect(
        () => decodeHomepageDetailView(<String, Object?>{
          '_id': 'retired-storage-key',
          'homepageType': 'sight',
          'title': '拒绝 _id',
        }),
        throwsFormatException,
      );
    });

    test('认领与状态上报结果只接受 metadata canonical 业务键', () {
      final claim = decodeHomepageClaimRequestView(<String, Object?>{
        'claimRequestId': 'claim-1',
        'homepageId': 'homepage-1',
        'requesterPersonaId': 'persona-1',
        'claimTier': 'verified',
        'status': 'pending_review',
        'createdAt': '2026-07-17T00:00:00Z',
      });
      final report = decodeHomepageStatusReportView(<String, Object?>{
        'reportId': 'report-1',
        'homepageId': 'homepage-1',
        'reporterPersonaId': 'persona-2',
        'reason': 'offline',
        'status': 'pending_review',
        'createdAt': '2026-07-17T00:00:00Z',
      });

      expect(claim.claimRequestId, 'claim-1');
      expect(report.reportId, 'report-1');
      expect(
        () => decodeHomepageClaimRequestView(<String, Object?>{
          'id': 'retired-claim-key',
          'homepageId': 'homepage-1',
          'requesterPersonaId': 'persona-1',
          'claimTier': 'verified',
          'status': 'pending_review',
        }),
        throwsFormatException,
      );
      expect(
        () => decodeHomepageStatusReportView(<String, Object?>{
          'id': 'retired-report-key',
          'homepageId': 'homepage-1',
          'reporterPersonaId': 'persona-2',
          'reason': 'offline',
          'status': 'pending_review',
        }),
        throwsFormatException,
      );
    });

    test('搜索、对象页和关联群组均返回不可变强类型投影', () {
      final search = decodeHomepageSearchSlice(<String, Object?>{
        'items': <Object?>[
          <String, Object?>{
            'homepageId': 'homepage-1',
            'homepageType': 'sight',
            'canonicalEntityId': 'entity:putuoshan',
            'title': '普陀山',
            'status': 'published',
            'ratingCount': 8,
          },
        ],
        'nextCursor': 'cursor-1',
      });
      expect(search.items.single.homepageId, 'homepage-1');
      expect(search.nextCursor, 'cursor-1');

      final objectPage = decodeObjectPageBundle(<String, Object?>{
        'objectType': 'homepage',
        'objectId': 'homepage-1',
        'canonicalEntityId': 'entity:putuoshan',
        'title': '普陀山',
        'objectPageTemplate': 'homepage-default',
        'tagRefs': <String>['travel'],
        'stats': <String, Object?>{'followers': 12},
        'intersectionReasons': <Object?>[],
        'highlightItems': <Object?>[],
        'contentSections': <String, Object?>{},
        'relatedObjects': <Object?>[],
        'relationEdges': <Object?>[],
      });
      expect(objectPage.stats['followers'], 12);
      expect(objectPage.intersectionReasons, isEmpty);

      final groups = decodeHomepageRelatedGroupSummaryView(<String, Object?>{
        'groups': <Object?>[
          <String, Object?>{
            'circleId': 'circle-1',
            'name': '海岛旅行',
            'memberCount': 20,
            'ownerUserId': 'user-1',
            'ownerDisplayNameSnapshot': '主理人',
            'ownerAvatarUrlSnapshot': '',
            'evidenceSnapshotId': 'circle:circle-1:members',
          },
        ],
      });
      expect(groups.groups!.single.circleId, 'circle-1');
      expect(
        () => decodeHomepageRelatedGroupSummaryView(<String, Object?>{
          'groups': <Object?>['invalid'],
        }),
        throwsFormatException,
      );
    });
  });
}
