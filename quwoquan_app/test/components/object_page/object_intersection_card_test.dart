import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_point.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_card.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';

/// T2：对象页统一交集卡口径（V5 · primaryText 单通道 / 全局验收 G2）。
/// - 无 primaryText → 不展示；
/// - 主句唯一来源为 IntersectionReason.primaryText；
/// - primarySpans 只作为同一句话的可交互投影；
/// - affinity 只能显示推荐辅助，不伪装事实；
/// - 折叠、旅程高亮与全部入口按 reason 维度工作。
IntersectionReason _reason({
  required String id,
  required String primaryText,
  String source = '',
  String dimension = 'relationship',
  String intersectionClass = 'fact',
  String confidenceLabel = '',
  String connectionSummary = '',
  List<IntersectionTextSpan> primarySpans = const <IntersectionTextSpan>[],
  List<IntersectionPoint> intersectionPoints = const <IntersectionPoint>[],
}) {
  return IntersectionReason(
    intersectionId: id,
    source: source,
    dimension: dimension,
    primaryText: primaryText,
    intersectionClass: intersectionClass,
    confidenceLabel: confidenceLabel,
    connectionSummary: connectionSummary,
    primarySpans: primarySpans,
    intersectionPoints: intersectionPoints,
  );
}

void main() {
  group('ObjectIntersectionCard.fromReasons（G2 primaryText 口径）', () {
    test('reasons 为 null → 返回 null（不展示）', () {
      expect(
        ObjectIntersectionCard.fromReasons(
          title: '为什么推荐这里',
          reasons: null,
          isDark: false,
        ),
        isNull,
      );
    });

    test('reasons 为空或无 primaryText → 返回 null', () {
      expect(
        ObjectIntersectionCard.fromReasons(
          title: '为什么推荐这个圈子',
          reasons: const <IntersectionReason>[],
          isDark: false,
        ),
        isNull,
      );
      expect(
        ObjectIntersectionCard.fromReasons(
          title: '为什么推荐这里',
          reasons: <IntersectionReason>[
            _reason(id: 'blank', primaryText: '   '),
          ],
          isDark: false,
        ),
        isNull,
      );
    });

    testWidgets('主句只读 primaryText，不从 intersectionPoints 拼 label/count/sample', (
      tester,
    ) async {
      final card = ObjectIntersectionCard.fromReasons(
        title: '为什么推荐这里',
        reasons: <IntersectionReason>[
          _reason(
            id: 'ix_primary',
            primaryText: '4 位共同关注的人正在这里讨论',
            connectionSummary: '最近有你关注的人参与讨论',
            intersectionPoints: <IntersectionPoint>[
              IntersectionPoint(
                pointId: 'legacy_point',
                label: '共同关注',
                displayText: '共同关注',
                count: 4,
                sampleText: '林清越',
              ),
            ],
          ),
        ],
        isDark: false,
      );

      await tester.pumpWidget(CupertinoApp(home: card!));

      expect(find.text('为什么推荐这里'), findsOneWidget);
      expect(find.text('4 位共同关注的人正在这里讨论'), findsOneWidget);
      expect(find.text('最近有你关注的人参与讨论'), findsOneWidget);
      expect(find.text('共同关注 4'), findsNothing);
      expect(find.text('林清越'), findsNothing);
    });

    testWidgets('primarySpans 与 primaryText 同句展示，点击行回传原 reason 归因对象', (
      tester,
    ) async {
      IntersectionReason? tapped;
      final reason = _reason(
        id: 'ix_spans',
        primaryText: '你与林清越等 3 位都在这里互动过',
        primarySpans: <IntersectionTextSpan>[
          IntersectionTextSpan(text: '你与', role: 'plain'),
          IntersectionTextSpan(text: '林清越', role: 'object'),
          IntersectionTextSpan(text: '等 ', role: 'plain'),
          IntersectionTextSpan(text: '3', role: 'count'),
          IntersectionTextSpan(text: ' 位都在这里互动过', role: 'plain'),
        ],
      );
      final card = ObjectIntersectionCard.fromReasons(
        title: '为什么推荐这里',
        reasons: <IntersectionReason>[reason],
        isDark: false,
        onReasonTap: (r) => tapped = r,
      );

      await tester.pumpWidget(CupertinoApp(home: card!));

      expect(find.textContaining('林清越'), findsOneWidget);
      await tester.tap(find.textContaining('林清越'));
      await tester.pump();

      expect(tapped, same(reason));
    });

    testWidgets('affinity 只显示推荐辅助文案，不伪装成事实计数', (tester) async {
      final card = ObjectIntersectionCard.fromReasons(
        title: '为什么推荐这个圈子',
        reasons: <IntersectionReason>[
          _reason(
            id: 'ix_affinity',
            primaryText: '这个圈子的讨论与你最近关注的主题相关',
            dimension: 'interest',
            intersectionClass: 'affinity',
          ),
        ],
        isDark: false,
      );

      await tester.pumpWidget(CupertinoApp(home: card!));

      expect(find.text('这个圈子的讨论与你最近关注的主题相关'), findsOneWidget);
      expect(
        find.text(DiscoveryFeedText.intersectionAffinityLabel),
        findsOneWidget,
      );
      expect(find.textContaining('共同关注'), findsNothing);
    });

    testWidgets('就地展开：默认 inlineExpandCount 条 reason，点击展开余下理由', (tester) async {
      final card = ObjectIntersectionCard.fromReasons(
        title: '为什么推荐这里',
        inlineExpandCount: 2,
        reasons: <IntersectionReason>[
          _reason(id: 'r1', primaryText: '第一条推荐理由'),
          _reason(id: 'r2', primaryText: '第二条推荐理由'),
          _reason(id: 'r3', primaryText: '第三条推荐理由'),
        ],
        isDark: false,
      );

      await tester.pumpWidget(CupertinoApp(home: card!));
      expect(find.text('第一条推荐理由'), findsOneWidget);
      expect(find.text('第二条推荐理由'), findsOneWidget);
      expect(find.text('第三条推荐理由'), findsNothing);

      await tester.tap(find.text(DiscoveryFeedText.intersectionExpandMore));
      await tester.pumpAndSettle();
      expect(find.text('第三条推荐理由'), findsOneWidget);
    });

    testWidgets('旅程高亮：highlightKind 命中折叠区 reason 时自动展开', (tester) async {
      final card = ObjectIntersectionCard.fromReasons(
        title: '为什么推荐这个圈子',
        inlineExpandCount: 1,
        highlightKind: 'coCommented',
        reasons: <IntersectionReason>[
          _reason(id: 'r1', primaryText: '第一条推荐理由', source: 'sharedFollowees'),
          _reason(id: 'r2', primaryText: '共同讨论正在升温', source: 'coCommented'),
        ],
        isDark: false,
      );

      await tester.pumpWidget(CupertinoApp(home: card!));
      await tester.pumpAndSettle();
      expect(find.text('共同讨论正在升温'), findsOneWidget);
    });

    testWidgets('展开更多两段式：先展开，再进入全部连接', (tester) async {
      var openedAll = false;
      final card = ObjectIntersectionCard.fromReasons(
        title: '为什么推荐这里',
        inlineExpandCount: 1,
        moreLabel: '全部连接',
        onMoreTap: () => openedAll = true,
        reasons: <IntersectionReason>[
          _reason(id: 'r1', primaryText: '第一条推荐理由'),
          _reason(id: 'r2', primaryText: '第二条推荐理由'),
        ],
        isDark: false,
      );

      await tester.pumpWidget(CupertinoApp(home: card!));
      await tester.pumpAndSettle();

      expect(find.text('第一条推荐理由'), findsOneWidget);
      expect(find.text('第二条推荐理由'), findsNothing);
      expect(
        find.text(DiscoveryFeedText.intersectionExpandMore),
        findsOneWidget,
      );

      await tester.tap(find.text(DiscoveryFeedText.intersectionExpandMore));
      await tester.pumpAndSettle();

      expect(find.text('第二条推荐理由'), findsOneWidget);
      expect(find.text('全部连接'), findsOneWidget);
      expect(openedAll, isFalse);

      await tester.tap(find.text('全部连接'));
      await tester.pump();

      expect(openedAll, isTrue);
    });
  });
}
