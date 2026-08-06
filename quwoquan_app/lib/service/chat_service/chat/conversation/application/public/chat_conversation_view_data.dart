import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

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
