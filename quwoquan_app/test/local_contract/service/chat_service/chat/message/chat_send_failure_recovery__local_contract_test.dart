// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/spec.md#sit-002
//
// 发送失败可恢复与撤回离线占位（迭代四 B 批次的可靠性真链）：
//   - 失败气泡的失败指示器是可点击重发行动点，触发按原 clientMsgId 重放；
//   - outbox 拒收过的命令手动重试时直发兜底，不再被 loadMessages 静默吞掉；
//   - 自动 drain 送达后回调对应会话（failed 气泡收敛的刷新入口）；
//   - 撤回把 recalled 占位写回本地副本而非物理删除（离线重开仍可见占位）。
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/runtime/di/chat_message_application_dependencies.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_message_bubble.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_message_display_item.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_send_outbox.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_timeline_cache.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/voice_message_interaction.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/runtime/observability/recording_app_telemetry_recorder.dart';
import '../../../../../support/runtime/platform/storage/sqflite_ffi_test_support.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';

const _conversationId = 'conv_retry_001';

ChatMessageDisplayItem _displayItem({required String status}) {
  return ChatMessageDisplayItem(
    id: 'retry_msg_1',
    conversationId: _conversationId,
    seq: 0,
    clientMsgId: 'retry_client_1',
    senderId: 'user_001',
    senderName: '',
    senderAvatar: '',
    senderPersonaId: 'user_001',
    type: 'text',
    content: '待重发消息',
    status: status,
    timestampLabel: '',
    sentAtIso: '2026-08-13T09:00:00.000Z',
    isSelf: true,
    isRead: false,
    mediaUrl: '',
    imageUrl: '',
    thumbnailUrl: '',
    audioDurationMs: 0,
    audioWaveform: const <double>[],
    mentions: const <String>[],
  );
}

Widget _wrapBubble(
  ChatMessageDisplayItem message, {
  VoidCallback? onRetrySend,
}) {
  return ProviderScope(
    child: MaterialApp(
      home: Scaffold(
        body: ChatMessageBubble(
          message: message,
          isRight: true,
          bubbleColor: Colors.white,
          textColor: Colors.black,
          isSelectionMode: false,
          isSelected: false,
          onLongPressStart: (_) {},
          onRetrySend: onRetrySend,
        ),
      ),
    ),
  );
}

