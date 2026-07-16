import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';

/// T1 契约测试（会话0 B1 交集理由）。
/// 验收 G2：dimension 为 5 源闭集；端只读展示、无来源时字段空且不编造。
void main() {
  group('IntersectionReason 契约', () {
    test('fromMap 解析全字段（云侧主结论句 primaryText + 计数 totalPointCount）', () {
      final r = IntersectionReason.fromMap(<String, dynamic>{
        'dimension': 'identity',
        'tagRefs': <String>['Entity/机构/学校/北京大学'],
        'displayName': '北京大学',
        'totalPointCount': 3,
        'strength': 0.9,
        'primaryText': '推荐你了解北京大学',
        'primarySpans': <Map<String, dynamic>>[
          <String, dynamic>{'text': '推荐你了解', 'role': 'plain'},
          <String, dynamic>{
            'text': '北京大学',
            'role': 'object',
            'target': <String, dynamic>{
              'objectType': 'homepage',
              'objectId': 'homepage_pku',
              'objectKind': 'school',
              'routeId': 'homepageDetail',
            },
          },
        ],
        'actionType': 'view_object',
        'actionTargetId': 'homepage_pku',
        'source': 'entityRef',
      });
      expect(r.dimension, 'identity');
      expect(r.tagRefs, <String>['Entity/机构/学校/北京大学']);
      expect(r.displayName, '北京大学');
      expect(r.totalPointCount, 3);
      expect(r.strength, 0.9);
      expect(r.primaryText, '推荐你了解北京大学');
      expect(r.primarySpans, hasLength(2));
      expect(r.primarySpans.last.target?.objectType, 'homepage');
      expect(r.actionType, 'view_object');
      expect(r.source, 'entityRef');
    });

    test('无来源时字段为空（UI 不展示理由，禁止编造）', () {
      final r = IntersectionReason.fromMap(<String, dynamic>{});
      expect(r.dimension, '');
      expect(r.tagRefs, isEmpty);
      expect(r.primaryText, '');
      expect(r.connectionSummary, '');
    });

    test('dimension 为 5 源闭集', () {
      const valid = <String>{
        'identity',
        'location',
        'content',
        'interest',
        'relationship',
      };
      for (final d in valid) {
        final r = IntersectionReason.fromMap(<String, dynamic>{'dimension': d});
        expect(r.dimension, d);
      }
    });

    test('relationship 维度走 relationKind + relationObjectId', () {
      final r = IntersectionReason.fromMap(<String, dynamic>{
        'dimension': 'relationship',
        'relationKind': 'mutual',
        'relationObjectId': 'user_friend_1',
        'primaryText': '你们有共同好友',
      });
      expect(r.dimension, 'relationship');
      expect(r.relationKind, 'mutual');
      expect(r.relationObjectId, 'user_friend_1');
    });

    test('解析人数句逐人证据 actorEvidence', () {
      final r = IntersectionReason.fromMap(<String, dynamic>{
        'primaryText': '林清越等2位联系人关注了这篇内容',
        'actionTargetId': 'post_1',
        'representativeActor': <String, dynamic>{
          'actorId': 'u_lin',
          'displayName': '林清越',
          'relationLabel': '联系人',
          'target': <String, dynamic>{
            'objectType': 'user',
            'objectId': 'u_lin',
            'objectKind': 'person',
            'routeId': 'userProfile',
          },
        },
        'primarySpans': <Map<String, dynamic>>[
          <String, dynamic>{
            'text': '林清越',
            'role': 'object',
            'target': <String, dynamic>{
              'objectType': 'user',
              'objectId': 'u_lin',
              'objectKind': 'person',
              'routeId': 'userProfile',
            },
          },
          <String, dynamic>{'text': '等2位联系人关注了', 'role': 'plain'},
          <String, dynamic>{
            'text': '这篇内容',
            'role': 'object',
            'target': <String, dynamic>{
              'objectType': 'post',
              'objectId': 'post_1',
              'objectKind': 'post',
              'routeId': 'postDetail',
            },
          },
        ],
        'actorEvidenceTotalCount': 2,
        'actorEvidenceCompleteness': 'complete',
        'actorEvidence': <Map<String, dynamic>>[
          <String, dynamic>{
            'actorId': 'u_lin',
            'displayName': '林清越',
            'relationLabel': '联系人',
            'relationSourceRef': 'contact',
            'sourcePointId': 'p_contact',
            'sourceRef': 'commonContact',
            'actionSummaryText': '点赞了这条记录',
            'likeCount': 1,
            'target': <String, dynamic>{
              'objectType': 'user',
              'objectId': 'u_lin',
              'objectKind': 'person',
              'routeId': 'userProfile',
            },
            'evidenceRank': 5,
            'snapshotVersion': 'snap_home_1',
            'sortKey': 1,
          },
          <String, dynamic>{
            'actorId': 'u_zhou',
            'displayName': '周屿',
            'relationLabel': '你关注的人',
            'relationSourceRef': 'followee',
            'sourcePointId': 'p_followee',
            'sourceRef': 'sharedFollowees',
            'actionSummaryText': '评论了这条记录',
            'commentCount': 1,
            'evidenceRank': 10,
            'snapshotVersion': 'snap_home_1',
            'sortKey': 2,
          },
        ],
      });

      expect(r.actorEvidenceTotalCount, 2);
      expect(r.actorEvidenceCompleteness, 'complete');
      expect(r.actorEvidence, hasLength(2));
      expect(r.actorEvidence.first.relationLabel, '联系人');
      expect(r.actorEvidence.first.actionSummaryText, '点赞了这条记录');
      expect(r.actorEvidence.first.likeCount, 1);
      expect(r.actorEvidence.first.target?.routeId, 'userProfile');
      expect(r.actorEvidence.last.relationLabel, '你关注的人');
      expect(r.actorEvidence.last.commentCount, 1);
      expect(r.representativeActor?.displayName, '林清越');
      expect(r.representativeActor?.target?.objectType, 'user');
      expect(r.primarySpans.map((span) => span.text).join(), r.primaryText);
    });

    test('toMap round-trip 保持字段', () {
      final r = IntersectionReason(
        dimension: 'interest',
        tagRefs: const <String>['Topic/摄影'],
        displayName: '摄影',
        primaryText: '你们都爱摄影',
        actionType: 'view_object',
        source: 'tagRef',
      );
      final r2 = IntersectionReason.fromMap(r.toMap());
      expect(r2.dimension, 'interest');
      expect(r2.tagRefs, const <String>['Topic/摄影']);
      expect(r2.primaryText, '你们都爱摄影');
      expect(r2.source, 'tagRef');
    });
  });
}
