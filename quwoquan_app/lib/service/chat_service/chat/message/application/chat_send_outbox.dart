import 'dart:async';
import 'dart:convert';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/platform/temporary_file_cleanup.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_message_provider.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_send_outbox_control.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/voice_send_provider.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/voice_recording.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/voice_message_interaction.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// chat 发送可靠性的唯一持久化待发队列：文本命令与语音录音统一入队，
/// Hive 落盘保证断网/杀进程后自动重发；clientMsgId 幂等贯穿进程重启，
/// 服务端以唯一约束把重放折叠为首次结果。
///
/// 队列项两种形状（kind 字段区分）：
/// - `command`：ChatSendMessageCommand 的可重建 JSON（分享卡片消息不入队，
///   卡片发送失败由发起面即时反馈）。
/// - `voice`：待上传语音的本地文件引用，drain 时走上传+发送链。
class ChatSendOutbox {
  ChatSendOutbox({
    required this.maxQueueSize,
    required this.sendCommand,
    required this.sendQueuedVoice,
    required this.telemetry,
    this.onCommandDelivered,
    Future<void> Function(String path)? deleteTemporaryFile,
  }) : _deleteTemporaryFile = deleteTemporaryFile ?? deleteAppTemporaryFile;

  final ExceptionTelemetryPort telemetry;
  final int maxQueueSize;
  final Future<void> Function(ChatSendMessageCommand command) sendCommand;
  final Future<VoiceSendStatus> Function(
    String conversationId,
    VoiceRecordResult result,
  )
  sendQueuedVoice;

  /// 自动 drain 送达一条命令后回调（conversationId）：会话打开时气泡可能
  /// 停留在 failed 态，必须由消费方刷新该会话 timeline 与服务端收敛。
  final void Function(String conversationId)? onCommandDelivered;
  final Future<void> Function(String path) _deleteTemporaryFile;

  static const String boxName = 'chat_send_outbox';

  Box<String>? _box;
  StreamSubscription<List<ConnectivityResult>>? _connectivitySub;
  bool _draining = false;
  bool _terminallyPurged = false;

  Future<void> init() async {
    try {
      _box = await Hive.openBox<String>(boxName);
    } catch (error, stackTrace) {
      // Hive 不可用（如测试容器未初始化本地存储）时降级为不持久化：
      // 发送失败仍即时反馈，仅失去跨重启自动重发；结构化上报保留观测。
      unawaited(
        telemetry.recordHandledException(
          source: 'chat.send_outbox.init',
          error: error,
          stackTrace: stackTrace,
        ),
      );
    }
  }

  /// 文本/已上传媒体命令入队（发送失败或离线时调用）。
  Future<bool> enqueueCommand(ChatSendMessageCommand command) async {
    final box = _box;
    if (_terminallyPurged || box == null || box.length >= maxQueueSize) {
      return false;
    }
    if (command.card != null) return false;
    await box.add(
      jsonEncode(<String, Object?>{
        'kind': 'command',
        'conversationId': command.conversationId,
        'type': command.type,
        'content': command.content,
        'clientMsgId': command.clientMsgId,
        'mediaAssetId': command.mediaAssetId,
        'replyToMessageId': command.replyToMessageId,
        'mentions': command.mentions,
        'senderDisplayNameSnapshot': command.senderDisplayNameSnapshot,
        'senderAvatarUrlSnapshot': command.senderAvatarUrlSnapshot,
        'personaContextVersion': command.personaContextVersion,
        'enqueuedAt': DateTime.now().toIso8601String(),
      }),
    );
    startMonitor();
    return true;
  }

  /// 语音录音入队（上传或发送失败时调用）。
  Future<bool> enqueueVoice({
    required String conversationId,
    required VoiceRecordResult result,
  }) async {
    final box = _box;
    if (_terminallyPurged || box == null || box.length >= maxQueueSize) {
      return false;
    }
    await box.add(
      jsonEncode(<String, Object?>{
        'kind': 'voice',
        'conversationId': conversationId,
        'filePath': result.filePath,
        'durationMs': result.durationMs,
        'fileSize': result.fileSize,
        'waveform': result.waveform,
        'enqueuedAt': DateTime.now().toIso8601String(),
      }),
    );
    startMonitor();
    return true;
  }

