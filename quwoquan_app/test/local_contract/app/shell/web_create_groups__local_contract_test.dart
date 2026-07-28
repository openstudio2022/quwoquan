// spec_ref: specs/feature-tree/chat-conversation/group-creation-member-management/group-create-flow/spec.md#gwt-001
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/user/pages/login_page.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../support/app/web_shell_test_harness.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
  });

  group('Web 添加页', () {
    testWidgets('按创作方式/社交关系两组呈现，且无小趣创作助手', (tester) async {
      WebShellTestHarness.suppressExpectedErrors();
      WebShellTestHarness.useWideViewport(tester);

      await tester.pumpWidget(WebShellTestHarness.build(authenticated: true));
      await WebShellTestHarness.enterToolbar(tester);
      await WebShellTestHarness.tapPrimary(tester, 'create');

      // 两个分组容器都在。
      expect(
        find.byKey(const ValueKey<String>('web-create-group-content')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('web-create-group-social')),
        findsOneWidget,
      );

      // 内容创作组卡片。
      expect(
        find.byKey(const ValueKey<String>('web-create-card-album')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('web-create-card-camera')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('web-create-card-write')),
        findsOneWidget,
      );
      expect(
        find.text(DiscoveryText.webPcCreateGalleryTitle),
        findsOneWidget,
      );
      expect(
        find.text(DiscoveryText.webPcCreateGallerySubtitle),
        findsOneWidget,
      );
      expect(find.text(DiscoveryText.webPcCreateCameraTitle), findsOneWidget);
      expect(
        find.text(DiscoveryText.webPcCreateCameraSubtitle),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('web-create-card-drafts')),
        findsNothing,
      );

      // 社交关系组：添加联系人 / 发起群聊 / 创建圈子。
      expect(
        find.byKey(const ValueKey<String>('web-create-card-group-chat')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('web-create-card-add-contact')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('web-create-card-create-circle')),
        findsOneWidget,
      );

      // 分组标题语义 token。
      expect(
        find.text(DiscoveryText.webPcCreateContentGroupTitle),
        findsOneWidget,
      );
      expect(
        find.text(DiscoveryText.webPcCreateSocialGroupTitle),
        findsOneWidget,
      );
      expect(find.text(ChatText.webPcCreateGroupChatTitle), findsOneWidget);

      // 去掉「小趣创作助手」上下文标题（不再出现）。
      expect(find.text('小趣创作助手'), findsNothing);
    });

    testWidgets('游客从网页发起群聊先登录，关闭后不回环', (tester) async {
      AuthGate.resetDebounce();
      WebShellTestHarness.suppressExpectedErrors();
      WebShellTestHarness.useWideViewport(tester);

      await tester.pumpWidget(WebShellTestHarness.build(authenticated: false));
      await WebShellTestHarness.enterToolbar(tester);
      await WebShellTestHarness.tapPrimary(tester, 'create');
      await tester.tap(
        find.byKey(const ValueKey<String>('web-create-card-group-chat')),
      );
      await tester.pumpAndSettle();

      expect(find.byType(LoginPage), findsOneWidget);

      await tester.tap(find.byIcon(CupertinoIcons.xmark));
      await tester.pumpAndSettle();

      expect(find.byType(LoginPage), findsNothing);
      await tester.pump(const Duration(seconds: 1));
      expect(find.byType(LoginPage), findsNothing);
    });
  });
}
