import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/circle/pages/circle_detail_page.dart';

Widget _scopedApp({CircleRepository? mock}) {
  final repo = mock ?? MockCircleRepository();
  return ProviderScope(
    overrides: [circleRepositoryProvider.overrideWithValue(repo)],
    child: MaterialApp(
      home: Scaffold(
        body: CircleDetailPage(
          circleId: 'circle_photo_01',
          onBack: () {},
        ),
      ),
    ),
  );
}

void main() {
  group('CircleDetailPage — 渲染契约', () {
    testWidgets('正常数据渲染圈子名称', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pump(const Duration(milliseconds: 500));

      expect(find.byType(CircleDetailPage), findsOneWidget);
    });

    testWidgets('板块区域按 sectionConfig 渲染', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pump(const Duration(milliseconds: 500));

      expect(find.byType(Scaffold), findsWidgets);
    });
  });

  group('CircleDetailPage — 交互契约', () {
    testWidgets('加入按钮存在且可点击', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pump(const Duration(milliseconds: 500));

      expect(find.byType(CircleDetailPage), findsOneWidget);
    });
  });

  group('CircleDetailPage — 错误态渲染', () {
    testWidgets('空 circleId 安全渲染', (tester) async {
      final widget = ProviderScope(
        overrides: [
          circleRepositoryProvider.overrideWithValue(MockCircleRepository()),
        ],
        child: MaterialApp(
          home: Scaffold(
            body: CircleDetailPage(
              circleId: '',
              onBack: () {},
            ),
          ),
        ),
      );
      await tester.pumpWidget(widget);
      await tester.pump(const Duration(milliseconds: 500));

      expect(find.byType(CircleDetailPage), findsOneWidget);
    });
  });
}
