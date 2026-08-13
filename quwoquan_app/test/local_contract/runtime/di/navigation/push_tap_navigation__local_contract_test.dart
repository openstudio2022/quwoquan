/// 设备推送 tap 直达路由契约：conversation 语义锚点分发到 chatDetail、
/// 来电帧不进入通用分发、目标缺失静默忽略、平台能力不可用时一致降级。
///
/// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/chat-offline-push-delivery/spec.md#req-003
library;

import 'dart:async';

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/navigation/push_tap_navigation.dart';
import 'package:quwoquan_app/runtime/platform/firebase_incoming_call_runtime.dart';

final class _ScriptedPushMessagingClient implements FirebasePushMessagingClient {
  _ScriptedPushMessagingClient({this.initialMessage});

  final RemoteMessage? initialMessage;
  final StreamController<RemoteMessage> opened =
      StreamController<RemoteMessage>.broadcast(sync: true);

  @override
  Future<void> initialize() async {}

  @override
  Future<String?> readToken() async => null;

  @override
  Stream<String> get tokenRefreshes => const Stream.empty();

  @override
  Stream<RemoteMessage> get foregroundMessages => const Stream.empty();

  @override
  Stream<RemoteMessage> get openedMessages => opened.stream;

  @override
  Future<RemoteMessage?> readInitialMessage() async => initialMessage;

  @override
  Future<bool> readNotificationAuthorization() async => false;
}

RemoteMessage _message(Map<String, String> data) =>
    RemoteMessage(data: data);

void main() {
  test('conversation 锚点分发到 chatDetail 且冷启动初始消息同链处理', () async {
    final client = _ScriptedPushMessagingClient(
      initialMessage: _message({
        'targetType': 'conversation',
        'targetId': 'conv_push_1',
      }),
    );
    final pushed = <String>[];
    final navigator = PushTapNavigator(
      messagingClient: client,
      push: pushed.add,
    );
    addTearDown(navigator.dispose);

    await navigator.start();
    expect(pushed, ['/chat/conv_push_1']);

    client.opened.add(
      _message({'targetType': 'conversation', 'targetId': 'conv_push_2'}),
    );
    expect(pushed, ['/chat/conv_push_1', '/chat/conv_push_2']);
  });

  test('来电帧与未知目标不进入通用分发', () async {
    final client = _ScriptedPushMessagingClient();
    final pushed = <String>[];
    final navigator = PushTapNavigator(
      messagingClient: client,
      push: pushed.add,
    );
    addTearDown(navigator.dispose);
    await navigator.start();

    client.opened.add(
      _message({
        'callId': 'call-1',
        'targetType': 'conversation',
        'targetId': 'conv_push_1',
      }),
    );
    client.opened.add(_message({'targetType': 'homepage', 'targetId': 'h1'}));
    client.opened.add(_message({'targetType': 'conversation'}));

    expect(
      pushed,
      isEmpty,
      reason: '来电帧归来电协调器；不可承接目标必须静默忽略而非死路由',
    );
  });

  test('平台能力不可用时 start 为一致降级 no-op', () async {
    final pushed = <String>[];
    final navigator = PushTapNavigator(messagingClient: null, push: pushed.add);
    await navigator.start();
    await navigator.dispose();
    expect(pushed, isEmpty);
  });
}
