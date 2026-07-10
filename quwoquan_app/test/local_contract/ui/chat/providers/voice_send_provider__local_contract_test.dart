import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/cloud/chat/models/send_message_response.dart';
import 'package:quwoquan_app/cloud/media/media_upload_manager.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/providers/voice_send_provider.dart';
import 'package:quwoquan_app/ui/chat/widgets/voice/voice_recorder.dart';

void main() {
  group('VoiceSendNotifier', () {
    test('上传完成后发送 audio 消息并压缩 waveform', () async {
      final uploadManager = _ImmediateUploadManager(
        cdnUrl: 'https://cdn.example.com/voice.m4a',
        assetId: 'media_001',
      );
      final analytics = _FakeAnalyticsService();
      final chatRepo = _TrackingChatRepository();
      final container = ProviderContainer(
        overrides: [
          mediaUploadManagerProvider.overrideWithValue(uploadManager),
          chatRepositoryProvider.overrideWithValue(chatRepo),
          currentUserIdProvider.overrideWithValue('user_001'),
          analyticsProvider.overrideWithValue(analytics),
        ],
      );
      addTearDown(container.dispose);
      addTearDown(uploadManager.dispose);

      final notifier = container.read(voiceSendProvider('conv_001').notifier);
      await notifier.sendVoice(
        VoiceRecordResult(
          filePath: '/tmp/voice.m4a',
          durationMs: 3200,
          fileSize: 1024,
          waveform: List<double>.generate(160, (index) => index / 160),
        ),
      );

      final state = container.read(voiceSendProvider('conv_001'));
      expect(state.status, VoiceSendStatus.completed);
      expect(chatRepo.lastType, 'audio');
      expect(chatRepo.lastMediaUrl, 'https://cdn.example.com/voice.m4a');
      expect(chatRepo.lastMedia?['durationMs'], 3200);
      expect(chatRepo.lastMedia?['codec'], 'aac');
      expect((chatRepo.lastMedia?['waveform'] as List), hasLength(80));
      expect(
        analytics.events.map((event) => event.eventName),
        containsAll(<String>[
          'voice_upload_started',
          'voice_upload_succeeded',
          'voice_send_started',
          'voice_send_succeeded',
        ]),
      );
    });

    test('无效录音文件不会上传或发送', () async {
      final uploadManager = _ImmediateUploadManager(
        cdnUrl: 'https://cdn.example.com/voice.m4a',
        assetId: 'media_001',
      );
      final analytics = _FakeAnalyticsService();
      final chatRepo = _TrackingChatRepository();
      final container = ProviderContainer(
        overrides: [
          mediaUploadManagerProvider.overrideWithValue(uploadManager),
          chatRepositoryProvider.overrideWithValue(chatRepo),
          analyticsProvider.overrideWithValue(analytics),
        ],
      );
      addTearDown(container.dispose);
      addTearDown(uploadManager.dispose);

      await container
          .read(voiceSendProvider('conv_001').notifier)
          .sendVoice(
            const VoiceRecordResult(
              filePath: '',
              durationMs: 1200,
              fileSize: 0,
              waveform: <double>[],
            ),
          );

      final state = container.read(voiceSendProvider('conv_001'));
      expect(state.status, VoiceSendStatus.failed);
      expect(state.error, UITextConstants.chatVoiceRecordUnavailable);
      expect(uploadManager.enqueueCount, 0);
      expect(chatRepo.sendCount, 0);
      expect(
        analytics.events.map((event) => event.eventName),
        contains('voice_record_invalid'),
      );
    });

    test('上传失败映射为统一语音上传失败文案', () async {
      final uploadManager = _ImmediateUploadManager(
        status: UploadStatus.failed,
        error: 'socket closed',
      );
      final analytics = _FakeAnalyticsService();
      final chatRepo = _TrackingChatRepository();
      final container = ProviderContainer(
        overrides: [
          mediaUploadManagerProvider.overrideWithValue(uploadManager),
          chatRepositoryProvider.overrideWithValue(chatRepo),
          analyticsProvider.overrideWithValue(analytics),
        ],
      );
      addTearDown(container.dispose);
      addTearDown(uploadManager.dispose);

      await container
          .read(voiceSendProvider('conv_001').notifier)
          .sendVoice(
            const VoiceRecordResult(
              filePath: '/tmp/voice.m4a',
              durationMs: 1200,
              fileSize: 1024,
              waveform: <double>[0.2, 0.8],
            ),
          );

      final state = container.read(voiceSendProvider('conv_001'));
      expect(state.status, VoiceSendStatus.failed);
      expect(state.error, UITextConstants.chatVoicePendingRetry);
      expect(chatRepo.sendCount, 0);
      expect(
        analytics.events.map((event) => event.eventName),
        contains('voice_upload_failed'),
      );
    });

    test('消息发送失败不会误判为完成', () async {
      final uploadManager = _ImmediateUploadManager(
        cdnUrl: 'https://cdn.example.com/voice.m4a',
        assetId: 'media_001',
      );
      final analytics = _FakeAnalyticsService();
      final chatRepo = _TrackingChatRepository(shouldFail: true);
      final container = ProviderContainer(
        overrides: [
          mediaUploadManagerProvider.overrideWithValue(uploadManager),
          chatRepositoryProvider.overrideWithValue(chatRepo),
          analyticsProvider.overrideWithValue(analytics),
        ],
      );
      addTearDown(container.dispose);
      addTearDown(uploadManager.dispose);

      await container
          .read(voiceSendProvider('conv_001').notifier)
          .sendVoice(
            const VoiceRecordResult(
              filePath: '/tmp/voice.m4a',
              durationMs: 1200,
              fileSize: 1024,
              waveform: <double>[0.2, 0.8],
            ),
          );

      final state = container.read(voiceSendProvider('conv_001'));
      expect(state.status, VoiceSendStatus.failed);
      expect(state.error, UITextConstants.chatVoicePendingRetry);
      expect(
        analytics.events.map((event) => event.eventName),
        contains('voice_send_failed'),
      );
    });
  });
}

