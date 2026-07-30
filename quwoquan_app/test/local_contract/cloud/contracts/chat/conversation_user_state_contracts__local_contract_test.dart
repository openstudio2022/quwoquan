import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('Chat ConversationUserState commands encode only writable fields', () {
    final markRead = encodeChatConversationUserStateMarkAsReadGeneratedRequest(
      ChatMarkConversationMessageReadCommand(
        conversationId: 'conversation-1',
        messageId: 'message-1',
      ),
    );
    final update =
        encodeChatConversationUserStateUpdateConversationSettingsGeneratedRequest(
          ChatUpdateConversationSettingsCommand(
            conversationId: 'conversation-1',
            muted: true,
          ),
        );

    expect(markRead.pathParameters, <String, String>{
      'conversationId': 'conversation-1',
      'messageId': 'message-1',
    });
    expect(markRead.body, isNull);
    expect(update.body, <String, Object?>{'muted': true});
    expect(
      ChatUpdateConversationSettingsCommand(
        conversationId: 'conversation-1',
      ).muted,
      isNull,
    );
  });
}
