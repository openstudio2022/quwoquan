import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

const _inlinePrimaryTabsKey = ValueKey<String>(
  'profile-shell-primary-tabs-inline',
);

/// 摘要区（连接卡 + 影响力卡 + 四列统计）变高后，一级 Tab 不再保证首屏内；
/// 交互前先把 ObjectPageShell 滚到一级 Tab 可见（lazy sliver 需滚动才构建），
/// 并回滚出 pinned 工具栏遮挡区，保证 inline Tab 可命中。
Future<void> revealProfilePrimaryTabs(WidgetTester tester) async {
  final tabs = find.byKey(_inlinePrimaryTabsKey);
  if (tabs.evaluate().isEmpty) {
    await tester.scrollUntilVisible(
      tabs,
      120,
      scrollable: find.byType(Scrollable).first,
      maxScrolls: 40,
    );
    await tester.pump();
  }
  // inline Tab 滚到顶部会被 pinned 工具栏盖住（点击由 pinned overlay 接管），
  // 测试统一回滚到工具栏以下，保持 inline Tab 直接可点。
  final rect = tester.getRect(tabs.first);
  const safeTop = 160.0;
  if (rect.top < safeTop) {
    await tester.drag(
      find.byType(Scrollable).first,
      Offset(0, safeTop - rect.top),
      warnIfMissed: false,
    );
    await tester.pump();
  }
}

/// 把摘要区内任意目标滚到可命中位置（先 ensureVisible，再滚出 pinned 工具栏遮挡区）。
Future<void> revealProfileSummaryWidget(
  WidgetTester tester,
  Finder finder,
) async {
  if (finder.evaluate().isEmpty) {
    await tester.scrollUntilVisible(
      finder,
      120,
      scrollable: find.byType(Scrollable).first,
      maxScrolls: 40,
    );
  } else {
    await tester.ensureVisible(finder.first);
  }
  await tester.pump();
  final rect = tester.getRect(finder.first);
  const safeTop = 160.0;
  if (rect.top < safeTop) {
    await tester.drag(
      find.byType(Scrollable).first,
      Offset(0, safeTop - rect.top),
      warnIfMissed: false,
    );
    await tester.pump();
  }
}

/// 滚动至一级 Tab 可点后点击指定 label 的 Tab。
Future<void> tapProfilePrimaryTab(WidgetTester tester, String label) async {
  await revealProfilePrimaryTabs(tester);
  final tab = find.descendant(
    of: find.byKey(_inlinePrimaryTabsKey),
    matching: find.text(label),
  );
  await tester.tap(tab.first, warnIfMissed: false);
  await tester.pump();
}
