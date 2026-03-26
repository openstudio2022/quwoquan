import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/search/pages/search_network_results_page.dart';
import 'package:quwoquan_app/ui/entity/widgets/homepage_summary_card.dart';

Widget _buildApp({
  SearchLaunchContext launchContext = const SearchLaunchContext(
    entrySurfaceId: '/search',
    prefilledQuery: '影',
    initialNetworkTabId: 'xiaoqu',
  ),
}) {
  return ProviderScope(
    child: MaterialApp(
      home: SearchNetworkResultsPage(launchContext: launchContext),
    ),
  );
}

void main() {
  testWidgets('网络结果页展示小趣搜和圈子频道分类', (tester) async {
    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    expect(find.text('小趣搜'), findsWidgets);
    expect(find.text('推荐'), findsOneWidget);
    expect(find.text('人文'), findsOneWidget);
    expect(find.textContaining('正在为你整理'), findsOneWidget);
  });

  testWidgets('切换频道后展示对应分类结果', (tester) async {
    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    await tester.tap(find.text('人文'));
    await tester.pumpAndSettle();

    expect(find.textContaining('人文'), findsWidgets);
    expect(find.text('街头摄影'), findsWidgets);
  });

  testWidgets('主页 tab 可展示共享主页结果', (tester) async {
    await tester.pumpWidget(
      _buildApp(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '西湖',
          initialNetworkTabId: 'homepages',
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('主页'), findsOneWidget);
    expect(find.text('西湖景区'), findsWidgets);
    expect(find.textContaining('共享主页并进入详情'), findsOneWidget);
    expect(find.byType(HomepageSummaryCard), findsWidgets);
  });

  testWidgets('内容类型筛选可驱动网络结果页加载指定内容结果', (tester) async {
    await tester.pumpWidget(
      _buildApp(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: 'UI',
          initialNetworkTabId: 'all',
          searchObjectSelection: SearchObjectSelection(
            contentTypes: <SearchContentTypeFilter>{
              SearchContentTypeFilter.article,
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('UI设计的心理学原理：色彩、布局与用户认知'), findsWidgets);
  });
}
