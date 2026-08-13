import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_media_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';

/// 时间线内容的来源态（reliability REQ：缓存读取结果必须可区分并驱动展示）。
///
/// - [none]：尚无任何内容来源（首帧加载中或本地为空且远端失败）。
/// - [localHydrated]：内容来自本地副本水合，远端刷新仍在进行。
/// - [remoteSynced]：内容已与远端收敛。
/// - [offlineReadOnly]：内容来自本地副本且本次远端刷新失败，为离线只读。
///
/// 「本地待发」在消息级以 `status == sending/failed` 区分，不占用时间线级来源。
enum ChatTimelineContentSource { none, localHydrated, remoteSynced, offlineReadOnly }

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
    this.source = ChatTimelineContentSource.none,
    this.peerReadSeq = 0,
    this.error,
  });

  final List<ChatMessageViewData> messages;
  final bool isLoading;
  final bool isRefreshing;
  final bool isLoadingOlder;
  final bool hasMore;
  final ChatTimelineContentSource source;

  /// 对端已读水位（1v1 双勾）：由实时水位事件单调推进，0 为未观测。
  final int peerReadSeq;
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
    String? replyToMessageId,
  });

  Future<void> retrySendMessage(String clientMsgId);

  Future<void> recallMessage(String messageId);

  Future<void> syncFromSeq(int lastSeq);

  void addMessage(ChatMessageViewData message);

  void markRecalled(String messageId);

  /// 推进对端已读水位（`ConversationReadWatermarkAdvanced` 实时事件）。
  /// 读者为当前用户自身时由调用方过滤；水位只单调前进。
  void advancePeerReadSeq(int readSeq);

  void clearLocalTimeline();
}