  /// 监听连通性恢复后自动 drain。
  void startMonitor() {
    if (_terminallyPurged) {
      return;
    }
    _connectivitySub ??= Connectivity().onConnectivityChanged.listen((results) {
      final hasConnection = results.any((r) => r != ConnectivityResult.none);
      if (hasConnection) {
        drainQueue();
      }
    });
  }

  /// 顺序重发全部队列项；单项失败停止本轮（保持发送顺序），等待下次触发。
  Future<void> drainQueue() async {
    final box = _box;
    if (_terminallyPurged || box == null || _draining) return;
    _draining = true;
    try {
      final keys = box.keys.toList();
      for (final key in keys) {
        if (_terminallyPurged) {
          break;
        }
        final raw = box.get(key);
        if (raw == null) continue;
        try {
          final data = jsonDecode(raw) as Map<String, dynamic>;
          final conversationId =
              (data['conversationId'] as String?)?.trim() ?? '';
          if (conversationId.isEmpty) {
            await box.delete(key);
            continue;
          }
          final kind = data['kind'] as String? ?? 'voice';
          final delivered = switch (kind) {
            'command' => await _drainCommand(data),
            _ => await _drainVoice(conversationId, data),
          };
          if (!delivered) {
            break;
          }
          await box.delete(key);
          if (kind == 'command') {
            onCommandDelivered?.call(conversationId);
          }
        } catch (error, stackTrace) {
          unawaited(
            telemetry.recordHandledException(
              source: 'chat.send_outbox.drain',
              error: error,
              stackTrace: stackTrace,
            ),
          );
          break;
        }
      }
    } finally {
      _draining = false;
    }
  }

  Future<bool> _drainCommand(Map<String, dynamic> data) async {
    final command = ChatSendMessageCommand(
      conversationId: data['conversationId'] as String,
      type: (data['type'] as String?) ?? 'text',
      content: (data['content'] as String?) ?? '',
      clientMsgId: data['clientMsgId'] as String,
      mediaAssetId: data['mediaAssetId'] as String?,
      replyToMessageId: data['replyToMessageId'] as String?,
      mentions: ((data['mentions'] as List?) ?? const <Object?>[])
          .map((item) => item.toString())
          .where((item) => item.isNotEmpty),
      senderDisplayNameSnapshot: data['senderDisplayNameSnapshot'] as String?,
      senderAvatarUrlSnapshot: data['senderAvatarUrlSnapshot'] as String?,
      personaContextVersion: (data['personaContextVersion'] as num?)?.toInt(),
    );
    try {
      await sendCommand(command);
      return true;
    } on CloudException catch (error) {
      // 幂等冲突说明服务端已持有首次结果，视为已送达出队。
      if ((error.code ?? '').endsWith('message_idempotency_conflict')) {
        return true;
      }
      rethrow;
    }
  }

  Future<bool> _drainVoice(
    String conversationId,
    Map<String, dynamic> data,
  ) async {
    final result = VoiceRecordResult(
      filePath: data['filePath'] as String,
      durationMs: (data['durationMs'] as num).toInt(),
      fileSize: (data['fileSize'] as num).toInt(),
      waveform: ((data['waveform'] as List?) ?? const <Object?>[])
          .map((e) => (e as num).toDouble())
          .toList(),
    );
    final status = await sendQueuedVoice(conversationId, result);
    return status == VoiceSendStatus.completed;
  }

  int get queueLength => _box?.length ?? 0;

