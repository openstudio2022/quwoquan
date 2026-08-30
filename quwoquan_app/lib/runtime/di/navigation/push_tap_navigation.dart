import 'package:quwoquan_app/runtime/platform/firebase_incoming_call_runtime.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';

/// 设备推送 tap 直达路由（chat-offline-push-delivery REQ-003）。
///
/// 消费平台防腐层交出的中性 tap intent，按目标语义锚点分发到既有路由；
/// 来电帧由来电协调器独立消费，不可承接目标静默忽略。
class PushTapNavigator {
  PushTapNavigator({required this.intentSource, required this.push});

  final PushTapIntentSource? intentSource;
  final void Function(String location) push;
  bool _started = false;

  Future<void> start() async {
    final source = intentSource;
    if (source == null || _started) {
      return;
    }
    _started = true;
    await source.start(handleTapIntent);
  }

  /// 单条 tap intent 的分发；公开给测试直接驱动。
  void handleTapIntent(PushTapIntent intent) {
    if (intent.callId.isNotEmpty) {
      return;
    }
    if (intent.targetType == 'conversation' && intent.targetId.isNotEmpty) {
      push(AppRoutePaths.chatDetail(id: intent.targetId));
    }
  }

  Future<void> dispose() async {
    await intentSource?.stop();
    _started = false;
  }
}
