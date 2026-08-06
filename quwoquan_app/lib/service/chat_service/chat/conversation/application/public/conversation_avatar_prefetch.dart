/// Conversation 对外提供的会话头像成员预取能力。
///
/// 只暴露 inbox 预取所需的最小投影，不泄漏成员列表状态机或 Riverpod Provider。
const int kConversationAvatarInitialPrefetchLimit = 12;
const int kConversationAvatarBackgroundPrefetchLimit = 24;

final class ConversationAvatarPrefetchItem {
  const ConversationAvatarPrefetchItem({
    required this.conversationId,
    required this.conversationType,
    required this.avatarUrl,
    required this.groupAvatarVersion,
  });

  final String conversationId;
  final String conversationType;
  final String avatarUrl;
  final int groupAvatarVersion;
}

abstract interface class ConversationAvatarPrefetchCapability {
  Future<void> prefetchInbox(
    List<ConversationAvatarPrefetchItem> items, {
    int offset = 0,
    int limit = kConversationAvatarInitialPrefetchLimit,
  });
}
