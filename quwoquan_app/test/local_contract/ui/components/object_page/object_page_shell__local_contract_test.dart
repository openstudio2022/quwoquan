import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/object_page/object_page_shell.dart';

/// T2：对象页统一壳层骨架（V3 S1）几何引擎 + 渲染正确性。
void main() {
  group('ObjectPageShell.springDampedOffset（同源下拉回弹）', () {
    test('raw<=0 或 maxPull<=0 → 0', () {
      expect(ObjectPageShell.springDampedOffset(0, 100), 0);
      expect(ObjectPageShell.springDampedOffset(-10, 100), 0);
      expect(ObjectPageShell.springDampedOffset(50, 0), 0);
    });

    test('随 raw 单调递增且不超过 maxPull（渐进阻尼）', () {
      const maxPull = 120.0;
      final a = ObjectPageShell.springDampedOffset(20, maxPull);
      final b = ObjectPageShell.springDampedOffset(80, maxPull);
      final c = ObjectPageShell.springDampedOffset(400, maxPull);
      expect(a, greaterThan(0));
      expect(b, greaterThan(a));
      expect(c, greaterThanOrEqualTo(b));
      expect(c, lessThanOrEqualTo(maxPull));
    });
  });

  group('ObjectPageShell 渲染（背景/summary/toolbar/页签/body）', () {
    testWidgets('各插槽与背景层均渲染', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: ObjectPageShell(
            keyPrefix: 'test-shell',
            pinMode: ObjectPagePinMode.standard,
            backgroundBuilder: (context, pull) =>
                const ColoredBox(color: Color(0xFF112233)),
            summaryBuilder: (context) =>
                const Text('summary-slot', textDirection: TextDirection.ltr),
            toolbarBuilder: (context, identity, bg) =>
                const Text('toolbar-slot', textDirection: TextDirection.ltr),
            tabBarBuilder: (context, pinned, opacity) =>
                const Text('tabbar-slot', textDirection: TextDirection.ltr),
            tabBodyBuilder: (context) =>
                const Text('tab-body-slot', textDirection: TextDirection.ltr),
          ),
        ),
      );
      await tester.pump();

      expect(find.text('toolbar-slot'), findsOneWidget);
      expect(find.text('summary-slot'), findsOneWidget);
      expect(find.text('tab-body-slot'), findsOneWidget);
      // inline + (offstage) pinned 两处页签
      expect(find.text('tabbar-slot'), findsWidgets);
      expect(find.byType(CustomScrollView), findsOneWidget);
      expect(
        find.byKey(const ValueKey<String>('test-shell-background-layer')),
        findsOneWidget,
      );
    });

    testWidgets('minimal 模式带底栏、无吸顶页签', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: ObjectPageShell(
            keyPrefix: 'min-shell',
            pinMode: ObjectPagePinMode.minimal,
            backgroundBuilder: (context, pull) =>
                const ColoredBox(color: Color(0xFF112233)),
            summaryBuilder: (context) =>
                const Text('summary-slot', textDirection: TextDirection.ltr),
            toolbarBuilder: (context, identity, bg) =>
                const Text('toolbar-slot', textDirection: TextDirection.ltr),
            tabBodyBuilder: (context) =>
                const Text('tab-body-slot', textDirection: TextDirection.ltr),
            bottomBar:
                const Text('bottom-bar', textDirection: TextDirection.ltr),
          ),
        ),
      );
      await tester.pump();

      expect(find.text('bottom-bar'), findsOneWidget);
      expect(find.text('tabbar-slot'), findsNothing);
      expect(find.text('summary-slot'), findsOneWidget);
    });
  });
}
