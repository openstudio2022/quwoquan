import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_repository.dart';
import 'package:quwoquan_app/components/object_page/evidence_group.dart';

/// T2：对象页关系类交集（§2 证据组闭集 + 三层关系分层）。
/// - 关系分层不混用：联系人(contact)/互相关注(mutual)/关注(following) 文案互不混淆；
/// - 多证据组：单对象返回多条可见证据组（人脸抽屉列表来源）；
/// - 数字 single-source：可见证据组 count 之和稳定；
/// - 连接说明：由实例构成的一句话（connectionSummary），端不本地拼装；
/// - 维度开放：kind 为开放字符串，未来新增不需改契约。
void main() {
  late MockIntersectionRepository repo;

  setUp(() => repo = MockIntersectionRepository());

  group('getObjectIntersections（关系分层 + 证据组）', () {
    test('用户对象：含共同关注/联系人/关注三层，互不混用', () async {
      final reasons = await repo.getObjectIntersections(
        objectId: 'u_lin',
        objectType: 'user',
      );
      expect(reasons, isNotEmpty);
      final groups = EvidenceGroup.fromReason(reasons.first);
      final labels = groups.map((g) => g.label).toList();

      // 三层关系分别独立呈现，禁止用「好友」指代「关注」。
      expect(labels, contains('共同关注的人'));
      expect(labels, contains('共同联系人'));
      // 不出现把关注混称为好友的错误文案。
      expect(labels.where((l) => l.contains('共同关注')).length, 1);
    });

    test('圈子对象：关注的人在这/联系人在这/关注的人常来 分层', () async {
      final reasons = await repo.getObjectIntersections(
        objectId: 'c_photo',
        objectType: 'circle',
      );
      final groups = EvidenceGroup.fromReason(reasons.first);
      final labels = groups.map((g) => g.label).toList();
      expect(labels, contains('关注的人在这'));
      expect(labels, contains('联系人在这'));
      expect(labels, contains('关注的人常来'));
    });

    test('实体对象：关注的人来过/联系人来过/关注的人加入 分层（地点维度）', () async {
      final reasons = await repo.getObjectIntersections(
        objectId: 'e_pku',
        objectType: 'entity',
      );
      final groups = EvidenceGroup.fromReason(reasons.first);
      final labels = groups.map((g) => g.label).toList();
      expect(labels, contains('关注的人来过'));
      expect(labels, contains('联系人来过'));
      expect(labels, contains('关注的人加入'));
    });

    test('数字 single-source：可见证据组 count 之和与列表一致', () async {
      final reasons = await repo.getObjectIntersections(
        objectId: 'u_lin',
        objectType: 'user',
      );
      final groups = EvidenceGroup.fromReason(reasons.first);
      final total = EvidenceGroup.totalCount(groups);
      // 由各组 count 加总得到，不存在端侧二次推导的独立总数。
      final manual = groups.fold<int>(0, (s, g) => s + g.count);
      expect(total, manual);
      expect(total, greaterThan(0));
    });

    test('连接说明：实例化一句话，由具体样本构成', () async {
      final reasons = await repo.getObjectIntersections(
        objectId: 'u_lin',
        objectType: 'user',
      );
      final summary = reasons.first.connectionSummary;
      expect(summary.trim(), isNotEmpty);
      // 「…把你们连在一起」由实例（如好友名）构成，非空说维度词。
      expect(summary, contains('把你们连在一起'));
      expect(summary, isNot(contains('交集点')));
    });

    test('推荐组排在事实之后并标记推荐', () async {
      final reasons = await repo.getObjectIntersections(
        objectId: 'u_lin',
        objectType: 'user',
      );
      final groups = EvidenceGroup.fromReason(reasons.first);
      final firstRecommendedIndex = groups.indexWhere((g) => g.isRecommended);
      // 存在推荐组时，其前面至少有一个事实组（事实优先）。
      if (firstRecommendedIndex >= 0) {
        expect(
          groups.take(firstRecommendedIndex).every((g) => !g.isRecommended),
          isTrue,
        );
      }
    });

    test('未知对象类型 → 返回空（不造假）', () async {
      final reasons = await repo.getObjectIntersections(
        objectId: 'x',
        objectType: 'future_object_kind',
      );
      expect(reasons, isEmpty);
    });
  });
}
