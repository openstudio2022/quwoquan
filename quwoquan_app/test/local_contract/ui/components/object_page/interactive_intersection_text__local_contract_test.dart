import 'package:flutter/cupertino.dart';
import '../../../../support/fixtures/intersection_fixtures.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/recommendation/recommendation/recommendation_feature_profile_view/presentation/interactive_intersection_text.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 取 InteractiveIntersectionText 最外层（DFS 首个）RichText——槽②行内头像由 WidgetSpan
/// 承载，其子树可能含独立 RichText，这里只关心承载结论句的根 RichText。
RichText _rootRichText(WidgetTester tester) => tester
    .widgetList<RichText>(
      find.descendant(
        of: find.byType(InteractiveIntersectionText),
        matching: find.byType(RichText),
      ),
    )
    .first;

/// 顺序拼接根 RichText 中所有 TextSpan 的文本（WidgetSpan 不贡献字符），
/// 用于校验 join(spans.text) == primaryText 不变量不被槽②行内头像破坏。
String _joinedSpanText(WidgetTester tester) {
  final buffer = StringBuffer();
  _rootRichText(tester).text.visitChildren((span) {
    if (span is TextSpan && span.text != null) {
      buffer.write(span.text);
    }
    return true;
  });
  return buffer.toString();
}

/// 触发 RichText 中指定文本片段的 TapGestureRecognizer。
///
/// 内联 span 无法用屏幕坐标稳定命中，这里遍历 InlineSpan 树按文本定位 recognizer 并直接触发，
/// 用于验证「按角色分发点击」这一行为契约（命中返回 true，无 recognizer 返回 false）。
bool _tapSpanByText(WidgetTester tester, String text) {
  final richText = tester.widget<RichText>(
    find.descendant(
      of: find.byType(InteractiveIntersectionText),
      matching: find.byType(RichText),
    ),
  );
  var hit = false;
  richText.text.visitChildren((span) {
    if (span is TextSpan && span.text == text) {
      final recognizer = span.recognizer;
      if (recognizer is TapGestureRecognizer && recognizer.onTap != null) {
        recognizer.onTap!();
        hit = true;
        return false;
      }
    }
    return true;
  });
  return hit;
}

TextSpan _spanByText(WidgetTester tester, String text) {
  final richText = tester.widget<RichText>(
    find.descendant(
      of: find.byType(InteractiveIntersectionText),
      matching: find.byType(RichText),
    ),
  );
  TextSpan? result;
  richText.text.visitChildren((span) {
    if (span is TextSpan && span.text == text) {
      result = span;
      return false;
    }
    return true;
  });
  return result!;
}

// 槽②行内头像走 AppCachedNetworkImage，其图片加载失败上报读 Riverpod provider，
// 故统一在 ProviderScope 下挂载（与真实 App 根一致），避免裸渲染缺 scope 崩溃。
Widget _host(Widget child) => ProviderScope(
  child: CupertinoApp(home: CupertinoPageScaffold(child: child)),
);

