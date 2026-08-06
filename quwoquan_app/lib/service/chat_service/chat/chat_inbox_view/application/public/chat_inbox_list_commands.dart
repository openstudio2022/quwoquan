/// ChatInboxView 对外暴露的会话列表命令面。
///
/// 跨对象只通过该能力刷新/标记已读，不直连 inbox Notifier 或列表状态。
abstract interface class ChatInboxListCommands {
  Future<void> refresh();

  void markConversationRead(String conversationId);
}
