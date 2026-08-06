/// Realtime-facing seam for keeping a conversation membership projection fresh.
///
/// The realtime object reports authoritative membership events through this
/// port; it does not reach into the conversation object's Riverpod state.
abstract interface class RealtimeConversationMembershipProjection {
  Future<void> refresh(String conversationId);

  void evict(String conversationId);

  void refreshHome(String conversationId);
}