void main() {
  group('InteractiveIntersectionText 降级链（spans → fallback → 隐藏）', () {
    testWidgets('spans 为空 + fallback 非空 → 纯文本整行命中 onFallbackTap', (
      tester,
    ) async {
      var fallbackTaps = 0;
      await tester.pumpWidget(
        _host(
          InteractiveIntersectionText(
            spans: <IntersectionTextSpan>[],
            fallbackText: '8人与你有关',
            onFallbackTap: () => fallbackTaps++,
          ),
        ),
      );

      expect(find.text('8人与你有关'), findsOneWidget);
      await tester.tap(find.text('8人与你有关'));
      expect(fallbackTaps, 1);
    });

    testWidgets('spans 为空 + fallback 为空 → 隐藏（无文本渲染）', (tester) async {
      await tester.pumpWidget(
        _host(
          const InteractiveIntersectionText(
            spans: <IntersectionTextSpan>[],
            fallbackText: '   ',
          ),
        ),
      );

      expect(
        find.descendant(
          of: find.byType(InteractiveIntersectionText),
          matching: find.byType(Text),
        ),
        findsNothing,
      );
    });
  });

  group('InteractiveIntersectionText 富文本点击分发（按角色）', () {
    final spans = <IntersectionTextSpan>[
      intersectionTextSpanFixture(text: '你与', role: 'plain'),
      intersectionTextSpanFixture(
        text: '林清越',
        role: 'object',
        target: intersectionTargetFixture(
          objectId: 'u_lin',
          objectKind: 'person',
          routeId: 'userProfile',
        ),
      ),
      intersectionTextSpanFixture(text: '等 ', role: 'plain'),
      intersectionTextSpanFixture(
        text: '3',
        role: 'count',
        target: intersectionTargetFixture(
          objectId: 'relationship',
          routeId: 'myIntersections',
        ),
      ),
      intersectionTextSpanFixture(text: ' 位都来这里互动过', role: 'plain'),
    ];

    testWidgets('object 片段与 count 片段各自分发对应 span', (tester) async {
      final tapped = <IntersectionTextSpan>[];
      await tester.pumpWidget(
        _host(
          InteractiveIntersectionText(
            spans: spans,
            fallbackText: '你与林清越等 3 位都来这里互动过',
            onSpanTap: tapped.add,
          ),
        ),
      );

      expect(_tapSpanByText(tester, '林清越'), isTrue);
      expect(_tapSpanByText(tester, '3'), isTrue);
      expect(tapped.map((s) => s.role).toList(), <String>['object', 'count']);
      expect(tapped.first.target?.routeId, 'userProfile');
      expect(tapped.last.target?.routeId, 'myIntersections');
    });

    testWidgets('plain 片段不可点击（无 recognizer）', (tester) async {
      await tester.pumpWidget(
        _host(
          InteractiveIntersectionText(
            spans: spans,
            fallbackText: 'x',
            onSpanTap: (_) {},
          ),
        ),
      );

      expect(_tapSpanByText(tester, ' 位都来这里互动过'), isFalse);
    });

    testWidgets('仅 object/count 可点击片段使用强调色，且保持普通字重', (tester) async {
      await tester.pumpWidget(
        _host(
          InteractiveIntersectionText(
            spans: spans,
            fallbackText: '你与林清越等 3 位都来这里互动过',
            onSpanTap: (_) {},
          ),
        ),
      );

      final context = tester.element(find.byType(InteractiveIntersectionText));
      // 统一交互蓝字采用低饱和 slogan-accent（浅色态），不再用高饱和 iOS systemBlue。
      final accent = AppColors.profileSloganAccentLight;
      final plain = AppColors.iosLabel(context);
      expect(_spanByText(tester, '林清越').style?.color, accent);
      expect(_spanByText(tester, '3').style?.color, accent);
      expect(
        _spanByText(tester, '林清越').style?.fontWeight,
        AppTypography.regular,
      );
      expect(_spanByText(tester, '3').style?.fontWeight, AppTypography.regular);
      expect(_spanByText(tester, '你与').style?.color, plain);
      expect(_spanByText(tester, '等 ').style?.color, plain);
      expect(_spanByText(tester, ' 位都来这里互动过').style?.color, plain);

      await tester.pumpWidget(
        _host(
          InteractiveIntersectionText(
            spans: const <IntersectionTextSpan>[],
            fallbackText: '8人与你有关',
            onFallbackTap: () {},
          ),
        ),
      );

      final fallback = tester.widget<Text>(find.text('8人与你有关'));
      final fallbackContext = tester.element(
        find.byType(InteractiveIntersectionText),
      );
      expect(
        fallback.style?.color,
        isNot(AppColors.iosAccent(fallbackContext)),
      );
    });

    testWidgets('count 片段 target 为空仍可点击（消费方拦截开 sheet 场景）', (tester) async {
      final tapped = <IntersectionTextSpan>[];
      await tester.pumpWidget(
        _host(
          InteractiveIntersectionText(
            spans: <IntersectionTextSpan>[
              intersectionTextSpanFixture(text: '23', role: 'count'),
              intersectionTextSpanFixture(text: ' 人因你加入圈子', role: 'plain'),
            ],
            fallbackText: '23 人因你加入圈子',
            onSpanTap: tapped.add,
          ),
        ),
      );

      expect(_tapSpanByText(tester, '23'), isTrue);
      expect(tapped.single.role, 'count');
      expect(tapped.single.target, isNull);
    });
  });

  group('InteractiveIntersectionText 槽②行内头像（visual）', () {
    final spans = <IntersectionTextSpan>[
      intersectionTextSpanFixture(
        text: '林清越',
        role: 'object',
        visual: intersectionVisualFixture(
          assetKind: 'avatar',
          imageUrl: 'https://example.com/lin.png',
        ),
        target: intersectionTargetFixture(
          objectId: 'u_lin',
          objectKind: 'person',
          routeId: 'userProfile',
        ),
      ),
      intersectionTextSpanFixture(text: '等 3 位都来这里互动过', role: 'plain'),
    ];

    testWidgets(
      'visual 非空注入 WidgetSpan，但不破坏 join(spans.text)==primaryText 不变量',
      (tester) async {
        const primaryText = '林清越等 3 位都来这里互动过';
        await tester.pumpWidget(
          _host(
            InteractiveIntersectionText(
              spans: spans,
              fallbackText: primaryText,
              onSpanTap: (_) {},
            ),
          ),
        );

        // 行内头像贡献一个 WidgetSpan（无字符），文本不变量必须保持。
        expect(_joinedSpanText(tester), primaryText);

        var widgetSpanCount = 0;
        _rootRichText(tester).text.visitChildren((span) {
          if (span is WidgetSpan) widgetSpanCount++;
          return true;
        });
        expect(widgetSpanCount, 1);
      },
    );

    testWidgets('visual 全空时不注入任何 WidgetSpan', (tester) async {
      await tester.pumpWidget(
        _host(
          InteractiveIntersectionText(
            spans: <IntersectionTextSpan>[
              intersectionTextSpanFixture(text: '你与林清越互动过', role: 'plain'),
            ],
            fallbackText: '你与林清越互动过',
            onSpanTap: (_) {},
          ),
        ),
      );

      var widgetSpanCount = 0;
      _rootRichText(tester).text.visitChildren((span) {
        if (span is WidgetSpan) widgetSpanCount++;
        return true;
      });
      expect(widgetSpanCount, 0);
    });
  });
}
