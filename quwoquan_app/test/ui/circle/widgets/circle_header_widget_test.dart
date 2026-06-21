import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_visual.g.dart';
import 'package:quwoquan_app/components/object_page/intersection_visual_cluster.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_header.dart';

Widget _wrap(Widget child) => MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: SizedBox(
            height: 300,
            child: child,
          ),
        ),
      ),
    );

void main() {
  group('CircleHeader — 渲染契约', () {
    testWidgets('正常数据渲染圈子名称', (tester) async {
      await tester.pumpWidget(_wrap(
        const CircleHeader(
          isDark: false,
          name: 'Test Circle Name',
          description: 'A description for the circle',
          tags: ['flutter', 'dart'],
        ),
      ));
      await tester.pump();

      expect(find.text('Test Circle Name'), findsOneWidget);
    });

    testWidgets('描述文本正确渲染', (tester) async {
      await tester.pumpWidget(_wrap(
        const CircleHeader(
          isDark: false,
          name: 'My Circle',
          description: 'This is a test description',
        ),
      ));
      await tester.pump();

      expect(find.text('This is a test description'), findsOneWidget);
    });

    testWidgets('标签正确渲染', (tester) async {
      await tester.pumpWidget(_wrap(
        const CircleHeader(
          isDark: false,
          name: 'Tagged Circle',
          tags: ['tech', 'design', 'art'],
        ),
      ));
      await tester.pump();

      expect(find.text('tech'), findsOneWidget);
      expect(find.text('design'), findsOneWidget);
      expect(find.text('art'), findsOneWidget);
    });

    testWidgets('无头像时显示默认图标', (tester) async {
      await tester.pumpWidget(_wrap(
        const CircleHeader(
          isDark: false,
          name: 'No Avatar Circle',
        ),
      ));
      await tester.pump();

      expect(find.byIcon(CupertinoIcons.person_3_fill), findsOneWidget);
    });

    testWidgets('深色模式正确渲染', (tester) async {
      await tester.pumpWidget(_wrap(
        const CircleHeader(
          isDark: true,
          name: 'Dark Mode Circle',
          description: 'Dark mode test',
        ),
      ));
      await tester.pump();

      expect(find.text('Dark Mode Circle'), findsOneWidget);
      expect(find.text('Dark mode test'), findsOneWidget);
    });
  });

  group('CircleHeader — 交互契约', () {
    testWidgets('长名称文本截断不崩溃', (tester) async {
      await tester.pumpWidget(_wrap(
        CircleHeader(
          isDark: false,
          name: 'A' * 200,
          description: 'B' * 500,
        ),
      ));
      await tester.pump();

      expect(find.byType(CircleHeader), findsOneWidget);
    });

    testWidgets('大量标签渲染时 Wrap 正确工作', (tester) async {
      await tester.pumpWidget(_wrap(
        CircleHeader(
          isDark: false,
          name: 'Many Tags',
          tags: List.generate(20, (i) => 'tag_$i'),
        ),
      ));
      await tester.pump();

      expect(find.byType(CircleHeader), findsOneWidget);
      expect(find.byType(Wrap), findsOneWidget);
    });
  });

  group('CircleHeader — 错误态渲染', () {
    testWidgets('空名称安全渲染', (tester) async {
      await tester.pumpWidget(_wrap(
        const CircleHeader(
          isDark: false,
          name: '',
        ),
      ));
      await tester.pump();

      expect(find.byType(CircleHeader), findsOneWidget);
    });

    testWidgets('无描述和标签安全渲染', (tester) async {
      await tester.pumpWidget(_wrap(
        const CircleHeader(
          isDark: false,
          name: 'Minimal Circle',
        ),
      ));
      await tester.pump();

      expect(find.text('Minimal Circle'), findsOneWidget);
      expect(find.byType(Wrap), findsNothing);
    });

    testWidgets('空头像 URL 降级为默认图标', (tester) async {
      await tester.pumpWidget(_wrap(
        const CircleHeader(
          isDark: false,
          avatarUrl: '',
          name: 'Empty URL',
        ),
      ));
      await tester.pump();

      expect(find.byIcon(CupertinoIcons.person_3_fill), findsOneWidget);
    });

    testWidgets('空标签列表不渲染 Wrap', (tester) async {
      await tester.pumpWidget(_wrap(
        const CircleHeader(
          isDark: false,
          name: 'No Tags',
          tags: [],
        ),
      ));
      await tester.pump();

      expect(find.byType(Wrap), findsNothing);
    });
  });

  // ── N8：成员簇归一到统一交集视觉簇（IntersectionVisualCluster），不再裸 URL 自绘 ──
  group('CircleHeader — 成员视觉簇标准化', () {
    testWidgets('有 memberVisuals 时渲染统一 IntersectionVisualCluster', (tester) async {
      await tester.pumpWidget(_wrap(
        CircleHeader(
          isDark: false,
          name: 'Cluster Circle',
          memberVisuals: <IntersectionVisual>[
            IntersectionVisual(
              assetKind: 'avatar',
              imageUrl: 'media/a.png',
              displayName: '林清越',
            ),
            IntersectionVisual(
              assetKind: 'avatar',
              imageUrl: 'media/b.png',
              displayName: '周野',
            ),
          ],
        ),
      ));
      await tester.pump();

      // 统一组件出现，且挂在约定 key 上（替代旧裸 CircleAvatar Stack 自绘）。
      expect(find.byType(IntersectionVisualCluster), findsOneWidget);
      expect(
        find.byKey(const ValueKey<String>('circle-header-member-cluster')),
        findsOneWidget,
      );
    });

    testWidgets('memberVisuals 为空时不渲染视觉簇（G2 不占位）', (tester) async {
      await tester.pumpWidget(_wrap(
        const CircleHeader(
          isDark: false,
          name: 'No Cluster Circle',
        ),
      ));
      await tester.pump();

      expect(find.byType(IntersectionVisualCluster), findsNothing);
    });
  });
}
