import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'web_shell_test_harness.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
  });

  group('Web 宽屏登录入口契约', () {
    testWidgets('未登录点击消息入口进入 openChat 登录门', (tester) async {
      WebShellTestHarness.suppressExpectedErrors();
      WebShellTestHarness.useWideViewport(tester);
      AuthGate.resetDebounce();

      await tester.pumpWidget(WebShellTestHarness.build(authenticated: false));
      await WebShellTestHarness.enterToolbar(tester);
      await WebShellTestHarness.tapPrimary(tester, 'chat');
      await tester.pump(const Duration(milliseconds: 600));

      expect(find.text(AuthGateReason.openChat.title), findsAtLeastNWidgets(1));
    });

    testWidgets('未登录点击我的入口进入 profileTab 登录门', (tester) async {
      WebShellTestHarness.suppressExpectedErrors();
      WebShellTestHarness.useWideViewport(tester);
      AuthGate.resetDebounce();

      await tester.pumpWidget(WebShellTestHarness.build(authenticated: false));
      await WebShellTestHarness.enterToolbar(tester);
      await WebShellTestHarness.tapPrimary(tester, 'profile');
      await tester.pump(const Duration(milliseconds: 600));

      expect(
        find.text(AuthGateReason.profileTab.title),
        findsAtLeastNWidgets(1),
      );
    });
  });
}
