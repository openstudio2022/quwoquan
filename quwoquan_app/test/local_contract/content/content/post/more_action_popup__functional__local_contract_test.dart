import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/settings_conversation/more_actions_popup/configs/media_post_config.dart';
import 'package:quwoquan_app/components/settings_conversation/more_actions_popup/more_action_popup.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

void main() {
  testWidgets('更多面板只展示有真实动作的入口', (tester) async {
    var reportCalls = 0;
    await tester.pumpWidget(
      ProviderScope(
        child: CupertinoApp(
          home: Builder(
            builder: (context) => CupertinoButton(
              onPressed: () => MoreActionPopup.show(
                context: context,
                config: MediaPostMoreActionConfig(
                  onCopyLink: () {},
                  onNotInterested: () {},
                  onBlockUser: () {},
                  onBlockWords: () {},
                  onReport: () => reportCalls += 1,
                ),
              ),
              child: const Text(ContentText.moreActionsTitle),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text(ContentText.moreActionsTitle));
    await tester.pumpAndSettle();

    expect(find.text(FoundationText.copyLink), findsOneWidget);
    expect(find.text(ContentText.notInterested), findsOneWidget);
    expect(find.text(ContentText.blockAuthor), findsOneWidget);
    expect(find.text(ContentText.blockKeywords), findsOneWidget);
    expect(find.text(ContentText.report), findsOneWidget);
    expect(find.text('打赏'), findsNothing);
    expect(find.text('私信'), findsNothing);
    expect(find.text('字体设置'), findsNothing);
    expect(find.text('功能反馈'), findsNothing);

    await tester.tap(find.text(ContentText.report));
    await tester.pumpAndSettle();
    expect(reportCalls, 1);
  });

  testWidgets('未提供回调的治理动作不会渲染成静默关闭项', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        child: CupertinoApp(
          home: Builder(
            builder: (context) => CupertinoButton(
              onPressed: () => MoreActionPopup.show(
                context: context,
                config: const MediaPostMoreActionConfig(),
              ),
              child: const Text(ContentText.moreActionsTitle),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text(ContentText.moreActionsTitle));
    await tester.pumpAndSettle();

    expect(find.text(ContentText.notInterested), findsNothing);
    expect(find.text(ContentText.blockAuthor), findsNothing);
    expect(find.text(ContentText.blockKeywords), findsNothing);
    expect(find.text(ContentText.report), findsNothing);
  });
}
