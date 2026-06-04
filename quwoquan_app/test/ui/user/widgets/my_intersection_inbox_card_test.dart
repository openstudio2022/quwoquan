import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_inbox_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/widgets/my_intersection_inbox_card.dart';

/// 空摘要 Repository：用于验证空态文案（用户语言、不占位为工程术语）。
class _EmptyIntersectionRepository implements IntersectionRepository {
  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async {
    return IntersectionInboxSummary(totalCount: 0, totalNewCount: 0);
  }

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    int limit = 50,
  }) async => const <IntersectionReason>[];

  @override
  Future<void> markIntersectionsVisited({String? dimension}) async {}

  @override
  Future<List<IntersectionReason>> getFeedIntersections({
    String? channel,
    int limit = 4,
  }) async => const <IntersectionReason>[];

  @override
  Future<void> reportExposure({required List<String> objectIds}) async {}
}

Widget _scope(ProviderContainer container) {
  return UncontrolledProviderScope(
    container: container,
    child: const CupertinoApp(
      home: CupertinoPageScaffold(
        child: SafeArea(
          child: Padding(
            padding: EdgeInsets.all(16),
            child: MyIntersectionInboxCard(isDark: false),
          ),
        ),
      ),
    ),
  );
}

void main() {
  testWidgets('我的交集卡：默认折叠最多 3 维度，超出显示「展开更多」', (tester) async {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    await tester.pumpWidget(_scope(container));
    // 等待 summary 异步加载（initState microtask）。
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text(UITextConstants.myIntersectionsTitle), findsOneWidget);
    // 我的主页是统计卡：突出云侧 summary.totalCount，不渲染对象列表项。
    expect(find.text('6'), findsWidgets);
    expect(find.text('林清越'), findsNothing);
    // mock 含 5 维度，折叠态显示 3 + 「展开更多」。
    expect(find.text(UITextConstants.intersectionExpandMore), findsOneWidget);

    await tester.tap(find.text(UITextConstants.intersectionExpandMore));
    await tester.pump();
    // 展开后变为「收起」。
    expect(find.text(UITextConstants.intersectionCollapse), findsOneWidget);
  });

  testWidgets('我的交集卡：无交集时显示用户语言空态', (tester) async {
    final container = ProviderContainer(
      overrides: [
        intersectionRepositoryProvider.overrideWithValue(
          _EmptyIntersectionRepository(),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(_scope(container));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text(UITextConstants.myIntersectionsEmpty), findsOneWidget);
    // 空态不展示「展开更多」。
    expect(find.text(UITextConstants.intersectionExpandMore), findsNothing);
  });
}
