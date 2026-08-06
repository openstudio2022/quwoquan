// spec_ref: specs/feature-tree/chat-conversation/group-creation-member-management/group-create-flow/spec.md#gwt-001
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/presentation/login_page.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../support/runtime/shell/web/web_shell_test_harness.dart';
import '../../../support/service/content_service/content/post/content_facet_overrides.dart';
import '../../../support/service/content_service/content/post/mock_content_repository.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
  });

  group('Web 添加页', () {
    testWidgets('首层固定发内容活动群聊，发内容后二级固定照片视频文字', (tester) async {
      WebShellTestHarness.suppressExpectedErrors();
      WebShellTestHarness.useWideViewport(tester);

      await tester.pumpWidget(
        WebShellTestHarness.build(
          authenticated: true,
          businessOverrides: mockContentFacetOverrides(MockContentRepository()),
        ),
      );
      await WebShellTestHarness.enterToolbar(tester);
      await WebShellTestHarness.tapPrimary(tester, 'create');

      // 首层只展示三项具体方向和取消。
      expect(
        find.byKey(const ValueKey<String>('web-create-actions')),
        findsOneWidget,
      );
      expect(
        find.byKey(TestKeys.webCreateActionPublishContent),
        findsOneWidget,
      );
      expect(
        find.byKey(TestKeys.webCreateActionStartGathering),
        findsOneWidget,
      );
      expect(
        find.byKey(TestKeys.webCreateActionStartGroupChat),
        findsOneWidget,
      );
      expect(find.byKey(TestKeys.webCreateActionCancel), findsOneWidget);
      expect(find.text(ChatText.webPcCreateGroupChatTitle), findsOneWidget);
      expect(
        find.byKey(const ValueKey<String>('web-create-card-album')),
        findsNothing,
      );
      expect(
        find.byKey(const ValueKey<String>('web-create-card-camera')),
        findsNothing,
      );
      expect(
        find.byKey(const ValueKey<String>('web-create-card-write')),
        findsNothing,
      );
      expect(
        find.byKey(const ValueKey<String>('web-create-card-add-contact')),
        findsNothing,
      );
      expect(
        find.byKey(const ValueKey<String>('web-create-card-create-circle')),
        findsNothing,
      );

      await tester.tap(find.byKey(TestKeys.webCreateActionPublishContent));
      await tester.pump();

      expect(find.byKey(TestKeys.webCreateActionPublishContent), findsNothing);
      expect(find.byKey(TestKeys.webCreateActionStartGathering), findsNothing);
      expect(find.byKey(TestKeys.webCreateActionStartGroupChat), findsNothing);
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
      expect(find.text(DiscoveryText.webPcCreateGalleryTitle), findsOneWidget);
      expect(find.text(DiscoveryText.webPcCreateCameraTitle), findsOneWidget);
      expect(find.text(DiscoveryText.webPcCreateTextTitle), findsOneWidget);
    });

    testWidgets('游客从网页发起群聊先登录，关闭后不回环', (tester) async {
      AuthGate.resetDebounce();
      WebShellTestHarness.suppressExpectedErrors();
      WebShellTestHarness.useWideViewport(tester);

      await tester.pumpWidget(
        WebShellTestHarness.build(
          authenticated: false,
          businessOverrides: mockContentFacetOverrides(MockContentRepository()),
        ),
      );
      await WebShellTestHarness.enterToolbar(tester);
      await WebShellTestHarness.tapPrimary(tester, 'create');
      await tester.tap(find.byKey(TestKeys.webCreateActionStartGroupChat));
      await tester.pumpAndSettle();

      expect(find.byType(LoginPage), findsOneWidget);

      await tester.tap(find.byIcon(CupertinoIcons.xmark));
      await tester.pumpAndSettle();

      expect(find.byType(LoginPage), findsNothing);
      expect(find.byKey(TestKeys.webCreateActionStartGathering), findsNothing);
      await tester.pump(const Duration(seconds: 1));
      expect(find.byType(LoginPage), findsNothing);
    });

    testWidgets('游客从网页发起活动先登录，关闭后回安全首页且不回环', (tester) async {
      AuthGate.resetDebounce();
      WebShellTestHarness.suppressExpectedErrors();
      WebShellTestHarness.useWideViewport(tester);

      await tester.pumpWidget(
        WebShellTestHarness.build(
          authenticated: false,
          businessOverrides: mockContentFacetOverrides(MockContentRepository()),
        ),
      );
      await WebShellTestHarness.enterToolbar(tester);
      await WebShellTestHarness.tapPrimary(tester, 'create');
      await tester.tap(find.byKey(TestKeys.webCreateActionStartGathering));
      await tester.pumpAndSettle();

      expect(find.byType(LoginPage), findsOneWidget);

      await tester.tap(find.byIcon(CupertinoIcons.xmark));
      await tester.pumpAndSettle();

      expect(find.byType(LoginPage), findsNothing);
      expect(find.byKey(TestKeys.webCreateActionStartGathering), findsNothing);
      await tester.pump(const Duration(seconds: 1));
      expect(find.byType(LoginPage), findsNothing);
    });
  });
}
