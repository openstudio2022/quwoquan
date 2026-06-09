import 'dart:async';
import 'dart:convert';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/ui/chat/providers/voice_send_provider.dart';
import 'package:quwoquan_app/ui/chat/widgets/voice/voice_recorder.dart';

/// Persists voice recordings to Hive when offline, auto-sends on reconnect.
class VoiceOfflineQueue {
  VoiceOfflineQueue({
    required this.maxQueueSize,
    required this.sendQueuedVoice,
  });

  final int maxQueueSize;
  final Future<VoiceSendStatus> Function(
    String conversationId,
    VoiceRecordResult result,
  )
  sendQueuedVoice;
  static const String _boxName = 'voice_offline_queue';

  Box<String>? _box;
  StreamSubscription<List<ConnectivityResult>>? _connectivitySub;

  Future<void> init() async {
    _box = await Hive.openBox<String>(_boxName);
  }

  /// Enqueue a voice recording for later upload+send.
  Future<bool> enqueue({
    required String conversationId,
    required VoiceRecordResult result,
  }) async {
    final box = _box;
    if (box == null) return false;

    if (box.length >= maxQueueSize) return false;

    final entry = jsonEncode({
      'conversationId': conversationId,
      'filePath': result.filePath,
      'durationMs': result.durationMs,
      'fileSize': result.fileSize,
      'waveform': result.waveform,
      'enqueuedAt': DateTime.now().toIso8601String(),
    });

    await box.add(entry);
    startMonitor();
    return true;
  }

  /// Starts monitoring connectivity and auto-sending queued items.
  void startMonitor() {
    _connectivitySub ??= Connectivity().onConnectivityChanged.listen((results) {
      final hasConnection = results.any((r) => r != ConnectivityResult.none);
      if (hasConnection) {
        drainQueue();
      }
    });
  }

  /// Attempts to send all queued voice recordings.
  Future<void> drainQueue() async {
    final box = _box;
    if (box == null) return;

    final keys = box.keys.toList();
    for (final key in keys) {
      final raw = box.get(key);
      if (raw == null) continue;

      try {
        final data = jsonDecode(raw) as Map<String, dynamic>;
        final conversationId = (data['conversationId'] as String?)?.trim();
        if (conversationId == null || conversationId.isEmpty) {
          await box.delete(key);
          continue;
        }
        final result = VoiceRecordResult(
          filePath: data['filePath'] as String,
          durationMs: (data['durationMs'] as num).toInt(),
          fileSize: (data['fileSize'] as num).toInt(),
          waveform: (data['waveform'] as List)
              .map((e) => (e as num).toDouble())
              .toList(),
        );

        final sendStatus = await sendQueuedVoice(conversationId, result);
        if (sendStatus != VoiceSendStatus.completed) {
          break;
        }
        await box.delete(key);
      } catch (_) {
        break;
      }
    }
  }

  int get queueLength => _box?.length ?? 0;

  Future<void> dispose() async {
    _connectivitySub?.cancel();
    await _box?.close();
  }
}

class VoiceOfflineQueueNotifier extends Notifier<int> {
  VoiceOfflineQueueNotifier(this.conversationId);

  final String conversationId;
  VoiceOfflineQueue? _queue;
  Future<void>? _ready;

  @override
  int build() {
    final sender = ref.read(voiceQueuedSenderProvider);
    final queue = VoiceOfflineQueue(maxQueueSize: 50, sendQueuedVoice: sender);
    _queue = queue;
    ref.onDispose(() {
      queue.dispose();
    });
    _ready = Future<void>.microtask(() async {
      await queue.init();
      state = queue.queueLength;
      if (state > 0) {
        queue.startMonitor();
      }
    });
    return 0;
  }

  Future<void> enqueue(VoiceRecordResult result) async {
    final q = _queue;
    if (q == null) return;
    await _ready;
    await q.enqueue(conversationId: conversationId, result: result);
    state = q.queueLength;
  }

  Future<void> drain() async {
    final q = _queue;
    if (q == null) return;
    await _ready;
    await q.drainQueue();
    state = q.queueLength;
  }
}

/// Provider for the offline voice queue (per conversation).
final voiceOfflineQueueProvider =
    NotifierProvider.family<VoiceOfflineQueueNotifier, int, String>(
      VoiceOfflineQueueNotifier.new,
    );

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
