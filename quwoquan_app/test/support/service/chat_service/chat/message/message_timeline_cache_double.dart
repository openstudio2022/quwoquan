import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_timeline_cache.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';

/// Suite-local-safe typed double: no database, platform directory or network.
final class EmptyChatMessageTimelineCache implements ChatMessageTimelineCache {
  const EmptyChatMessageTimelineCache();

  @override
  Future<List<ChatMessageViewData>> readMessages({
    required ChatMessageTimelineScope scope,
    required String conversationId,
    int beforeSeq = 0,
    int limit = 50,
  }) async => const <ChatMessageViewData>[];

  @override
  Future<void> writeMessages({
    required ChatMessageTimelineScope scope,
    required List<ChatMessageViewData> messages,
  }) async {}

  @override
  Future<void> removeCachedMessage({
    required ChatMessageTimelineScope scope,
    required String messageId,
  }) async {}
}
