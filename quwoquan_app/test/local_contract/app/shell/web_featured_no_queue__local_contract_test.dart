import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/content/content/post/presentation/home_multi_form_feed.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../support/app/web_shell_test_harness.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
  });

  group('Web 视频书页', () {
    testWidgets('改为复用发现内容流的多列墙，无旧精品队列', (tester) async {
      WebShellTestHarness.suppressExpectedErrors();
      WebShellTestHarness.useWideViewport(tester);

      await tester.pumpWidget(WebShellTestHarness.build(authenticated: true));
      await WebShellTestHarness.enterToolbar(tester);
      await WebShellTestHarness.tapPrimary(tester, 'featured');

      // 视频书默认 filter=all → 发现频道 work，复用 HomeMultiFormFeed 多列墙。
      expect(
        find.byKey(const ValueKey<String>('web-content-feed-work')),
        findsOneWidget,
      );
      expect(find.byType(HomeMultiFormFeed), findsOneWidget);

      // 旧的精品队列语义被移除，rail 文案不再含「队列」。
      expect(find.textContaining('队列'), findsNothing);

      // 右侧说明栏已移除，不再展示占位 rail 文案。
      expect(find.text(DiscoveryText.webPcFeaturedRailTitle), findsNothing);

      // format 筛选 tab 仍可用（图片/视频/图文）。
      expect(find.text(DiscoveryText.workFormatFilterImage), findsOneWidget);
      expect(find.text(DiscoveryText.workFormatFilterVideo), findsWidgets);
    });
  });
}
