// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/commercial-remote-only-message-system/spec.md#gwt-001
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_message_display_item.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/message_action_menu_overlay.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';

void main() {
  group('ConversationMessageActionMenuOverlay', () {
    testWidgets('文本消息展示复制与撤回动作，并在点击后关闭菜单', (tester) async {
      String? triggeredAction;
      var closed = false;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ConversationMessageActionMenuOverlay(
              message: _message(
                type: 'text',
                isSelf: true,
                sentAtIso: DateTime.now().toIso8601String(),
              ),
              position: const Offset(160, 240),
              onAction: (action) => triggeredAction = action,
              onClose: () => closed = true,
            ),
          ),
        ),
      );

      expect(find.text(ChatText.messageActionCopy), findsOneWidget);
      expect(find.text(ChatText.messageActionRecall), findsOneWidget);

      await tester.tap(find.text(ChatText.messageActionCopy));
      await tester.pump();

      expect(triggeredAction, 'copy');
      expect(closed, isTrue);
    });

    testWidgets('非文本他人消息不展示复制与撤回动作', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ConversationMessageActionMenuOverlay(
              message: _message(type: 'image', isSelf: false),
              position: Offset(160, 240),
              onAction: _noopAction,
              onClose: _noopClose,
            ),
          ),
        ),
      );

      expect(find.text(ChatText.messageActionCopy), findsNothing);
      expect(find.text(ChatText.messageActionRecall), findsNothing);
      // 服务端没有 DeleteMessage 契约，菜单不得暴露无副作用的假删除入口。
      expect(find.text(ChatText.messageActionDelete), findsNothing);
      expect(find.text(ChatText.messageActionForward), findsOneWidget);
      expect(find.text(ChatText.messageActionSelect), findsOneWidget);
    });

    testWidgets('仅在会话开启回执时为自己发送的消息展示已读回执动作', (tester) async {
      String? triggeredAction;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ConversationMessageActionMenuOverlay(
              message: _message(type: 'text', isSelf: true),
              position: const Offset(160, 240),
              receiptEnabled: true,
              onAction: (action) => triggeredAction = action,
              onClose: _noopClose,
            ),
          ),
        ),
      );

      expect(find.text(ChatText.messageActionReceipts), findsOneWidget);
      await tester.tap(find.text(ChatText.messageActionReceipts));
      await tester.pump();
      expect(triggeredAction, 'receipts');
    });
  });
}

void _noopAction(String _) {}

void _noopClose() {}

ChatMessageDisplayItem _message({
  required String type,
  required bool isSelf,
  String sentAtIso = '',
}) {
  return ChatMessageDisplayItem(
    id: 'msg_1',
    conversationId: 'conv_1',
    seq: 1,
    clientMsgId: 'client_1',
    senderId: isSelf ? 'user_self' : 'user_other',
    senderName: isSelf ? '我' : '对方',
    senderAvatar: '',
    senderPersonaId: isSelf ? 'user_self' : 'user_other',
    type: type,
    content: type == 'text' ? 'hello' : '',
    status: 'sent',
    timestampLabel: sentAtIso,
    sentAtIso: sentAtIso,
    isSelf: isSelf,
    isRead: true,
    mediaUrl: '',
    imageUrl: '',
    thumbnailUrl: '',
    audioDurationMs: 0,
    audioWaveform: const <double>[],
  );
}
