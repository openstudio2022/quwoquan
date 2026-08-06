// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/commercial-remote-only-message-system/spec.md#gwt-001
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/message_receipt_sheet.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  testWidgets('typed receipt rows render member identity and read time', (
    tester,
  ) async {
    await tester.pumpWidget(
      CupertinoApp(
        home: MessageReceiptSheet(
          receipts: <ChatMessageReceipt>[
            ChatMessageReceipt(
              id: 'receipt_1',
              messageId: 'message_1',
              conversationId: 'conversation_1',
              userId: 'persona_1',
              readAt: DateTime.utc(2026, 8, 6, 2, 30),
            ),
          ],
          displayNames: const <String, String>{'persona_1': '林墨'},
        ),
      ),
    );

    expect(find.text(ChatText.messageReceiptTitle), findsOneWidget);
    expect(find.text('林墨'), findsOneWidget);
    expect(
      find.byIcon(CupertinoIcons.check_mark_circled_solid),
      findsOneWidget,
    );
  });

  testWidgets('legal empty receipt result remains an explicit empty state', (
    tester,
  ) async {
    await tester.pumpWidget(
      const CupertinoApp(home: MessageReceiptSheet(receipts: [])),
    );

    expect(find.text(ChatText.messageReceiptEmpty), findsOneWidget);
  });
}
