import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'web_shell_test_harness.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
  });

  group('Web 消息页', () {
    testWidgets('去掉「消息助手」上下文，改为中性消息中心，且无小趣助手 tab', (tester) async {
      WebShellTestHarness.suppressExpectedErrors();
      WebShellTestHarness.useWideViewport(tester);

      await tester.pumpWidget(WebShellTestHarness.build(authenticated: true));
      await WebShellTestHarness.enterToolbar(tester);
      await WebShellTestHarness.tapPrimary(tester, 'chat');

      // 右侧说明栏已移除，不再展示占位 rail 文案。
      expect(find.text(UITextConstants.webPcMessagesRailTitle), findsNothing);
      expect(find.text('消息助手'), findsNothing);

      // 上下文 tab 与移动端主 tab 对齐，去掉「小趣」助手入口。
      expect(
        find.byKey(const ValueKey<String>('web-context-tab-messages')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('web-context-tab-contacts')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('web-context-tab-xiaoqu')),
        findsNothing,
      );

      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump(const Duration(seconds: 1));
    });
  });
}
