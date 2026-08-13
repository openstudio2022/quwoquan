import 'dart:async';

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:quwoquan_app/runtime/platform/firebase_incoming_call_runtime.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';

/// 设备推送 tap 直达路由（chat-offline-push-delivery REQ-003）。
///
/// 消费平台防腐层的推送打开流（冷启动初始消息 + 后台点开消息），按投递
/// payload 的语义锚点（`targetType`/`targetId`，与 notification 投递记录
/// 同源）分发到既有路由；不解析来电信令（`callId`/`action` 帧由来电协调
/// 器独立消费），目标缺失或不可承接时静默忽略，不进入死路由。
class PushTapNavigator {
  PushTapNavigator({required this.messagingClient, required this.push});

  final FirebasePushMessagingClient? messagingClient;
  final void Function(String location) push;
  StreamSubscription<RemoteMessage>? _openedSub;
  bool _started = false;

  Future<void> start() async {
    final client = messagingClient;
    if (client == null || _started) {
      // 平台能力不可用（非 Android）或已启动：一致降级，无副作用。
      return;
    }
    _started = true;
    _openedSub = client.openedMessages.listen(handleTapMessage);
    final initial = await client.readInitialMessage();
    if (initial != null) {
      handleTapMessage(initial);
    }
  }

  /// 单条 tap 消息的分发；公开给测试直接驱动。
  void handleTapMessage(RemoteMessage message) {
    final data = message.data;
    if ((data['callId'] ?? '').toString().trim().isNotEmpty) {
      // 来电帧归来电协调器，不在通用 tap 路由分发。
      return;
    }
    final targetType = (data['targetType'] ?? '').toString().trim();
    final targetId = (data['targetId'] ?? '').toString().trim();
    if (targetType == 'conversation' && targetId.isNotEmpty) {
      push(AppRoutePaths.chatDetail(id: targetId));
    }
  }

  Future<void> dispose() async {
    await _openedSub?.cancel();
    _openedSub = null;
    _started = false;
  }
}
