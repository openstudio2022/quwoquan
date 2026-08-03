import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

/// App-owned inbox state.
///
/// The cloud wire owner is [ChatInboxItemView]. This type only adds local
/// cache/presentation semantics such as a nullable last-message timestamp and
/// immutable copy updates; it does not decode cloud JSON.
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

/// App-owned contact row state. Cloud decoding is owned by
/// [ChatContactListRow].
final class ChatContactRowViewData {
  const ChatContactRowViewData({
    this.userId = '',
    this.userHandle = '',
    this.displayName = '',
    this.avatarUrl = '',
    this.bio = '',
    this.metFrom = '',
    this.lastInteraction = '',
    this.relationState = 'not_following',
    this.source = '',
    this.isStarred = false,
  });

  factory ChatContactRowViewData.fromWire(ChatContactListRow source) {
    return ChatContactRowViewData(
      userId: source.userId,
      userHandle: source.userHandle,
      displayName: source.displayName,
      avatarUrl: source.avatarUrl,
      bio: source.bio,
      metFrom: source.metFrom,
      lastInteraction: source.lastInteraction,
      relationState: source.relationState,
      source: source.source,
      isStarred: source.isStarred,
    );
  }

  final String userId;
  final String userHandle;
  final String displayName;
  final String avatarUrl;
  final String bio;
  final String metFrom;
  final String lastInteraction;
  final String relationState;
  final String source;
  final bool isStarred;

  ChatContactRowViewData copyWith({
    String? userId,
    String? userHandle,
    String? displayName,
    String? avatarUrl,
    String? bio,
    String? metFrom,
    String? lastInteraction,
    String? relationState,
    String? source,
    bool? isStarred,
  }) {
    return ChatContactRowViewData(
      userId: userId ?? this.userId,
      userHandle: userHandle ?? this.userHandle,
      displayName: displayName ?? this.displayName,
      avatarUrl: avatarUrl ?? this.avatarUrl,
      bio: bio ?? this.bio,
      metFrom: metFrom ?? this.metFrom,
      lastInteraction: lastInteraction ?? this.lastInteraction,
      relationState: relationState ?? this.relationState,
      source: source ?? this.source,
      isStarred: isStarred ?? this.isStarred,
    );
  }
}

/// Result needed by App navigation after the canonical conversation command.
final class ChatConversationCreatedViewData {
  const ChatConversationCreatedViewData({this.conversationId = ''});

  factory ChatConversationCreatedViewData.fromWire(ChatConversation source) {
    return ChatConversationCreatedViewData(
      conversationId: source.conversationId,
    );
  }

  final String conversationId;
}

/// App edit state for the subset of group settings exposed on the current
/// screen. The authoritative cloud object remains [ChatConversation].
final class ChatGroupSettingsViewData {
  const ChatGroupSettingsViewData({
    this.nameEditableByAdminOnly = false,
    this.conversationType = 'group',
    this.circleId = '',
    this.circleGroupId = '',
  });

  factory ChatGroupSettingsViewData.fromWire(ChatConversation source) {
    return ChatGroupSettingsViewData(
      nameEditableByAdminOnly: source.nameEditableByAdminOnly,
      conversationType: source.type,
      circleId: source.circleId,
      circleGroupId: source.circleGroupId,
    );
  }

  final bool nameEditableByAdminOnly;
  final String conversationType;
  final String circleId;
  final String circleGroupId;

  ChatGroupSettingsViewData copyWith({
    bool? nameEditableByAdminOnly,
    String? conversationType,
    String? circleId,
    String? circleGroupId,
  }) {
    return ChatGroupSettingsViewData(
      nameEditableByAdminOnly:
          nameEditableByAdminOnly ?? this.nameEditableByAdminOnly,
      conversationType: conversationType ?? this.conversationType,
      circleId: circleId ?? this.circleId,
      circleGroupId: circleGroupId ?? this.circleGroupId,
    );
  }
}
