import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'web_shell_test_harness.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
  });

  group('Web 添加页', () {
    testWidgets('按内容创作/社交关系两组呈现，含发起群聊，且无小趣创作助手', (tester) async {
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
        find.byKey(const ValueKey<String>('web-create-card-gallery')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('web-create-card-write')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('web-create-card-drafts')),
        findsOneWidget,
      );

      // 社交关系组：发起群聊 / 添加联系人 / 创建圈子。
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
        find.text(UITextConstants.webPcCreateContentGroupTitle),
        findsOneWidget,
      );
      expect(
        find.text(UITextConstants.webPcCreateSocialGroupTitle),
        findsOneWidget,
      );
      expect(
        find.text(UITextConstants.webPcCreateGroupChatTitle),
        findsOneWidget,
      );

      // 去掉「小趣创作助手」上下文标题（不再出现）。
      expect(find.text('小趣创作助手'), findsNothing);
    });
  });
}
