import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_point.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/components/object_page/evidence_group.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_card.dart';

/// T2：对象页统一交集卡口径（V4 · 人脸抽屉列表 / 全局验收 G2）。
/// - 无来源 / 无可展示证据组 → 不展示；
/// - 数字 single-source：顶部总数 = 可见证据组 count 之和，与列表逐项一致；
/// - 零内部词：行内只出现云侧短句 + 计数 + 实例，不出现「N 个交集点 / 身份 / 兴趣」内部词；
/// - 维度开放：未知 dimension 仍能按 label + count 优雅降级展示；
/// - 推荐角标：recommended 点带「推荐」标识，不伪装事实。
IntersectionPoint _point({
  required String dimension,
  required String label,
  required int count,
  String pointClass = 'fact',
  String sampleText = '',
}) {
  return IntersectionPoint(
    pointId: '$dimension-$label',
    pointClass: pointClass,
    dimension: dimension,
    label: label,
    displayText: label,
    count: count,
    sampleText: sampleText,
  );
}

void main() {
  group('ObjectIntersectionCard.fromReasons（G2 口径）', () {
    test('reasons 为 null → 返回 null（不展示）', () {
      expect(
        ObjectIntersectionCard.fromReasons(
          title: '你们的交集',
          reasons: null,
          isDark: false,
        ),
        isNull,
      );
    });

    test('reasons 为空 → 返回 null', () {
      expect(
        ObjectIntersectionCard.fromReasons(
          title: '你和这里的交集',
          reasons: const <IntersectionReason>[],
          isDark: false,
        ),
        isNull,
      );
    });

    test('无可展示证据组（无点 + 空 label） → 返回 null', () {
      expect(
        ObjectIntersectionCard.fromReasons(
          title: '你们的交集',
          reasons: [IntersectionReason(label: '   ')],
          isDark: false,
        ),
        isNull,
      );
    });

    test('数字 single-source：总数 = 可见证据组 count 之和', () {
      final reason = IntersectionReason(
        dimension: 'relationship',
        intersectionPoints: <IntersectionPoint>[
          _point(dimension: 'relationship', label: '共同关注', count: 4),
          _point(dimension: 'content', label: '共看内容', count: 2),
        ],
      );
      final groups = EvidenceGroup.fromReason(reason);
      expect(EvidenceGroup.totalCount(groups), 6);
    });

    testWidgets('抽屉列表行：短句 + 计数 + 实例；顶部总数与逐项一致；零内部词', (tester) async {
      final card = ObjectIntersectionCard.fromReasons(
        title: '你们的交集',
        reasons: [
          IntersectionReason(
            dimension: 'relationship',
            relationKind: 'person',
            intersectionPoints: <IntersectionPoint>[
              _point(
                dimension: 'relationship',
                label: '共同关注',
                count: 4,
                sampleText: '林清越',
              ),
            ],
          ),
          IntersectionReason(
            dimension: 'content',
            relationKind: 'circle',
            intersectionPoints: <IntersectionPoint>[
              _point(
                dimension: 'content',
                label: '共看内容',
                count: 8,
                sampleText: '黄金投资圈',
              ),
            ],
          ),
        ],
        isDark: false,
      );

      await tester.pumpWidget(CupertinoApp(home: card!));

      expect(find.text('你们的交集'), findsOneWidget);
      // 总数 = 4 + 8 = 12，与逐项一致（single-source）。
      expect(find.text('12'), findsOneWidget);
      // 短句 + 实例。
      expect(find.text('共同关注'), findsOneWidget);
      expect(find.text('林清越'), findsOneWidget);
      expect(find.text('共看内容'), findsOneWidget);
      expect(find.text('黄金投资圈'), findsOneWidget);
      // 零内部词：不出现「N 个交集点 / 身份 / 兴趣」内部分类语言。
      expect(find.textContaining('个交集点'), findsNothing);
      expect(find.textContaining('身份'), findsNothing);
    });

    testWidgets('未知维度优雅降级：仍按 label + count 展示，不崩', (tester) async {
      final card = ObjectIntersectionCard.fromReasons(
        title: '你们的交集',
        reasons: [
          IntersectionReason(
            dimension: 'future_new_dimension',
            relationKind: 'place',
            intersectionPoints: <IntersectionPoint>[
              _point(
                dimension: 'future_new_dimension',
                label: '同时段到访',
                count: 3,
                sampleText: '798 艺术区',
              ),
            ],
          ),
        ],
        isDark: false,
      );

      await tester.pumpWidget(CupertinoApp(home: card!));
      expect(find.text('同时段到访'), findsOneWidget);
      expect(find.text('798 艺术区'), findsOneWidget);
      // 总数与唯一行计数都是 3（single-source 一致）：顶部 1 + 行内 1。
      expect(find.text('3'), findsNWidgets(2));
    });

    testWidgets('推荐点带「推荐」角标，不伪装事实', (tester) async {
      final card = ObjectIntersectionCard.fromReasons(
        title: '你们的交集',
        reasons: [
          IntersectionReason(
            dimension: 'interest',
            relationKind: 'person',
            intersectionClass: 'affinity',
            intersectionPoints: <IntersectionPoint>[
              _point(
                dimension: 'interest',
                label: '可能合得来',
                count: 5,
                pointClass: 'recommended',
              ),
            ],
          ),
        ],
        isDark: false,
      );

      await tester.pumpWidget(CupertinoApp(home: card!));
      expect(find.text('可能合得来'), findsOneWidget);
      expect(find.text('推荐'), findsOneWidget);
    });

    testWidgets('连接说明：缺省回落云侧 connectionSummary 实例化一句话', (tester) async {
      final card = ObjectIntersectionCard.fromReasons(
        title: '你们的交集',
        reasons: [
          IntersectionReason(
            dimension: 'relationship',
            relationKind: 'person',
            connectionSummary: '北京大学、摄影把你们连在一起',
            intersectionPoints: <IntersectionPoint>[
              _point(dimension: 'relationship', label: '共同关注', count: 4),
            ],
          ),
        ],
        isDark: false,
      );

      await tester.pumpWidget(CupertinoApp(home: card!));
      // §7.1：连接说明由实例构成，端不本地拼装。
      expect(find.text('北京大学、摄影把你们连在一起'), findsWidgets);
    });

    testWidgets('CTA：展示下一步动作并复用 reason tap 归因入口', (tester) async {
      var tapped = false;
      final reason = IntersectionReason(
        dimension: 'relationship',
        relationKind: 'person',
        actionType: 'follow_author',
        connectionSummary: '同校与摄影把你们连在一起',
        intersectionPoints: <IntersectionPoint>[
          _point(dimension: 'relationship', label: '共同关注', count: 4),
        ],
      );
      final card = ObjectIntersectionCard.fromReasons(
        title: '你们的交集',
        reasons: <IntersectionReason>[reason],
        isDark: false,
        onReasonTap: (_) => tapped = true,
      );

      await tester.pumpWidget(CupertinoApp(home: card!));

      expect(
        find.byKey(const ValueKey<String>('object-intersection-primary-cta')),
        findsOneWidget,
      );
      expect(find.text('关注作者'), findsOneWidget);
      expect(find.text('同校与摄影把你们连在一起'), findsWidgets);

      await tester.tap(
        find.byKey(const ValueKey<String>('object-intersection-primary-cta')),
      );
      expect(tapped, isTrue);
    });

    testWidgets('就地展开：默认 inlineExpandCount 行，点击展开余下证据组', (tester) async {
      final card = ObjectIntersectionCard.fromReasons(
        title: '你们的交集',
        inlineExpandCount: 2,
        reasons: [
          IntersectionReason(
            dimension: 'relationship',
            relationKind: 'person',
            intersectionPoints: <IntersectionPoint>[
              _point(dimension: 'relationship', label: '共同关注', count: 4),
              _point(dimension: 'relationship', label: '共同关注扩展', count: 6),
              _point(dimension: 'content', label: '都赞过', count: 3),
            ],
          ),
        ],
        isDark: false,
      );

      await tester.pumpWidget(CupertinoApp(home: card!));
      // 默认只显示前 2 行证据组（第 3 条隐藏）。
      expect(find.text('共同关注'), findsOneWidget);
      expect(find.text('共同关注扩展'), findsOneWidget);
      expect(find.text('都赞过'), findsNothing);
      // 点击「展开更多」就地展开。
      await tester.tap(find.textContaining('展开更多'));
      await tester.pumpAndSettle();
      expect(find.text('都赞过'), findsOneWidget);
    });

    testWidgets('旅程高亮：highlightKind 命中折叠区证据组时自动展开', (tester) async {
      final card = ObjectIntersectionCard.fromReasons(
        title: '你们的交集',
        inlineExpandCount: 2,
        // 命中第 3 条（折叠区内）的 kind。
        highlightKind: 'content',
        reasons: [
          IntersectionReason(
            dimension: 'relationship',
            relationKind: 'person',
            intersectionPoints: <IntersectionPoint>[
              _point(dimension: 'relationship', label: '共同关注', count: 4),
              _point(dimension: 'relationship', label: '共同关注', count: 6),
              _point(dimension: 'content', label: '都赞过', count: 3),
            ],
          ),
        ],
        isDark: false,
      );

      await tester.pumpWidget(CupertinoApp(home: card!));
      await tester.pumpAndSettle();
      // 旅程无断点：落地即见被高亮的证据组（即便它原本在折叠区）。
      expect(find.text('都赞过'), findsOneWidget);
    });

    testWidgets('宽屏下切成横向封面 rail，更多入口保留且高度收敛', (tester) async {
      tester.view.physicalSize = const Size(1280, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final card = ObjectIntersectionCard.fromReasons(
        title: '你和这里的交集',
        reasons: [
          IntersectionReason(
            dimension: 'relationship',
            relationKind: 'circle',
            displayName: '摄影圈',
            avatarUrl: '',
            intersectionPoints: <IntersectionPoint>[
              _point(
                dimension: 'relationship',
                label: '共同关注',
                count: 8,
                sampleText: '林清越',
              ),
              _point(
                dimension: 'content',
                label: '共看内容',
                count: 4,
                sampleText: '川西攻略',
              ),
            ],
          ),
        ],
        isDark: false,
      );

      await tester.pumpWidget(
        CupertinoApp(
          home: Center(child: SizedBox(width: 760, child: card!)),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('你和这里的交集'), findsOneWidget);
      expect(find.text('摄影圈'), findsOneWidget);
      expect(
        find.text('共同关注').evaluate().isNotEmpty ||
            find.text('共看内容').evaluate().isNotEmpty,
        isTrue,
      );
      expect(find.text('川西攻略'), findsNothing);
      expect(find.textContaining('展开更多'), findsOneWidget);
      expect(
        tester.getSize(find.byType(ObjectIntersectionCard)).height,
        lessThan(260),
      );

      await tester.tap(find.textContaining('展开更多'));
      await tester.pumpAndSettle();

      expect(find.text('川西攻略'), findsOneWidget);
    });
  });
}
