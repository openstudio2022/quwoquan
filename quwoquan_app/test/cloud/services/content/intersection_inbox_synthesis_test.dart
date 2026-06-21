import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_point.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_representative_actor.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_fact_items.dart';

/// T1：我的交集行归一（云侧 G2 模拟）合约。
/// - 句式恒「代表人在数字前」，代表人是纯文本蓝字（无头像），数字/对象切成可点 span；
/// - kind → iconKey 闭集映射由 codegen [IntersectionKindMetadata] 单一真相源驱动（§23 去桥接，
///   端不再硬编码 kind→iconKey switch）；
/// - 无路由对象（tag/content）渲染纯文本，不生成死蓝字；
/// - mutualCount 真相取 point.count；
/// - 已携带 primarySpans 的（云侧直出富文本）不二次合成。
void main() {
  IntersectionReason reason({
    required String kind,
    String dimension = 'relationship',
    required String objectName,
    String objectId = '',
    required String objectKind,
    int count = 0,
    String? repName,
    String? repId,
    String repPrivacy = 'visible',
    String intersectionClass = 'fact',
    List<IntersectionTextSpan> primarySpans = const <IntersectionTextSpan>[],
  }) {
    return IntersectionReason(
      dimension: dimension,
      intersectionId: 'ix_test',
      intersectionClass: intersectionClass,
      displayName: objectName,
      objectKind: objectKind,
      actionTargetId: objectId,
      totalPointCount: count,
      source: kind,
      primarySpans: primarySpans,
      intersectionPoints: <IntersectionPoint>[
        IntersectionPoint(
          pointId: 'p',
          sourceRef: kind,
          count: count,
          dimension: dimension,
        ),
      ],
      representativeActor: repName == null
          ? null
          : IntersectionRepresentativeActor(
              actorId: repId ?? '',
              displayName: repName,
              privacyState: repPrivacy,
            ),
    );
  }

  String joined(List<IntersectionTextSpan> spans) =>
      spans.map((s) => s.text).join();

  IntersectionTextSpan spanOfRole(
    List<IntersectionTextSpan> spans,
    String role,
  ) => spans.firstWhere((s) => s.role == role);

  group('buildInboxStatementSpans / normalizeInboxReason', () {
    test('sharedFollowees 无代表人：你关注的N人也关注了[对象]', () {
      final r = normalizeInboxReason(reason(
        kind: 'sharedFollowees',
        objectName: '林清越',
        objectId: 'u_lin',
        objectKind: 'person',
        count: 4,
      ));
      expect(r.primaryText, '你关注的4人也关注了林清越');
      expect(r.iconKey, 'people');
      expect(r.mutualCount, 4);
      // 数字片段：role=count，文本=N，下钻 myIntersections。
      final countSpan = spanOfRole(r.primarySpans, 'count');
      expect(countSpan.text, '4');
      expect(countSpan.target?.routeId, 'myIntersections');
      // 对象人名：role=object，可点 userProfile。
      final objectSpan = r.primarySpans
          .firstWhere((s) => s.role == 'object' && s.text == '林清越');
      expect(objectSpan.target?.objectId, 'u_lin');
      expect(objectSpan.target?.routeId, 'userProfile');
      // 文本=span 拼接（端不再二次拼装）。
      expect(joined(r.primarySpans), r.primaryText);
      // 行动建议非空，首项=注册表 actionHintsByKind 首位（codegen 主行动真相源）。
      expect(r.actionHints, isNotEmpty);
      expect(
        r.actionHints.first.actionKey,
        IntersectionKindMetadata.of('sharedFollowees')!.primaryActionKey,
      );
      expect(r.actionHints.first.actionKey, 'follow_person');
    });

    test('coCommented 含代表人：代表人纯文本蓝字恒在数字前', () {
      final r = normalizeInboxReason(reason(
        kind: 'coCommented',
        dimension: 'content',
        objectName: '黄金投资圈',
        objectId: 'circle_gold',
        objectKind: 'circle',
        count: 8,
        repName: '王然',
        repId: 'u_wang',
      ));
      expect(r.primaryText, '你和王然等8人都讨论过黄金投资圈');
      expect(r.iconKey, 'discussion');
      // 代表人是可点 person span，且出现在数字之前。
      final repIndex =
          r.primarySpans.indexWhere((s) => s.text == '王然');
      final countIndex = r.primarySpans.indexWhere((s) => s.role == 'count');
      expect(repIndex, greaterThanOrEqualTo(0));
      expect(repIndex, lessThan(countIndex));
      final repSpan = r.primarySpans[repIndex];
      expect(repSpan.role, 'object');
      expect(repSpan.target?.objectKind, 'person');
      expect(repSpan.target?.objectId, 'u_wang');
      // 圈子对象可点 circleDetail。
      final objectSpan = r.primarySpans
          .firstWhere((s) => s.role == 'object' && s.text == '黄金投资圈');
      expect(objectSpan.target?.routeId, 'circleDetail');
      // 主行动由 codegen 注册表 actionHintsByKind 首位驱动（端不再硬编码 kind→action）。
      expect(
        r.actionHints.first.actionKey,
        IntersectionKindMetadata.of('coCommented')!.primaryActionKey,
      );
      expect(r.actionHints.first.actionKey, 'open_content');
    });

    test('sharedTagSample：标签无路由 → 纯文本，不生成死蓝字', () {
      final r = normalizeInboxReason(reason(
        kind: 'sharedTagSample',
        dimension: 'interest',
        objectName: '胶片摄影',
        objectId: 'tag_film',
        objectKind: 'tag',
        repName: '林清越',
        repId: 'u_lin',
      ));
      expect(r.primaryText, '你和林清越都关注胶片摄影');
      expect(r.iconKey, 'interest');
      // 代表人可点。
      final repSpan = r.primarySpans.firstWhere((s) => s.text == '林清越');
      expect(repSpan.role, 'object');
      // 标签是纯文本（无 target）。
      final tagSpan = r.primarySpans.firstWhere((s) => s.text == '胶片摄影');
      expect(tagSpan.role, 'plain');
      expect(tagSpan.target, isNull);
    });

    test('affinity：你可能和[对象]兴趣相投（概率推荐）', () {
      final r = normalizeInboxReason(reason(
        kind: 'affinity',
        dimension: 'interest',
        objectName: '陆衡',
        objectId: 'u_lu',
        objectKind: 'person',
        intersectionClass: 'affinity',
      ));
      expect(r.primaryText, '你可能和陆衡兴趣相投');
      expect(r.iconKey, 'interest');
      final objectSpan = r.primarySpans.firstWhere((s) => s.text == '陆衡');
      expect(objectSpan.role, 'object');
      expect(objectSpan.target?.objectId, 'u_lu');
    });

    test('commonContact：对象是人、数字落末尾', () {
      final r = normalizeInboxReason(reason(
        kind: 'commonContact',
        objectName: '李航',
        objectId: 'u_li',
        objectKind: 'person',
        count: 3,
      ));
      expect(r.primaryText, '你和李航有3位共同联系人');
      expect(r.iconKey, 'contact');
      expect(spanOfRole(r.primarySpans, 'count').text, '3');
      expect(r.actionHints.first.actionKey, 'greet_person');
    });

    test('代表人隐私态非 visible → 不外显具体名字', () {
      final r = normalizeInboxReason(reason(
        kind: 'coLiked',
        dimension: 'content',
        objectName: '一条记录',
        objectId: 'post_1',
        objectKind: 'content',
        count: 6,
        repName: '私密用户',
        repId: 'u_secret',
        repPrivacy: 'hidden',
      ));
      expect(r.primaryText.contains('私密用户'), isFalse);
      expect(r.primaryText, '你和6人都赞过一条记录');
    });

    test('已携带 primarySpans 的不二次合成，只补 iconKey 等元数据', () {
      final preset = <IntersectionTextSpan>[
        IntersectionTextSpan(text: '云侧直出富文本', role: 'plain'),
      ];
      final r = normalizeInboxReason(reason(
        kind: 'sharedFollowees',
        objectName: '林清越',
        objectId: 'u_lin',
        objectKind: 'person',
        count: 4,
        primarySpans: preset,
      ));
      expect(r.primarySpans, same(preset));
      // iconKey 仍按 kind 回填。
      expect(r.iconKey, 'people');
    });
  });

  group('kind 解析（codegen 元数据驱动）/ mutualCount / iconKey', () {
    test('point.sourceRef 作为 kind 真相源（reason.kind 缺省时）→ 命中注册表 iconKey', () {
      final r = IntersectionReason(
        dimension: 'location',
        // source 是维度名（非注册表 kind），kind 一等字段缺省，
        // 真相应回退到 point.sourceRef。
        source: 'location',
        objectKind: 'place',
        displayName: '西湖',
        actionTargetId: 'place_xihu',
        totalPointCount: 5,
        intersectionPoints: <IntersectionPoint>[
          IntersectionPoint(
            pointId: 'p',
            sourceRef: 'coVisitedEntity',
            count: 5,
            dimension: 'location',
          ),
        ],
      );
      final n = normalizeInboxReason(r);
      // point.sourceRef=coVisitedEntity → codegen iconKey=place。
      expect(n.iconKey, IntersectionKindMetadata.of('coVisitedEntity')!.iconKey);
      expect(n.iconKey, 'place');
      expect(intersectionMutualCountOf(r), 5);
    });

    test('source 退化为维度名时不作为 kind（图标走 dimension 末级回退而非误当 kind）', () {
      final r = IntersectionReason(
        dimension: 'relationship',
        source: 'relationship',
        objectKind: 'person',
        displayName: '某人',
      );
      // 'relationship' 是维度名、非注册表 kind → codegen 命中失败。
      expect(IntersectionKindMetadata.of('relationship'), isNull);
      final n = normalizeInboxReason(r);
      // 未命中 kind → 不按 kind 模板合成富文本（无 primarySpans）。
      expect(n.primarySpans, isEmpty);
      // iconKey 仅来自 codegen dimension 末级回退（intersectionIconKeyByDimension），
      // 证明维度名没有被误当 kind 去查 kind.iconKey。
      expect(n.iconKey, intersectionIconKeyByDimension['relationship']);
    });

    test('kind → iconKey 闭集映射由 codegen IntersectionKindMetadata 驱动', () {
      expect(IntersectionKindMetadata.of('sharedFollowees')!.iconKey, 'people');
      expect(IntersectionKindMetadata.of('commonContact')!.iconKey, 'contact');
      expect(IntersectionKindMetadata.of('coVisitedEntity')!.iconKey, 'place');
      expect(IntersectionKindMetadata.of('followeeVisited')!.iconKey, 'placeHere');
      expect(IntersectionKindMetadata.of('sharedCircle')!.iconKey, 'circle');
      // 未登记 kind 返回 null（端据此安全降级，不再硬编码 default 分支）。
      expect(IntersectionKindMetadata.of('unknown_future_kind'), isNull);
    });
  });

  group('fallbackInboxReasons 整体自洽', () {
    test('每条都生成富文本 + iconKey + 行动建议，且文本=span 拼接', () {
      final reasons = fallbackInboxReasons();
      expect(reasons, isNotEmpty);
      for (final r in reasons) {
        expect(r.primarySpans, isNotEmpty, reason: r.intersectionId);
        expect(r.iconKey, isNotEmpty, reason: r.intersectionId);
        expect(r.actionHints, isNotEmpty, reason: r.intersectionId);
        expect(joined(r.primarySpans), r.primaryText, reason: r.intersectionId);
      }
    });

    test('无裸 avatar span：代表人恒为纯文本，无 image role', () {
      final reasons = fallbackInboxReasons();
      for (final r in reasons) {
        for (final s in r.primarySpans) {
          expect(s.role, isNot('avatar'));
          expect(s.role, isNot('image'));
        }
      }
    });
  });
}
