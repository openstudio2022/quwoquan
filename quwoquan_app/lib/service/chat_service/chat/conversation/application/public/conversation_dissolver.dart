/// Chat Conversation 对象的窄解散命令端口。
///
/// presentation 只依赖该公开 seam；production adapter 由 `runtime/di`
/// composition root 注入，避免页面反向读取 concrete repository Provider。
abstract interface class ConversationDissolver {
  Future<void> dissolveConversation(String conversationId);
}
