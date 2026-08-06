import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_media_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';

/// Read-only cross-object projection of one conversation's message timeline.
///
/// Riverpod state, repositories and transport details remain private to the
/// Message object. Consumers observe this immutable value through runtime DI.
final class ChatMessageTimelineSnapshot {
  const ChatMessageTimelineSnapshot({
    this.messages = const <ChatMessageViewData>[],
    this.isLoading = false,
    this.isRefreshing = false,
    this.isLoadingOlder = false,
    this.hasMore = true,
    this.error,
  });

  final List<ChatMessageViewData> messages;
  final bool isLoading;
  final bool isRefreshing;
  final bool isLoadingOlder;
  final bool hasMore;
  final String? error;
}

/// Explicit Message application capability consumed by Conversation and the
/// realtime composition. The concrete notifier stays inside Message.
abstract interface class ChatMessageTimelineController {
  Future<void> loadMessages({int? maxSeq});

  Future<int> loadOlderMessages();

  Future<bool> markConversationRead();

  Future<bool> sendMessage(
    String type,
    String content, {
    ChatMessageMediaViewData? media,
    String? senderName,
    String? senderAvatar,
    List<String>? mentions,
  });

  Future<void> retrySendMessage(String clientMsgId);

  Future<void> recallMessage(String messageId);

  Future<void> syncFromSeq(int lastSeq);

  void addMessage(ChatMessageViewData message);

  void markRecalled(String messageId);

  void clearLocalTimeline();
}
