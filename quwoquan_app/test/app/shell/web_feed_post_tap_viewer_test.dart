import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/discovery/widgets/home_multi_form_feed.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'web_shell_test_harness.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
  });

  group('Web 首页内容流', () {
    testWidgets('复用移动端 HomeMultiFormFeed，post 可点击进沉浸 viewer（同源动作已接线）', (
      tester,
    ) async {
      WebShellTestHarness.suppressExpectedErrors();
      WebShellTestHarness.useWideViewport(tester);

      await tester.pumpWidget(WebShellTestHarness.build(authenticated: true));
      await WebShellTestHarness.enterToolbar(tester);

      // 首页默认 recommend 频道复用移动端内容流组件。
      final feedFinder = find.byKey(
        const ValueKey<String>('web-content-feed-recommend'),
      );
      expect(feedFinder, findsOneWidget);

      final feed = tester.widget<HomeMultiFormFeed>(feedFinder);
      // post 点击动作已接线（→ openHomeFeedPost → MediaViewerExtra → viewer），
      // 不是 Web 自绘的不可点卡片；作者点击也复用作者主页 route。
      expect(feed.onPostTap, isNotNull);
      expect(feed.onUserTap, isNotNull);
      // 频道与宿主上下文一致（同源数据链，不另起 Web feed query）。
      expect(feed.channelId, 'recommend');
    });
  });
}
