import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/presentation/login_page.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../support/runtime/shell/web/web_shell_test_harness.dart';
import '../../../support/service/content_service/content/post/content_facet_overrides.dart';
import '../../../support/service/content_service/content/post/mock_content_repository.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
  });

  group('Web 宽屏登录入口契约', () {
    testWidgets('未登录点击消息入口进入 openChat 登录门', (tester) async {
      WebShellTestHarness.suppressExpectedErrors();
      WebShellTestHarness.useWideViewport(tester);
      AuthGate.resetDebounce();

      await tester.pumpWidget(WebShellTestHarness.build(
        authenticated: false,
        businessOverrides: mockContentFacetOverrides(MockContentRepository()),
      ));
      await WebShellTestHarness.enterToolbar(tester);
      await WebShellTestHarness.tapPrimary(tester, 'chat');
      await tester.pump(const Duration(milliseconds: 600));

      final login = tester.widget<LoginPage>(find.byType(LoginPage));
      expect(login.reason, AuthGateReason.openChat.name);
    });

    testWidgets('未登录点击我的入口进入 profileTab 登录门', (tester) async {
      WebShellTestHarness.suppressExpectedErrors();
      WebShellTestHarness.useWideViewport(tester);
      AuthGate.resetDebounce();

      await tester.pumpWidget(WebShellTestHarness.build(
        authenticated: false,
        businessOverrides: mockContentFacetOverrides(MockContentRepository()),
      ));
      await WebShellTestHarness.enterToolbar(tester);
      await WebShellTestHarness.tapPrimary(tester, 'profile');
      await tester.pump(const Duration(milliseconds: 600));

      final login = tester.widget<LoginPage>(find.byType(LoginPage));
      expect(login.reason, AuthGateReason.profileTab.name);
    });
  });
}
