import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_message_provider.dart';

/// Routes incoming realtime events to the appropriate domain handlers.
/// Called by [RealtimeConnectionManager] when a WebSocket or long-poll
/// event arrives.
class RealtimeMessageHandler {
  RealtimeMessageHandler(this._ref);

  final Ref _ref;

  void handle(Map<String, dynamic> event) {
    final eventType = event['type'] as String? ?? '';
    final conversationId = event['conversationId'] as String? ?? '';
    final payload = event['payload'] as Map<String, dynamic>? ?? event;

    switch (eventType) {
      case 'MessageSent':
        if (conversationId.isEmpty) return;
        final msg = MessageDto.fromMap({
          ...payload,
          'conversationId': conversationId,
        });
        _ref.read(chatMessageProvider(conversationId).notifier).addMessage(msg);

      case 'MessageRecalled':
        if (conversationId.isEmpty) return;
        final messageId = payload['messageId'] as String? ?? '';
        if (messageId.isNotEmpty) {
          _ref.read(chatMessageProvider(conversationId).notifier)
              .markRecalled(messageId);
        }

      case 'ReadReceiptSent':
        // TODO: Update read receipt status on message bubbles
        break;

      case 'MemberJoined':
      case 'MemberLeft':
        // TODO: Insert system message for membership change
        break;

      case 'ConversationSettingsUpdated':
        // TODO: Refresh conversation title / settings
        break;

      default:
        break;
    }
  }
}
