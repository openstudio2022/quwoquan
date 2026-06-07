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

/// Mock/Remote 共用的 realtime 连接生命周期接口。
abstract interface class RealtimeConnectionDelegate {
  TransportState get state;

  void onAppForeground();

  void onAppBackground();

  void onEnterChatDetail(String conversationId);

  void onLeaveChatDetail();

  void dispose();
}