class _FakeAnalyticsService extends AnalyticsService {
  _FakeAnalyticsService() : super.forTesting();

  final List<AnalyticsEvent> events = <AnalyticsEvent>[];

  @override
  Future<void> trackEvent(AnalyticsEvent event) async {
    events.add(event);
  }
}

class _ImmediateUploadManager extends MediaUploadManager {
  _ImmediateUploadManager({
    this.status = UploadStatus.completed,
    this.cdnUrl,
    this.assetId,
    this.error,
  }) : super();

  final UploadStatus status;
  final String? cdnUrl;
  final String? assetId;
  final String? error;
  int enqueueCount = 0;

  @override
  Future<UploadTask> enqueue(UploadTask task) async {
    enqueueCount++;
    task
      ..status = status
      ..cdnUrl = cdnUrl
      ..assetId = assetId
      ..error = error;
    return task;
  }

  @override
  Stream<UploadTask> get onTaskUpdate => const Stream<UploadTask>.empty();

  @override
  void startOfflineMonitor() {}
}

class _TrackingChatRepository extends MockChatRepository {
  _TrackingChatRepository({this.shouldFail = false});

  final bool shouldFail;
  int sendCount = 0;
  String? lastType;
  String? lastMediaUrl;
  CloudJsonMap? lastMedia;

  @override
  Future<SendMessageResponse> sendMessage({
    required String conversationId,
    required String type,
    required String content,
    String? mediaUrl,
    CloudJsonMap? media,
    CloudJsonMap? cardPayload,
    String? replyToMessageId,
    List<String>? mentions,
    String? senderSubAccountId,
    String? personaContextVersion,
    String? senderDisplayNameSnapshot,
    String? senderAvatarUrlSnapshot,
    required String clientMsgId,
  }) async {
    sendCount++;
    if (shouldFail) {
      throw StateError('send failed');
    }
    lastType = type;
    lastMediaUrl = mediaUrl;
    lastMedia = media;
    return SendMessageResponse(
      id: 'msg_voice_$sendCount',
      seq: sendCount,
      timestamp: DateTime.utc(2026, 6, 6),
    );
  }
}
