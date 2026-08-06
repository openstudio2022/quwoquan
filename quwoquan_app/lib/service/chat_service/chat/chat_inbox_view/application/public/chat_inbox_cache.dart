import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

/// Inbox application boundary for the shared conversation cache.
///
/// The conversation object owns the concrete cache. Inbox state only consumes
/// its own typed rows and never imports the concrete adapter or storage record.
abstract interface class ChatInboxCache {
  List<ChatInboxCacheEntry> readInbox();

  ChatInboxCacheEntry? readInboxEntry(String conversationId);

  void replaceInbox(Iterable<ChatInboxCacheEntry> items);

  void patchInbox(String conversationId, ChatInboxCachePatch patch);

  void removeInbox(String conversationId);

  void addInboxListener(void Function() listener);

  void removeInboxListener(void Function() listener);
}

final class ChatInboxCacheEntry {
  const ChatInboxCacheEntry({
    required this.id,
    required this.type,
    required this.title,
    required this.avatarUrl,
    required this.groupAvatarVersion,
    required this.lastMessagePreview,
    required this.lastMessageType,
    required this.lastMessageTime,
    required this.lastSeq,
    required this.unreadCount,
    required this.mentionUnreadCount,
    required this.muted,
    required this.pinned,
    required this.circleId,
  });

  final String id;
  final String type;
  final String title;
  final String avatarUrl;
  final int groupAvatarVersion;
  final String lastMessagePreview;
  final MessageType lastMessageType;
  final DateTime? lastMessageTime;
  final int lastSeq;
  final int unreadCount;
  final int mentionUnreadCount;
  final bool muted;
  final bool pinned;
  final String circleId;
}

final class ChatInboxCachePatch {
  const ChatInboxCachePatch({
    this.lastMessagePreview,
    this.lastMessageAt,
    this.unreadCount,
    this.mentionUnreadCount,
  });

  final String? lastMessagePreview;
  final DateTime? lastMessageAt;
  final int? unreadCount;
  final int? mentionUnreadCount;
}
