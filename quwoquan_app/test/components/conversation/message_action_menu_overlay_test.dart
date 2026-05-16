import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';
import 'package:quwoquan_app/components/conversation/message_action_menu_overlay.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

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

      expect(find.text(UITextConstants.messageActionCopy), findsOneWidget);
      expect(find.text(UITextConstants.messageActionRecall), findsOneWidget);

      await tester.tap(find.text(UITextConstants.messageActionCopy));
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

      expect(find.text(UITextConstants.messageActionCopy), findsNothing);
      expect(find.text(UITextConstants.messageActionRecall), findsNothing);
      expect(find.text(UITextConstants.messageActionDelete), findsOneWidget);
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
    senderSubAccountId: isSelf ? 'user_self' : 'user_other',
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
    tasks: const <ChatTaskCardEntry>[],
  );
}
