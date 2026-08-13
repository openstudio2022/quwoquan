/// 断连恢复事件 → seq 补洞的可靠性契约。
/// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/realtime-push-and-offline-sync/spec.md#gwt-002.t1
///
/// 覆盖：WS 断连重连成功后 delegate 发出携带活跃会话的 `Reconnected` 恢复
/// 事件；handler 以端侧已持有的最大 seq 为起点触发补洞（本地为空则整段
/// 重拉）；补齐结果与实时推送经同一去重链路合并、无重复无乱序。
///
/// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/realtime-push-and-offline-sync/spec.md#gwt-002
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/chat_message_application_dependencies.dart';
import 'package:quwoquan_app/runtime/observability/app_observability_ports.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart' show RuntimeFailureBase;
import 'package:quwoquan_app/service/chat_service/chat/conversation/adapters/conversation_sync_service.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_media_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_timeline.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/adapters/longpoll_transport.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/adapters/realtime_config.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/adapters/remote_realtime_connection_delegate.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/adapters/websocket_transport.dart';
import 'package:quwoquan_app/runtime/di/local_chat_search_sync_service.dart';
import 'package:riverpod/misc.dart' show ProviderListenable;

const _conversationId = 'conv_gap_recovery';

ChatMessageViewData _message(int seq) => ChatMessageViewData(
  id: 'msg_$seq',
  conversationId: _conversationId,
  seq: seq,
  clientMsgId: 'client_$seq',
  senderId: 'peer',
  type: 'text',
  content: '第 $seq 条',
  status: 'sent',
);

final class _FakeConversationSync extends Fake
    implements ConversationSyncService {
  int syncCalls = 0;
  int avatarPatchCalls = 0;

  @override
  Future<bool> sync({bool force = false}) async {
    syncCalls += 1;
    return true;
  }

  @override
  Future<bool> syncAvatarPatches({
    int? hintedLatestSyncSeq,
    bool force = false,
  }) async {
    avatarPatchCalls += 1;
    return true;
  }
}

final class _FakeLocalChatSearchSync extends Fake
    implements LocalChatSearchSyncService {
  int syncCalls = 0;

  @override
  Future<bool> sync({bool force = false}) async {
    syncCalls += 1;
    return true;
  }
}

final class _RecordingTimelineController extends Fake
    implements ChatMessageTimelineController {
  final List<int> syncFromSeqCalls = <int>[];
  int loadMessagesCalls = 0;

  @override
  Future<void> syncFromSeq(int lastSeq) async {
    syncFromSeqCalls.add(lastSeq);
  }

  @override
  Future<void> loadMessages({int? maxSeq}) async {
    loadMessagesCalls += 1;
  }

  @override
  Future<bool> sendMessage(
    String type,
    String content, {
    ChatMessageMediaViewData? media,
    String? senderName,
    String? senderAvatar,
    List<String>? mentions,
    String? replyToMessageId,
  }) async => true;
}

final class _FakeExceptionTelemetry extends Fake
    implements ExceptionTelemetryPort {
  @override
  Future<void> recordGlobalException({
    required String source,
    required String exceptionText,
    required String stackText,
    String pageId = 'global.app.runtime',
    String pageName = '',
    String surfaceId = 'global.app.runtime',
    String routeId = 'global.app.runtime',
    String operationId = 'app.runtime.capture_exception',
    RuntimeFailureBase? runtimeFailure,
    String exceptionType = '',
  }) async {}
}

/// 记录型 read：只解析恢复链路真实消费的 provider，其余一律拒绝。
final class _ReconnectReadScope {
  _ReconnectReadScope({
    required this.snapshot,
    required this.controller,
  });

  final ChatMessageTimelineSnapshot snapshot;
  final _RecordingTimelineController controller;
  final _FakeConversationSync conversationSync = _FakeConversationSync();
  final _FakeLocalChatSearchSync searchSync = _FakeLocalChatSearchSync();
  final _FakeExceptionTelemetry telemetry = _FakeExceptionTelemetry();

  T read<T>(ProviderListenable<T> listenable) {
    if (identical(listenable, conversationSyncProvider)) {
      return conversationSync as T;
    }
    if (identical(listenable, localChatSearchSyncProvider)) {
      return searchSync as T;
    }
    if (listenable == chatMessageTimelineProvider(_conversationId)) {
      return snapshot as T;
    }
    if (listenable == chatMessageTimelineControllerProvider(_conversationId)) {
      return controller as T;
    }
    if (identical(listenable, exceptionTelemetryPortProvider)) {
      return telemetry as T;
    }
    throw StateError('unexpected provider read in reconnect recovery test');
  }
}

