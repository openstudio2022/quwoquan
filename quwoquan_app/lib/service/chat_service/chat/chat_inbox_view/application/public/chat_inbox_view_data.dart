import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

/// App-owned inbox state.
///
/// The cloud wire owner is [ChatInboxItemView]. This type only adds local
/// cache/presentation semantics; it does not decode cloud JSON.
final class ChatInboxViewData {
  const ChatInboxViewData({
    this.id = '',
    this.type = '',
    this.title = '',
    this.avatarUrl = '',
    this.groupAvatarVersion = 0,
    this.lastMessagePreview = '',
    required this.lastMessageType,
    this.lastMessageTime,
    this.lastSeq = 0,
    this.unreadCount = 0,
    this.mentionUnreadCount = 0,
    this.muted = false,
    this.pinned = false,
    this.circleId = '',
  });

  factory ChatInboxViewData.fromWire(ChatInboxItemView source) {
    return ChatInboxViewData(
      id: source.id,
      type: source.type,
      title: source.title,
      avatarUrl: source.avatarUrl,
      groupAvatarVersion: source.groupAvatarVersion,
      lastMessagePreview: source.lastMessagePreview,
      lastMessageType: source.lastMessageType,
      lastMessageTime: source.lastMessageTime,
      lastSeq: source.lastSeq,
      unreadCount: source.unreadCount,
      mentionUnreadCount: source.mentionUnreadCount,
      muted: source.muted,
      pinned: source.pinned,
      circleId: source.circleId ?? '',
    );
  }

  factory ChatInboxViewData.fromConversation(ChatConversation source) {
    return ChatInboxViewData(
      id: source.id,
      type: source.type,
      title: source.title,
      avatarUrl: source.avatarUrl,
      groupAvatarVersion: source.groupAvatarVersion,
      lastMessagePreview: source.lastMessagePreview,
      lastMessageType: source.lastMessageType,
      lastMessageTime: source.lastMessageTime,
      lastSeq: source.maxSeq,
      circleId: source.circleId,
    );
  }

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

  bool get hasMention => mentionUnreadCount > 0;

  bool get hasUnread => unreadCount > 0;

  ChatInboxViewData copyWith({
    String? id,
    String? type,
    String? title,
    String? avatarUrl,
    int? groupAvatarVersion,
    String? lastMessagePreview,
    MessageType? lastMessageType,
    DateTime? lastMessageTime,
    int? lastSeq,
    int? unreadCount,
    int? mentionUnreadCount,
    bool? muted,
    bool? pinned,
    String? circleId,
  }) {
    return ChatInboxViewData(
      id: id ?? this.id,
      type: type ?? this.type,
      title: title ?? this.title,
      avatarUrl: avatarUrl ?? this.avatarUrl,
      groupAvatarVersion: groupAvatarVersion ?? this.groupAvatarVersion,
      lastMessagePreview: lastMessagePreview ?? this.lastMessagePreview,
      lastMessageType: lastMessageType ?? this.lastMessageType,
      lastMessageTime: lastMessageTime ?? this.lastMessageTime,
      lastSeq: lastSeq ?? this.lastSeq,
      unreadCount: unreadCount ?? this.unreadCount,
      mentionUnreadCount: mentionUnreadCount ?? this.mentionUnreadCount,
      muted: muted ?? this.muted,
      pinned: pinned ?? this.pinned,
      circleId: circleId ?? this.circleId,
    );
  }
}
