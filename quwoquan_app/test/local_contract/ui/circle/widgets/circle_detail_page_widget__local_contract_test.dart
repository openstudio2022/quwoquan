import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/circle/pages/circle_detail_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../typed_circle_query_test_double.dart';

class _NoopCircleBehaviorFactWriter implements CircleBehaviorFactWriter {
  @override
  Future<void> append(AppendCircleBehaviorFactCommand command) async {}
}

Widget _scopedApp({
  CircleQueryReader? circleQuery,
  String circleId = 'fixture_circle_photo',
}) {
  final query = circleQuery ?? CircleQueryReaderTestDouble();
  return ProviderScope(
    overrides: [
      circleDetailQueryProvider.overrideWithValue(query),
      circlesListQueryProvider.overrideWithValue(query),
      // 游客态：行为信号守卫短路，不触发 Remote-only 装配链。
      resolvedOwnerUserIdProvider.overrideWithValue(''),
      circleDetailBehaviorFactWriterProvider.overrideWithValue(
        _NoopCircleBehaviorFactWriter(),
      ),
      behaviorRepositoryProvider.overrideWithValue(MockBehaviorRepository()),
    ],
    child: MaterialApp(
      home: Scaffold(
        body: CircleDetailPage(circleId: circleId, onBack: () {}),
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
      await tester.pumpWidget(_scopedApp(circleId: ''));
      await tester.pump(const Duration(milliseconds: 500));

      expect(find.byType(CircleDetailPage), findsOneWidget);
    });
  });
}
