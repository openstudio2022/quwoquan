/// Transport-level connection state.
enum TransportState {
  /// App is foreground but no active chat → long-polling for inbox updates.
  idle,

  /// User is viewing a chat detail → WebSocket for real-time messaging.
  active,

  /// App is in background → no connection (relies on FCM/APNs).
  disconnected,
}

typedef RealtimeConnectionStateListener = void Function();

/// Production Remote 与 alpha/test composition 共用的连接生命周期端口。
abstract interface class RealtimeConnectionDelegate {
  TransportState get state;

  void onAppForeground();

  void onAppBackground();

  void onEnterConversation(String conversationId);

  void onLeaveConversation();

  void dispose();
}
