import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/platform/incoming_call_envelope.dart';

/// 通话中收到的第二路来电（call waiting）轻提示状态。
///
/// 它只承载「有新来电、可稍后回拨」的提示语义，不得篡夺活跃 CallSession
/// 状态机，也不触发全屏来电页导航；消费方（通话页）展示提示后清除。
/// 未接来电的回拨入口由会话内 `system_call_log` 承载。
class SecondIncomingCallNotifier extends Notifier<IncomingCallEnvelope?> {
  @override
  IncomingCallEnvelope? build() => null;

  void notify(IncomingCallEnvelope envelope) {
    state = envelope;
  }

  void consume() {
    state = null;
  }
}

final secondIncomingCallProvider =
    NotifierProvider<SecondIncomingCallNotifier, IncomingCallEnvelope?>(
      SecondIncomingCallNotifier.new,
    );
