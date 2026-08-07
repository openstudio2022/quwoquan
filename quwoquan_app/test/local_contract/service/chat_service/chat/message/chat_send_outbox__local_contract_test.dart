// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/runtime/observability/app_observability_ports.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_send_outbox.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/voice_message_interaction.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/voice_recording.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    Hive.init(
      '${Directory.systemTemp.path}/qwq_chat_send_outbox_test_${DateTime.now().microsecondsSinceEpoch}',
    );
  });

  tearDown(() async {
    await Hive.deleteFromDisk();
  });

  ChatSendMessageCommand textCommand(String clientMsgId) {
    return ChatSendMessageCommand(
      conversationId: 'conv_001',
      type: 'text',
      content: 'offline probe',
      clientMsgId: clientMsgId,
      senderDisplayNameSnapshot: '契约用户',
    );
  }

  VoiceRecordResult recordResult() {
    return VoiceRecordResult(
      filePath: '/tmp/voice.m4a',
      durationMs: 1200,
      fileSize: 1024,
      waveform: <double>[0.1, 0.4],
    );
  }

  test('文本命令 drain 成功后出队且按原 clientMsgId 重放', () async {
    final sentClientMsgIds = <String>[];
    final outbox = ChatSendOutbox(
      telemetry: _SilentExceptionTelemetryPort(),
      maxQueueSize: 10,
      sendCommand: (command) async {
        sentClientMsgIds.add(command.clientMsgId);
      },
      sendQueuedVoice: (_, _) async => VoiceSendStatus.completed,
    );
    addTearDown(outbox.dispose);
    await outbox.init();

    expect(await outbox.enqueueCommand(textCommand('client-msg-1')), isTrue);
    expect(outbox.queueLength, 1);

    await outbox.drainQueue();

    expect(outbox.queueLength, 0);
    expect(sentClientMsgIds, <String>['client-msg-1']);
  });

  test('队列项跨实例持久化：重启后仍可 drain（杀进程语义）', () async {
    final first = ChatSendOutbox(
      telemetry: _SilentExceptionTelemetryPort(),
      maxQueueSize: 10,
      sendCommand: (_) async => throw StateError('offline'),
      sendQueuedVoice: (_, _) async => VoiceSendStatus.failed,
    );
    await first.init();
    await first.enqueueCommand(textCommand('client-msg-restart'));
    expect(first.queueLength, 1);
    // 模拟进程退出：不 drain 直接关闭。
    await first.dispose();

    final sentClientMsgIds = <String>[];
    final second = ChatSendOutbox(
      telemetry: _SilentExceptionTelemetryPort(),
      maxQueueSize: 10,
      sendCommand: (command) async {
        sentClientMsgIds.add(command.clientMsgId);
      },
      sendQueuedVoice: (_, _) async => VoiceSendStatus.completed,
    );
    addTearDown(second.dispose);
    await second.init();
    expect(second.queueLength, 1);

    await second.drainQueue();

    expect(second.queueLength, 0);
    expect(sentClientMsgIds, <String>['client-msg-restart']);
  });

  test('发送失败保留队列项等待下次连通恢复', () async {
    final outbox = ChatSendOutbox(
      telemetry: _SilentExceptionTelemetryPort(),
      maxQueueSize: 10,
      sendCommand: (_) async => throw StateError('still offline'),
      sendQueuedVoice: (_, _) async => VoiceSendStatus.failed,
    );
    addTearDown(outbox.dispose);
    await outbox.init();
    await outbox.enqueueCommand(textCommand('client-msg-keep'));

    await outbox.drainQueue();

    expect(outbox.queueLength, 1);
  });

  test('语音项 drain 成功后出队，失败保留', () async {
    var voiceStatus = VoiceSendStatus.failed;
    final outbox = ChatSendOutbox(
      telemetry: _SilentExceptionTelemetryPort(),
      maxQueueSize: 10,
      sendCommand: (_) async {},
      sendQueuedVoice: (_, _) async => voiceStatus,
    );
    addTearDown(outbox.dispose);
    await outbox.init();
    await outbox.enqueueVoice(
      conversationId: 'conv_001',
      result: recordResult(),
    );

    await outbox.drainQueue();
    expect(outbox.queueLength, 1);

    voiceStatus = VoiceSendStatus.completed;
    await outbox.drainQueue();
    expect(outbox.queueLength, 0);
  });

  test('文本与语音统一队列保持入队顺序', () async {
    final delivered = <String>[];
    final outbox = ChatSendOutbox(
      telemetry: _SilentExceptionTelemetryPort(),
      maxQueueSize: 10,
      sendCommand: (command) async {
        delivered.add('command:${command.clientMsgId}');
      },
      sendQueuedVoice: (conversationId, _) async {
        delivered.add('voice:$conversationId');
        return VoiceSendStatus.completed;
      },
    );
    addTearDown(outbox.dispose);
    await outbox.init();
    await outbox.enqueueCommand(textCommand('client-msg-a'));
    await outbox.enqueueVoice(
      conversationId: 'conv_001',
      result: recordResult(),
    );
    await outbox.enqueueCommand(textCommand('client-msg-b'));

    await outbox.drainQueue();

    expect(delivered, <String>[
      'command:client-msg-a',
      'voice:conv_001',
      'command:client-msg-b',
    ]);
  });

  test('分享卡片消息不入队（发起面即时反馈）', () async {
    final outbox = ChatSendOutbox(
      telemetry: _SilentExceptionTelemetryPort(),
      maxQueueSize: 10,
      sendCommand: (_) async {},
      sendQueuedVoice: (_, _) async => VoiceSendStatus.completed,
    );
    addTearDown(outbox.dispose);
    await outbox.init();

    final cardCommand = ChatSendMessageCommand(
      conversationId: 'conv_001',
      type: 'card',
      content: '',
      clientMsgId: 'client-msg-card',
      card: MessageCard(
        kind: MessageCardKind.profileQr,
        title: '分享卡片',
        attributes: const <MessageCardAttribute>[],
      ),
    );
    expect(await outbox.enqueueCommand(cardCommand), isFalse);
    expect(outbox.queueLength, 0);
  });

  test('账号 closed 终态物理清空待发队列并永久停止旧实例重放', () async {
    final delivered = <String>[];
    final deletedTemporaryFiles = <String>[];
    final outbox = ChatSendOutbox(
      telemetry: _SilentExceptionTelemetryPort(),
      maxQueueSize: 10,
      sendCommand: (command) async {
        delivered.add(command.clientMsgId);
      },
      sendQueuedVoice: (_, _) async => VoiceSendStatus.completed,
      deleteTemporaryFile: (path) async {
        deletedTemporaryFiles.add(path);
      },
    );
    await outbox.init();
    await outbox.enqueueCommand(textCommand('client-msg-closed'));
    await outbox.enqueueVoice(
      conversationId: 'conv-closed',
      result: recordResult(),
    );

    await outbox.purgeForTerminalAccountClosure();

    expect(outbox.queueLength, 0);
    expect(deletedTemporaryFiles, <String>['/tmp/voice.m4a']);
    expect(
      await outbox.enqueueCommand(textCommand('client-msg-after-closed')),
      isFalse,
    );
    await outbox.drainQueue();
    expect(delivered, isEmpty);
    await outbox.dispose();

    final reopened = ChatSendOutbox(
      telemetry: _SilentExceptionTelemetryPort(),
      maxQueueSize: 10,
      sendCommand: (_) async {},
      sendQueuedVoice: (_, _) async => VoiceSendStatus.completed,
    );
    addTearDown(reopened.dispose);
    await reopened.init();
    expect(reopened.queueLength, 0);
  });
}

/// 本用例关注离线队列语义，不关注遥测内容：用最小 typed double 吞掉上报，
/// 既满足注入契约，也不让测试依赖真实 telemetry 单例。
final class _SilentExceptionTelemetryPort implements ExceptionTelemetryPort {
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
