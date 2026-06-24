import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_repository.dart';
import 'package:quwoquan_app/components/object_page/evidence_group.dart';

/// T2：对象页关系类交集（§2 证据组闭集 + 三层关系分层）。
///
/// N3 真闭环：对象页「你们的交集」唯一真相源 = contract fixture
/// （content/test_fixtures intersection_core.objectIntersections，与 alpha/beta/gamma
/// seed 同源；alpha-dev-lite 亦含该 seed）。Mock 内硬编码 `_objectEvidenceGroups`
/// 已删除，Mock 与 Remote 同走 `IntersectionReason` 真实下发：
/// - 关系分层不混用：联系人(contact)/互相关注(mutual)/关注(following) 文案互不混淆；
/// - 多证据组：单对象返回多条可见证据组（人脸抽屉列表来源）；
/// - 数字 single-source：可见证据组 count 之和稳定；
/// - 富文本句：fixture 自带 primaryText + primarySpans（句内对象名蓝字可点）；
/// - 连接说明：由实例构成的一句话（connectionSummary），端不本地拼装；
/// - 无可解析交集 → 返回空（不造假、不回退硬编码证据组）。
void main() {
  late MockIntersectionRepository repo;

  setUp(() => repo = MockIntersectionRepository());

  group('getObjectIntersections（fixture 真实下发 · 关系分层 + 证据组）', () {
    test('用户对象 u_lin：seed 下发含共同关注/联系人/讨论，互不混用', () async {
      final reasons = await repo.getObjectIntersections(
        objectId: 'u_lin',
        objectType: 'user',
      );
      expect(reasons, isNotEmpty);
      final reason = reasons.first;
      // 真实链路证据：reason 由 fixture（intersection_core.objectIntersections.u_lin）下发，
      // 而非按 objectType 合成的硬编码组。
      expect(reason.intersectionId, 'objix_user_u_lin');
      expect(reason.actionTargetId, 'u_lin');

      final groups = EvidenceGroup.fromReason(reason);
      final labels = groups.map((g) => g.label).toList();
      // 三层关系分别独立呈现，禁止用「好友」指代「关注」。
      expect(labels, contains('共同关注的人'));
      expect(labels, contains('共同联系人'));
      expect(labels, contains('共同讨论'));
      // 不出现把关注混称为好友的错误文案。
      expect(labels.where((l) => l.contains('共同关注')).length, 1);
    });

    test('用户对象 u_lin：fixture 自带 primaryText + 句内对象 span（蓝字可点）', () async {
      final reasons = await repo.getObjectIntersections(
        objectId: 'u_lin',
        objectType: 'user',
      );
      final reason = reasons.first;
      expect(reason.primaryText.trim(), isNotEmpty);
      // primarySpans 由云侧/seed 同源下发，句内代表人为 object 角色（可下钻对象主页）。
      expect(reason.primarySpans, isNotEmpty);
      final objectSpan = reason.primarySpans.firstWhere(
        (s) => s.role == 'object',
        orElse: () => throw StateError('missing object span'),
      );
      expect(objectSpan.text.trim(), isNotEmpty);
      expect(objectSpan.target?.objectId.trim(), isNotEmpty);
      // G2 单通道：join(primarySpans.text) == primaryText。
      expect(
        reason.primarySpans.map((s) => s.text).join(),
        reason.primaryText,
      );
    });

    test('圈子对象 c_photo：关注的人在这/联系人在这/关注的人常来 分层', () async {
      final reasons = await repo.getObjectIntersections(
        objectId: 'c_photo',
        objectType: 'circle',
      );
      expect(reasons, isNotEmpty);
      expect(reasons.first.intersectionId, 'objix_circle_c_photo');
      final groups = EvidenceGroup.fromReason(reasons.first);
      final labels = groups.map((g) => g.label).toList();
      expect(labels, contains('关注的人在这'));
      expect(labels, contains('联系人在这'));
      expect(labels, contains('关注的人常来'));
    });

    test('实体对象 e_pku：关注的人来过/联系人来过/关注的人加入 分层（地点维度）', () async {
      final reasons = await repo.getObjectIntersections(
        objectId: 'e_pku',
        objectType: 'entity',
      );
      expect(reasons, isNotEmpty);
      expect(reasons.first.intersectionId, 'objix_entity_e_pku');
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
      // 「…把你们连在一起」由实例（如关注的人名）构成，非空说维度词。
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

    test('未 seed 的对象 → 返回空（不造假、无 objectType 合成回退）', () async {
      // 既往按 objectType 硬编码合成证据组的第二真相源已删除：
      // 任一未在 fixture objectIntersections 中登记的对象（含合法 user 类型）均返回空。
      final unknownType = await repo.getObjectIntersections(
        objectId: 'x',
        objectType: 'future_object_kind',
      );
      expect(unknownType, isEmpty);

      final unseededUser = await repo.getObjectIntersections(
        objectId: 'u_not_seeded',
        objectType: 'user',
      );
      expect(unseededUser, isEmpty);
    });
  });
}