/// 可控连接结果的 WS double：connect 即成功，可由测试触发断连。
final class _ConnectableWebSocketTransport extends WebSocketTransport {
  _ConnectableWebSocketTransport({
    required super.config,
    required super.authTokenProvider,
    required super.onEvent,
    required super.onDisconnect,
  });

  final ValueNotifier<bool> _fakeConnected = ValueNotifier<bool>(false);

  @override
  ValueListenable<bool> get isConnected => _fakeConnected;

  @override
  Future<void> connect({List<String> topics = const []}) async {
    _fakeConnected.value = true;
  }

  void simulateDisconnect() {
    _fakeConnected.value = false;
    onDisconnect();
  }

  @override
  Future<void> disconnect() async {
    _fakeConnected.value = false;
  }

  @override
  void dispose() {
    _fakeConnected.dispose();
  }
}

class _TokenProvider implements CloudAuthTokenProvider {
  const _TokenProvider();

  @override
  Future<String?> getAccessToken() async => 'jwt-token';
}

/// 不发起真实网络的 LongPoll double（降级路径只验证恢复事件语义）。
final class _InertLongPollTransport extends LongPollTransport {
  _InertLongPollTransport({
    required super.config,
    required super.authTokenProvider,
    required super.onEvents,
  });

  @override
  void start() {}

  @override
  void dispose() {}
}

Future<void> _drainRecoveryTimers() async {
  // handler 的恢复动作经 200ms 去抖 timer + 120ms avatar timer。
  await Future<void>.delayed(const Duration(milliseconds: 400));
}

