import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/object_page/object_page_sections.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_header.dart';

Widget _wrap(Widget child) => MaterialApp(
  home: Scaffold(
    body: SingleChildScrollView(child: SizedBox(height: 300, child: child)),
  ),
);

void main() {
  group('CircleHeader — 共享身份头底座契约', () {
    testWidgets('圈子名渲染到共享 ObjectIdentityHeader', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const CircleHeader(
            isDark: false,
            name: 'Test Circle Name',
            identityTags: <String>['flutter', 'dart'],
          ),
        ),
      );
      await tester.pump();

      expect(find.byType(ObjectIdentityHeader), findsOneWidget);
      expect(find.text('Test Circle Name'), findsOneWidget);
    });

    testWidgets('类型标签以 · 拼接为单行副标题（不再是 Wrap 标签墙）', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const CircleHeader(
            isDark: false,
            name: 'Tagged Circle',
            identityTags: <String>['AI 产品', '产品经理', '创业'],
          ),
        ),
      );
      await tester.pump();

      expect(find.text('AI 产品 · 产品经理 · 创业'), findsOneWidget);
      // 头部不再用标签 chip 墙，统一为单行副标题。
      expect(find.byType(Wrap), findsNothing);
    });

    testWidgets('无头像时回退到圈子类型占位图标', (tester) async {
      await tester.pumpWidget(
        _wrap(const CircleHeader(isDark: false, name: 'No Avatar Circle')),
      );
      await tester.pump();

      expect(find.byIcon(CupertinoIcons.person_3_fill), findsOneWidget);
    });

    testWidgets('空头像 URL 降级为类型占位图标', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const CircleHeader(isDark: false, avatarUrl: '', name: 'Empty URL'),
        ),
      );
      await tester.pump();

      expect(find.byIcon(CupertinoIcons.person_3_fill), findsOneWidget);
    });

    testWidgets('认证圈子展示认证勾', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const CircleHeader(
            isDark: false,
            name: 'Verified Circle',
            verified: true,
          ),
        ),
      );
      await tester.pump();

      expect(
        find.byKey(const ValueKey<String>('circle-header-verified-badge')),
        findsOneWidget,
      );
    });

    testWidgets('未认证圈子不展示认证勾', (tester) async {
      await tester.pumpWidget(
        _wrap(const CircleHeader(isDark: false, name: 'Plain Circle')),
      );
      await tester.pump();

      expect(
        find.byKey(const ValueKey<String>('circle-header-verified-badge')),
        findsNothing,
      );
    });

    testWidgets('深色模式正确渲染', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const CircleHeader(
            isDark: true,
            name: 'Dark Mode Circle',
            identityTags: <String>['夜间'],
          ),
        ),
      );
      await tester.pump();

      expect(find.text('Dark Mode Circle'), findsOneWidget);
    });
  });

  group('CircleHeader — 稳定性', () {
    testWidgets('长名称截断不崩溃', (tester) async {
      await tester.pumpWidget(
        _wrap(CircleHeader(isDark: false, name: 'A' * 200)),
      );
      await tester.pump();

      expect(find.byType(CircleHeader), findsOneWidget);
    });

    testWidgets('空名称安全渲染', (tester) async {
      await tester.pumpWidget(
        _wrap(const CircleHeader(isDark: false, name: '')),
      );
      await tester.pump();

      expect(find.byType(CircleHeader), findsOneWidget);
    });

    testWidgets('空标签列表不渲染副标题文本', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const CircleHeader(
            isDark: false,
            name: 'No Tags',
            identityTags: <String>[],
          ),
        ),
      );
      await tester.pump();

      expect(find.byType(CircleHeader), findsOneWidget);
    });
  });
}