  /// 云侧账号 closed 后停止重试并物理清空待发文本、媒体引用与语音引用。
  Future<void> purgeForTerminalAccountClosure() async {
    _terminallyPurged = true;
    await _connectivitySub?.cancel();
    _connectivitySub = null;
    final box = _box;
    if (box == null) {
      return;
    }
    final voicePaths = <String>{};
    for (final raw in box.values) {
      try {
        final decoded = jsonDecode(raw);
        if (decoded is Map && decoded['kind'] == 'voice') {
          final path = decoded['filePath']?.toString().trim() ?? '';
          if (path.isNotEmpty) {
            voicePaths.add(path);
          }
        }
      } on FormatException {
        // 损坏队列仍会被物理清空；无法可信解析的路径绝不能用于文件删除。
      }
    }
    Object? firstFileError;
    StackTrace? firstFileStackTrace;
    for (final path in voicePaths) {
      try {
        await _deleteTemporaryFile(path);
      } catch (error, stackTrace) {
        firstFileError ??= error;
        firstFileStackTrace ??= stackTrace;
      }
    }
    await box.clear();
    if (box.isNotEmpty) {
      throw StateError('chat send outbox cleanup verification failed');
    }
    if (firstFileError != null) {
      Error.throwWithStackTrace(firstFileError, firstFileStackTrace!);
    }
  }

  Future<void> dispose() async {
    await _connectivitySub?.cancel();
    await _box?.close();
  }
}

/// 全局 chat 发送 outbox（跨会话共享一个持久化队列，保持发送顺序）。
class ChatSendOutboxNotifier extends Notifier<int>
    implements ChatSendOutboxControl {
  ChatSendOutbox? _outbox;
  Future<void>? _ready;
  bool _terminalPurgeRequested = false;

  @override
  int build() {
    final writer = ref.read(chatMessageCommandWriterProvider);
    final voiceSender = ref.read(voiceQueuedSenderProvider);
    final outbox = ChatSendOutbox(
      maxQueueSize: 200,
      sendCommand: (command) => writer.sendMessage(command),
      sendQueuedVoice: voiceSender,
      telemetry: ref.read(exceptionTelemetryPortProvider),
      onCommandDelivered: (conversationId) {
        // 自动重放送达后刷新该会话 timeline：failed 气泡收敛为服务端确认态。
        unawaited(
          ref.read(chatMessageProvider(conversationId).notifier).loadMessages(),
        );
      },
    );
    _outbox = outbox;
    ref.onDispose(() {
      outbox.dispose();
    });
    _ready = Future<void>.microtask(() async {
      await outbox.init();
      if (_terminalPurgeRequested) {
        await outbox.purgeForTerminalAccountClosure();
        state = 0;
        return;
      }
      state = outbox.queueLength;
      if (state > 0) {
        outbox.startMonitor();
        unawaited(outbox.drainQueue());
      }
    });
    return 0;
  }

  @override
  Future<bool> enqueueCommand(ChatSendMessageCommand command) async {
    final outbox = _outbox;
    if (outbox == null) return false;
    await _ready;
    final accepted = await outbox.enqueueCommand(command);
    state = outbox.queueLength;
    return accepted;
  }

  @override
  Future<bool> enqueueVoice({
    required String conversationId,
    required QueuedChatVoice voice,
  }) async {
    final outbox = _outbox;
    if (outbox == null) return false;
    await _ready;
    final accepted = await outbox.enqueueVoice(
      conversationId: conversationId,
      result: VoiceRecordResult(
        filePath: voice.filePath,
        durationMs: voice.durationMs,
        fileSize: voice.fileSize,
        waveform: voice.waveform,
      ),
    );
    state = outbox.queueLength;
    return accepted;
  }

  @override
  Future<void> drain() async {
    final outbox = _outbox;
    if (outbox == null) return;
    await _ready;
    await outbox.drainQueue();
    state = outbox.queueLength;
  }

  @override
  Future<void> purgeForTerminalAccountClosure() async {
    _terminalPurgeRequested = true;
    final outbox = _outbox;
    if (outbox == null) {
      return;
    }
    await _ready;
    await outbox.purgeForTerminalAccountClosure();
    state = outbox.queueLength;
  }
}

final chatSendOutboxProvider = NotifierProvider<ChatSendOutboxNotifier, int>(
  ChatSendOutboxNotifier.new,
);

/// 语音重发链：复用 voiceSendProvider 的上传+发送流程。
final voiceQueuedSenderProvider =
    Provider<
      Future<VoiceSendStatus> Function(
        String conversationId,
        VoiceRecordResult result,
      )
    >((ref) {
      return (conversationId, result) async {
        await ref
            .read(voiceSendProvider(conversationId).notifier)
            .sendVoice(result);
        return ref.read(voiceSendProvider(conversationId)).status;
      };
    });
