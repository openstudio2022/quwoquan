/// Narrow lifecycle seam consumed by conversation presentation.
///
/// Transport ownership and concrete realtime composition remain inside the
/// realtime object and `runtime/di`; a page only announces its active
/// conversation boundary.
abstract interface class RealtimeConversationLifecycle {
  void onEnterConversation(String conversationId);

  void onLeaveConversation();
}
