import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/circle/providers/circle_state_provider.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_creations.dart';

Widget _buildApp(Widget child) {
  return ProviderScope(
    overrides: [
      circleRepositoryProvider.overrideWithValue(MockCircleRepository()),
    ],
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: '/',
        routes: [
          GoRoute(
            path: '/',
            builder: (_, _) => Scaffold(body: child),
          ),
          GoRoute(path: '/article/:id', builder: (_, _) => const SizedBox()),
          GoRoute(path: '/chat/:id', builder: (_, _) => const SizedBox()),
        ],
      ),
    ),
  );
}

void main() {
  testWidgets('圈子创作容器先展示全部/点滴/作品，再进入作品格式筛选', (tester) async {
    await tester.pumpWidget(
      _buildApp(
        const SizedBox(
          height: 800,
          child: SectionCreations(
            circleId: 'circle_photo_01',
            isDark: false,
            role: CircleRole.owner,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('全部'), findsOneWidget);
    expect(find.text('点滴'), findsOneWidget);
    expect(find.text('作品'), findsAtLeastNWidgets(1));
    expect(find.text('微趣'), findsNothing);
    expect(find.text('笔记'), findsNothing);

    await tester.tap(find.text('作品').first);
    await tester.pumpAndSettle();

    expect(find.text('图片'), findsAtLeastNWidgets(1));
    expect(find.text('视频'), findsAtLeastNWidgets(1));
    expect(find.text('笔记'), findsAtLeastNWidgets(1));
  });

  testWidgets('圈子作品切到笔记后，列表标签与筛选口径保持一致', (tester) async {
    await tester.pumpWidget(
      _buildApp(
        const SizedBox(
          height: 800,
          child: SectionCreations(
            circleId: 'circle_photo_01',
            isDark: false,
            role: CircleRole.owner,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('作品').first);
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('列表视图'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('笔记').first);
    await tester.pumpAndSettle();

    expect(find.text('笔记'), findsAtLeastNWidgets(2));
    expect(find.textContaining('赞 '), findsWidgets);
  });
}
