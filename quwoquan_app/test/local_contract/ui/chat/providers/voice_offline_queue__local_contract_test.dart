import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/ui/chat/providers/voice_offline_queue.dart';
import 'package:quwoquan_app/ui/chat/providers/voice_send_provider.dart';
import 'package:quwoquan_app/ui/chat/widgets/voice/voice_recorder.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    Hive.init(
      '${Directory.systemTemp.path}/qwq_voice_queue_test_${DateTime.now().microsecondsSinceEpoch}',
    );
  });

  tearDown(() async {
    await Hive.deleteFromDisk();
  });

  test('drain 成功后删除队列项', () async {
    final container = ProviderContainer(
      overrides: [
        voiceQueuedSenderProvider.overrideWithValue(
          (_, _) async => VoiceSendStatus.completed,
        ),
      ],
    );
    addTearDown(container.dispose);

    final notifier = container.read(
      voiceOfflineQueueProvider('conv_001').notifier,
    );
    await _waitForQueueInit(container, 'conv_001');
    await notifier.enqueue(_recordResult());
    expect(container.read(voiceOfflineQueueProvider('conv_001')), 1);

    await notifier.drain();

    expect(container.read(voiceOfflineQueueProvider('conv_001')), 0);
  });

  test('drain 失败时保留队列项等待后续恢复', () async {
    final container = ProviderContainer(
      overrides: [
        voiceQueuedSenderProvider.overrideWithValue(
          (_, _) async => VoiceSendStatus.failed,
        ),
      ],
    );
    addTearDown(container.dispose);

    final notifier = container.read(
      voiceOfflineQueueProvider('conv_001').notifier,
    );
    await _waitForQueueInit(container, 'conv_001');
    await notifier.enqueue(_recordResult());

    await notifier.drain();

    expect(container.read(voiceOfflineQueueProvider('conv_001')), 1);
  });
}

VoiceRecordResult _recordResult() {
  return const VoiceRecordResult(
    filePath: '/tmp/voice.m4a',
    durationMs: 1200,
    fileSize: 1024,
    waveform: <double>[0.1, 0.4],
  );
}

Future<void> _waitForQueueInit(
  ProviderContainer container,
  String conversationId,
) async {
  container.read(voiceOfflineQueueProvider(conversationId));
  await Future<void>.delayed(Duration.zero);
  await Future<void>.delayed(Duration.zero);
}
