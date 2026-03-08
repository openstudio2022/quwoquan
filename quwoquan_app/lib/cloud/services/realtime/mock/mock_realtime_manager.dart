import 'dart:async';

import 'package:flutter_riverpod/legacy.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_manager.dart';

/// Mock implementation of RealtimeConnectionManager for local development.
/// Simulates state transitions without real network connections.
class MockRealtimeConnectionManager extends StateNotifier<TransportState> {
  MockRealtimeConnectionManager() : super(TransportState.disconnected);

  Timer? _idleTimer;

  void onAppForeground() {
    if (state == TransportState.disconnected) {
      state = TransportState.idle;
    }
  }

  void onAppBackground() {
    _cancelIdleTimer();
    state = TransportState.disconnected;
  }

  void onEnterChatDetail(String conversationId) {
    _cancelIdleTimer();
    state = TransportState.active;
  }

  void onLeaveChatDetail() {
    _idleTimer = Timer(const Duration(seconds: 5), () {
      if (state == TransportState.active) {
        state = TransportState.idle;
      }
    });
  }

  void _cancelIdleTimer() {
    _idleTimer?.cancel();
    _idleTimer = null;
  }

  @override
  void dispose() {
    _cancelIdleTimer();
    super.dispose();
  }
}
