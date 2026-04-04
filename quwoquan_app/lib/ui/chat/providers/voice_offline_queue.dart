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
  });

  final int maxQueueSize;
  static const String _boxName = 'voice_offline_queue';

  Box<String>? _box;
  StreamSubscription<List<ConnectivityResult>>? _connectivitySub;
  VoiceSendNotifier? _sendNotifier;

  Future<void> init() async {
    _box = await Hive.openBox<String>(_boxName);
  }

  void bindSendNotifier(VoiceSendNotifier notifier) {
    _sendNotifier = notifier;
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
    final notifier = _sendNotifier;
    if (box == null || notifier == null) return;

    final keys = box.keys.toList();
    for (final key in keys) {
      final raw = box.get(key);
      if (raw == null) continue;

      try {
        final data = jsonDecode(raw) as Map<String, dynamic>;
        final result = VoiceRecordResult(
          filePath: data['filePath'] as String,
          durationMs: (data['durationMs'] as num).toInt(),
          fileSize: (data['fileSize'] as num).toInt(),
          waveform: (data['waveform'] as List)
              .map((e) => (e as num).toDouble())
              .toList(),
        );

        await notifier.sendVoice(result);
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

  @override
  int build() {
    final sendNotifier = ref.watch(voiceSendProvider(conversationId).notifier);
    final queue = VoiceOfflineQueue(maxQueueSize: 50);
    _queue = queue;
    ref.onDispose(() {
      queue.dispose();
    });
    Future<void>.microtask(() async {
      await queue.init();
      queue.bindSendNotifier(sendNotifier);
      queue.startMonitor();
      state = queue.queueLength;
    });
    return 0;
  }

  Future<void> enqueue(VoiceRecordResult result) async {
    final q = _queue;
    if (q == null) return;
    await q.enqueue(
      conversationId: conversationId,
      result: result,
    );
    state = q.queueLength;
  }

  Future<void> drain() async {
    final q = _queue;
    if (q == null) return;
    await q.drainQueue();
    state = q.queueLength;
  }
}

/// Provider for the offline voice queue (per conversation).
final voiceOfflineQueueProvider =
    NotifierProvider.family<VoiceOfflineQueueNotifier, int, String>(
  VoiceOfflineQueueNotifier.new,
);
