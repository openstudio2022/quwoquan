import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';

/// T1 契约测试（会话0 B1 交集理由）。
/// 验收 G2：dimension 为 5 源闭集；端只读展示、无来源时字段空且不编造。
void main() {
  group('IntersectionReason 契约', () {
    test('fromMap 解析全字段', () {
      final r = IntersectionReason.fromMap(<String, dynamic>{
        'dimension': 'identity',
        'tagRefs': <String>['Entity/机构/学校/北京大学'],
        'label': '北京大学',
        'sharedCount': 3,
        'strength': 0.9,
        'displayText': '你们都是北大的',
        'actionType': 'follow',
        'actionTargetId': 'user_x',
        'source': 'entityRef',
      });
      expect(r.dimension, 'identity');
      expect(r.tagRefs, <String>['Entity/机构/学校/北京大学']);
      expect(r.label, '北京大学');
      expect(r.sharedCount, 3);
      expect(r.strength, 0.9);
      expect(r.displayText, '你们都是北大的');
      expect(r.actionType, 'follow');
      expect(r.source, 'entityRef');
    });

    test('无来源时字段为空（UI 不展示理由，禁止编造）', () {
      final r = IntersectionReason.fromMap(<String, dynamic>{});
      expect(r.dimension, '');
      expect(r.tagRefs, isEmpty);
      expect(r.displayText, '');
      expect(r.label, '');
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
        'displayText': '你们有共同好友',
      });
      expect(r.dimension, 'relationship');
      expect(r.relationKind, 'mutual');
      expect(r.relationObjectId, 'user_friend_1');
    });

    test('toMap round-trip 保持字段', () {
      final r = IntersectionReason(
        dimension: 'interest',
        tagRefs: const <String>['Topic/摄影'],
        label: '摄影',
        displayText: '你们都爱摄影',
        actionType: 'view_object',
        source: 'tagRef',
      );
      final r2 = IntersectionReason.fromMap(r.toMap());
      expect(r2.dimension, 'interest');
      expect(r2.tagRefs, const <String>['Topic/摄影']);
      expect(r2.displayText, '你们都爱摄影');
      expect(r2.source, 'tagRef');
    });
  });
}