void main() {
  test('WS 断连重连成功后发出恢复事件并按本地最大 seq 补洞', () async {
    final scope = _ReconnectReadScope(
      snapshot: ChatMessageTimelineSnapshot(
        messages: [_message(1), _message(2), _message(3)],
      ),
      controller: _RecordingTimelineController(),
    );
    _ConnectableWebSocketTransport? ws;
    final delegate = RemoteRealtimeConnectionDelegate(
      read: scope.read,
      currentUserIdResolver: () => 'user-42',
      authTokenProvider: const _TokenProvider(),
      config: const RealtimeConfig(
        wsUrl: 'ws://127.0.0.1:18080/realtime/ws',
        gatewayBaseUrl: 'http://127.0.0.1:17000',
        longPollHoldSec: 1,
      ),
      reconnectDelayResolver: ({required attempt, required config}) =>
          Duration.zero,
      webSocketFactory:
          ({
            required config,
            required authTokenProvider,
            required onEvent,
            required onDisconnect,
          }) {
            return ws = _ConnectableWebSocketTransport(
              config: config,
              authTokenProvider: authTokenProvider,
              onEvent: onEvent,
              onDisconnect: onDisconnect,
            );
          },
    );
    addTearDown(delegate.dispose);

    delegate.onEnterConversation(_conversationId);
    await Future<void>.delayed(Duration.zero);
    await _drainRecoveryTimers();
    expect(
      scope.controller.syncFromSeqCalls,
      isEmpty,
      reason: '首次成功连接不是恢复，不得触发补洞',
    );

    ws!.simulateDisconnect();
    for (var i = 0; i < 4; i += 1) {
      await Future<void>.delayed(Duration.zero);
    }
    await _drainRecoveryTimers();

    expect(
      scope.controller.syncFromSeqCalls,
      [3],
      reason: '恢复事件必须以端侧已持有的最大 seq 为起点补齐缺口',
    );
    expect(scope.conversationSync.syncCalls, greaterThan(0));
    expect(scope.searchSync.syncCalls, greaterThan(0));
  });

  test('恢复事件下本地无消息时整段重拉而非空起点补洞', () async {
    final scope = _ReconnectReadScope(
      snapshot: const ChatMessageTimelineSnapshot(),
      controller: _RecordingTimelineController(),
    );
    _ConnectableWebSocketTransport? ws;
    final delegate = RemoteRealtimeConnectionDelegate(
      read: scope.read,
      currentUserIdResolver: () => 'user-42',
      authTokenProvider: const _TokenProvider(),
      config: const RealtimeConfig(
        wsUrl: 'ws://127.0.0.1:18080/realtime/ws',
        gatewayBaseUrl: 'http://127.0.0.1:17000',
        longPollHoldSec: 1,
      ),
      reconnectDelayResolver: ({required attempt, required config}) =>
          Duration.zero,
      webSocketFactory:
          ({
            required config,
            required authTokenProvider,
            required onEvent,
            required onDisconnect,
          }) {
            return ws = _ConnectableWebSocketTransport(
              config: config,
              authTokenProvider: authTokenProvider,
              onEvent: onEvent,
              onDisconnect: onDisconnect,
            );
          },
    );
    addTearDown(delegate.dispose);

    delegate.onEnterConversation(_conversationId);
    await Future<void>.delayed(Duration.zero);
    ws!.simulateDisconnect();
    for (var i = 0; i < 4; i += 1) {
      await Future<void>.delayed(Duration.zero);
    }
    await _drainRecoveryTimers();

    expect(scope.controller.syncFromSeqCalls, isEmpty);
    expect(
      scope.controller.loadMessagesCalls,
      1,
      reason: '本地为空的恢复必须整段重拉，不得以 seq=0 伪造补洞',
    );
  });

  test('后台切换到前台重建传输后触发与断连重连同等的补洞', () async {
    final scope = _ReconnectReadScope(
      snapshot: ChatMessageTimelineSnapshot(
        messages: [_message(1), _message(2), _message(3)],
      ),
      controller: _RecordingTimelineController(),
    );
    final delegate = RemoteRealtimeConnectionDelegate(
      read: scope.read,
      currentUserIdResolver: () => 'user-42',
      authTokenProvider: const _TokenProvider(),
      config: const RealtimeConfig(
        wsUrl: 'ws://127.0.0.1:18080/realtime/ws',
        gatewayBaseUrl: 'http://127.0.0.1:17000',
        longPollHoldSec: 1,
      ),
      reconnectDelayResolver: ({required attempt, required config}) =>
          Duration.zero,
      webSocketFactory:
          ({
            required config,
            required authTokenProvider,
            required onEvent,
            required onDisconnect,
          }) => _ConnectableWebSocketTransport(
            config: config,
            authTokenProvider: authTokenProvider,
            onEvent: onEvent,
            onDisconnect: onDisconnect,
          ),
    );
    addTearDown(delegate.dispose);

    delegate.onEnterConversation(_conversationId);
    await Future<void>.delayed(Duration.zero);
    await _drainRecoveryTimers();
    expect(scope.controller.syncFromSeqCalls, isEmpty);

    // 后台断开是断连窗口；回到前台重建 WS 后必须补洞。
    delegate.onAppBackground();
    delegate.onAppForeground();
    for (var i = 0; i < 4; i += 1) {
      await Future<void>.delayed(Duration.zero);
    }
    await _drainRecoveryTimers();

    expect(
      scope.controller.syncFromSeqCalls,
      [3],
      reason: '后台窗口的消息必须以本地最大 seq 为起点补齐',
    );
  });

  test('WS 重试预算耗尽降级 LongPoll 时同样触发恢复补洞', () async {
    final scope = _ReconnectReadScope(
      snapshot: ChatMessageTimelineSnapshot(
        messages: [_message(1), _message(2), _message(3)],
      ),
      controller: _RecordingTimelineController(),
    );
    _ConnectableWebSocketTransport? ws;
    final delegate = RemoteRealtimeConnectionDelegate(
      read: scope.read,
      currentUserIdResolver: () => 'user-42',
      authTokenProvider: const _TokenProvider(),
      config: const RealtimeConfig(
        wsUrl: 'ws://127.0.0.1:18080/realtime/ws',
        gatewayBaseUrl: 'http://127.0.0.1:17000',
        longPollHoldSec: 1,
        maxReconnectAttempts: 0,
      ),
      reconnectDelayResolver: ({required attempt, required config}) =>
          Duration.zero,
      webSocketFactory:
          ({
            required config,
            required authTokenProvider,
            required onEvent,
            required onDisconnect,
          }) {
            return ws = _ConnectableWebSocketTransport(
              config: config,
              authTokenProvider: authTokenProvider,
              onEvent: onEvent,
              onDisconnect: onDisconnect,
            );
          },
      longPollFactory:
          ({required config, required authTokenProvider, required onEvents}) =>
              _InertLongPollTransport(
                config: config,
                authTokenProvider: authTokenProvider,
                onEvents: onEvents,
              ),
    );
    addTearDown(delegate.dispose);

    delegate.onEnterConversation(_conversationId);
    await Future<void>.delayed(Duration.zero);
    await _drainRecoveryTimers();
    expect(scope.controller.syncFromSeqCalls, isEmpty);

    // 重试预算为 0：断连立即降级 LongPoll，降级本身必须承担补洞。
    ws!.simulateDisconnect();
    for (var i = 0; i < 4; i += 1) {
      await Future<void>.delayed(Duration.zero);
    }
    await _drainRecoveryTimers();

    expect(
      scope.controller.syncFromSeqCalls,
      [3],
      reason: '降级 LongPoll 不承载断连窗口回放，必须由 seq 补洞收敛',
    );
  });
}