void main() {
  setUpAll(ensureSqfliteFfiInitialized);

  group('失败气泡手动重发入口', () {
    testWidgets('failed 消息的失败指示器可点击并触发重发回调', (tester) async {
      var retried = 0;
      await tester.pumpWidget(
        _wrapBubble(
          _displayItem(status: 'failed'),
          onRetrySend: () => retried++,
        ),
      );
      await tester.pump();

      final retryFinder = find.byKey(
        const ValueKey<String>('chat_bubble_retry_send'),
      );
      expect(retryFinder, findsOneWidget);
      await tester.tap(retryFinder);
      expect(retried, 1);
    });

    testWidgets('已送达消息不渲染重发行动点', (tester) async {
      await tester.pumpWidget(
        _wrapBubble(_displayItem(status: 'sent'), onRetrySend: () {}),
      );
      await tester.pump();
      expect(
        find.byKey(const ValueKey<String>('chat_bubble_retry_send')),
        findsNothing,
      );
    });
  });

  group('retrySendMessage 兜底与撤回占位', () {
    late ProviderContainer container;
    late _RecordingWriter writer;
    late _RecordingTimelineCache cache;

    setUp(() {
      Hive.init(
        '${Directory.systemTemp.path}/qwq_retry_provider_${DateTime.now().microsecondsSinceEpoch}',
      );
      writer = _RecordingWriter();
      cache = _RecordingTimelineCache();
      const personaContext = ActivePersonaContextViewData(
        personaId: 'user_001',
        ownerUserId: 'user_001',
        subjectType: 'person',
        displayName: '测试用户',
        avatarUrl: '',
        isPrimary: true,
      );
      container = ProviderContainer(
        overrides: [
          ...sealedCloudBoundaryOverrides(),
          ...chatTestRepositoryOverrides(),
          activePersonaContextProvider.overrideWith(
            (ref) async => personaContext,
          ),
          activePersonaContextLoaderProvider.overrideWithValue(
            () async => personaContext,
          ),
          chatMessageCommandWriterProvider.overrideWithValue(writer),
          chatMessageTimelineCacheProvider.overrideWithValue(cache),
          contentConfigRepositoryProvider.overrideWithValue(
            InMemoryContentConfigRepository(),
          ),
          exceptionTelemetryPortProvider.overrideWithValue(_SilentTelemetry()),
          appTelemetryReporterProvider.overrideWithValue(
            RecordingAppTelemetryRecorder(),
          ),
        ],
      );
    });

    tearDown(() async {
      container.dispose();
      await Hive.deleteFromDisk();
    });

    test('outbox 拒收时手动重试直发兜底并确认消息', () async {
      // 用公开的终态 purge 路径确定性触发队列拒收（enqueueCommand 返回
      // false），验证重试不依赖队列、以原 clientMsgId 直发兜底。
      await container
          .read(chatSendOutboxProvider.notifier)
          .purgeForTerminalAccountClosure();
      final controller = container.read(
        chatMessageTimelineControllerProvider(_conversationId),
      );
      writer.failNext = true;
      await controller.sendMessage('text', '待重发消息');
      var snapshot = container.read(
        chatMessageTimelineProvider(_conversationId),
      );
      final failed = snapshot.messages
          .where((m) => m.status == 'failed')
          .toList(growable: false);
      expect(failed, hasLength(1), reason: '首次发送失败必须标记 failed');

      await controller.retrySendMessage(failed.single.clientMsgId);

      expect(
        writer.sentClientMsgIds,
        contains(failed.single.clientMsgId),
        reason: '队列拒收时重试必须以原 clientMsgId 直发',
      );
      snapshot = container.read(chatMessageTimelineProvider(_conversationId));
      expect(
        snapshot.messages.where((m) => m.status == 'failed'),
        isEmpty,
        reason: '直发成功后 failed 气泡必须收敛',
      );
    });

    test('撤回实时事件把 recalled 占位写回本地副本而非删除', () async {
      final controller = container.read(
        chatMessageTimelineControllerProvider(_conversationId),
      );
      controller.addMessage(
        ChatMessageViewData(
          id: 'recall_target_1',
          conversationId: _conversationId,
          seq: 7,
          clientMsgId: 'recall_client_1',
          senderId: 'peer_user',
          type: 'text',
          content: '将被撤回的消息',
          status: 'sent',
          timestamp: DateTime.utc(2026, 8, 13, 9),
        ),
      );
      // addMessage 的本地落盘是异步 best-effort：先让它完成再清空记录，
      // 保证下面的断言只观察撤回占位写入。
      await Future<void>.delayed(Duration.zero);
      await Future<void>.delayed(Duration.zero);
      cache.writes.clear();

      controller.markRecalled('recall_target_1');
      await Future<void>.delayed(Duration.zero);
      await Future<void>.delayed(Duration.zero);

      expect(cache.removals, isEmpty, reason: '撤回不得物理删除本地副本');
      final placeholder = cache.writes
          .where((m) => m.id == 'recall_target_1')
          .toList(growable: false);
      expect(placeholder, hasLength(1));
      expect(placeholder.single.status, 'recalled');
      expect(placeholder.single.recalledAt, isNotNull);
    });
  });

  group('outbox 自动 drain 送达回调', () {
    setUp(() {
      Hive.init(
        '${Directory.systemTemp.path}/qwq_retry_outbox_${DateTime.now().microsecondsSinceEpoch}',
      );
    });

    tearDown(() async {
      await Hive.deleteFromDisk();
    });

    test('command 送达后按会话回调（failed 气泡刷新入口）', () async {
      final deliveredConversations = <String>[];
      final outbox = ChatSendOutbox(
        telemetry: _SilentTelemetry(),
        maxQueueSize: 10,
        sendCommand: (_) async {},
        sendQueuedVoice: (_, _) async => VoiceSendStatus.completed,
        onCommandDelivered: deliveredConversations.add,
      );
      addTearDown(outbox.dispose);
      await outbox.init();
      await outbox.enqueueCommand(
        ChatSendMessageCommand(
          conversationId: _conversationId,
          type: 'text',
          content: '离线补发',
          clientMsgId: 'drain_client_1',
          senderDisplayNameSnapshot: '契约用户',
        ),
      );

      await outbox.drainQueue();

      expect(deliveredConversations, <String>[_conversationId]);
    });
  });
}

class _RecordingWriter implements ChatMessageCommandWriter {
  final List<String> sentClientMsgIds = <String>[];
  bool failNext = false;

  @override
  Future<ChatSendMessageResult> sendMessage(
    ChatSendMessageCommand command,
  ) async {
    if (failNext) {
      failNext = false;
      throw Exception('CHAT.MIDDLEWARE.unavailable');
    }
    sentClientMsgIds.add(command.clientMsgId);
    return ChatSendMessageResult(
      messageId: 'server_${command.clientMsgId}',
      seq: 99,
      timestamp: DateTime.utc(2026, 8, 13, 9, 30),
    );
  }
}

class _RecordingTimelineCache implements ChatMessageTimelineCache {
  final List<ChatMessageViewData> writes = <ChatMessageViewData>[];
  final List<String> removals = <String>[];

  @override
  Future<List<ChatMessageViewData>> readMessages({
    required ChatMessageTimelineScope scope,
    required String conversationId,
    int beforeSeq = 0,
    int limit = 50,
  }) async => const <ChatMessageViewData>[];

  @override
  Future<void> writeMessages({
    required ChatMessageTimelineScope scope,
    required List<ChatMessageViewData> messages,
  }) async {
    writes.addAll(messages);
  }

  @override
  Future<void> removeCachedMessage({
    required ChatMessageTimelineScope scope,
    required String messageId,
  }) async {
    removals.add(messageId);
  }
}

class _SilentTelemetry implements ExceptionTelemetryPort {
  @override
  Future<void> recordGlobalException({
    required String source,
    required String exceptionText,
    required String stackText,
    String pageId = '',
    String pageName = '',
    String surfaceId = '',
    String routeId = '',
    String operationId = '',
    RuntimeFailureBase? runtimeFailure,
    String exceptionType = '',
  }) async {}

  @override
  Future<void> recordHandledException({
    required String source,
    required Object error,
    required StackTrace stackTrace,
    String pageId = '',
    String pageName = '',
    String surfaceId = '',
    String routeId = '',
    String operationId = '',
  }) async {}

  @override
  Future<void> flushPending() async {}
}
