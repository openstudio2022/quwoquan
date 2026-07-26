import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/conversation/conversation_link_action_sheet.dart';
import 'package:quwoquan_app/core/constants/assistant_text_constants.dart';
import 'package:quwoquan_app/core/widgets/app_modal_surface.dart';

void main() {
  testWidgets('会话链接动作以统一底部面板展示并返回浏览器打开动作', (tester) async {
    ConversationLinkAction? result;
    const url = 'https://example.com/reference';

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) => CupertinoButton(
              onPressed: () async {
                result = await showConversationLinkActionSheet(
                  context,
                  url: url,
                  allowOpenInBrowser: true,
                );
              },
              child: const Text('open-link-actions'),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('open-link-actions'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.byType(AppBottomModalSurface), findsOneWidget);
    expect(find.byType(CupertinoActionSheet), findsNothing);
    expect(
      find.text(AssistantText.assistantReferenceActionTitle),
      findsOneWidget,
    );
    expect(find.text(url), findsOneWidget);
    expect(
      find.text(AssistantText.assistantReferenceOpenInBrowser),
      findsOneWidget,
    );
    expect(find.text(AssistantText.assistantReferenceCopyLink), findsOneWidget);

    await tester.tap(find.text(AssistantText.assistantReferenceOpenInBrowser));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(result, equals(ConversationLinkAction.openInBrowser));
  });

  testWidgets('禁用浏览器打开时仅保留复制链接动作', (tester) async {
    ConversationLinkAction? result;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) => CupertinoButton(
              onPressed: () async {
                result = await showConversationLinkActionSheet(
                  context,
                  url: 'https://example.com/reference',
                  allowOpenInBrowser: false,
                );
              },
              child: const Text('open-link-actions'),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('open-link-actions'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.byType(AppBottomModalSurface), findsOneWidget);
    expect(
      find.text(AssistantText.assistantReferenceOpenInBrowser),
      findsNothing,
    );
    expect(find.text(AssistantText.assistantReferenceCopyLink), findsOneWidget);

    await tester.tap(find.text(AssistantText.assistantReferenceCopyLink));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(result, equals(ConversationLinkAction.copyLink));
  });
}
