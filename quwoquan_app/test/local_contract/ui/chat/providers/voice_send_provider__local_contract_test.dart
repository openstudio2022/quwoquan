// spec_ref: specs/feature-tree/chat-conversation/list-detail-message-delivery/voice-message/spec.md#gwt-001
import 'dart:async';
import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/application/content/media/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/cloud/media/media_upload_manager.dart';
import 'package:quwoquan_app/cloud/remote/content/media/local_media_upload_source.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import '../../../../support/cloud_services/chat_repository_mock.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/providers/voice_send_provider.dart';
import 'package:quwoquan_app/ui/chat/widgets/voice/voice_recorder.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../support/cloud_services/content/mock_content_repository.dart';
import '../../../../support/recording_content_media_facet.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    // ChatSendOutbox 持久化队列依赖 Hive；发送失败路径会尝试入队。
    Hive.init(
      '${Directory.systemTemp.path}/qwq_voice_send_test_${DateTime.now().microsecondsSinceEpoch}',
    );
  });

  tearDown(() async {
    await Hive.deleteFromDisk();
  });

  group('VoiceSendNotifier', () {
    test('上传完成后只用 MediaAsset identity 发送 audio 消息', () async {
      final uploadManager = _ImmediateUploadManager(
        assetId: 'media_001',
      );
      final analytics = _FakeAnalyticsService();
      final writer = _TrackingMessageWriter();
      final container = ProviderContainer(
        overrides: [
          mediaUploadManagerProvider.overrideWithValue(uploadManager),
          chatRepositoryCompositionProvider.overrideWithValue(
            MockChatRepository(),
          ),
          chatMessageCommandWriterProvider.overrideWithValue(writer),
          contentConfigRepositoryProvider.overrideWithValue(
            MockContentRepository(),
          ),
          currentUserIdProvider.overrideWithValue('user_001'),
          activePersonaContextProvider.overrideWith(
            (ref) async => ActivePersonaContextViewData.fallback(
              subAccountId: 'user_001',
              ownerUserId: 'user_001',
              displayName: '语音发送测试用户',
              avatarUrl: '',
            ),
          ),
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
      expect(writer.lastCommand?.type, 'audio');
      expect(writer.lastCommand?.mediaAssetId, 'media_001');
      final wire =
          encodeChatSendMessageCommand(writer.lastCommand!).body
              as Map<String, Object?>;
      expect(wire['mediaAssetId'], 'media_001');
      expect(wire, isNot(contains('media')));
      expect(wire, isNot(contains('url')));
      expect(wire, isNot(contains('durationMs')));
      expect(wire, isNot(contains('waveform')));
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
        assetId: 'media_001',
      );
      final analytics = _FakeAnalyticsService();
      final writer = _TrackingMessageWriter();
      final container = ProviderContainer(
        overrides: [
          mediaUploadManagerProvider.overrideWithValue(uploadManager),
          chatRepositoryCompositionProvider.overrideWithValue(
            MockChatRepository(),
          ),
          chatMessageCommandWriterProvider.overrideWithValue(writer),
          contentConfigRepositoryProvider.overrideWithValue(
            MockContentRepository(),
          ),
          activePersonaContextProvider.overrideWith(
            (ref) async => ActivePersonaContextViewData.fallback(
              subAccountId: 'voice_invalid_user',
              ownerUserId: 'voice_invalid_user',
              displayName: '无效录音测试用户',
              avatarUrl: '',
            ),
          ),
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
      expect(state.error, ChatText.chatVoiceRecordUnavailable);
      expect(uploadManager.enqueueCount, 0);
      expect(writer.sendCount, 0);
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
      final writer = _TrackingMessageWriter();
      final container = ProviderContainer(
        overrides: [
          mediaUploadManagerProvider.overrideWithValue(uploadManager),
          chatRepositoryCompositionProvider.overrideWithValue(
            MockChatRepository(),
          ),
          chatMessageCommandWriterProvider.overrideWithValue(writer),
          contentConfigRepositoryProvider.overrideWithValue(
            MockContentRepository(),
          ),
          activePersonaContextProvider.overrideWith(
            (ref) async => ActivePersonaContextViewData.fallback(
              subAccountId: 'voice_upload_failure_user',
              ownerUserId: 'voice_upload_failure_user',
              displayName: '上传失败测试用户',
              avatarUrl: '',
            ),
          ),
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
      expect(state.error, ChatText.chatVoicePendingRetry);
      expect(writer.sendCount, 0);
      expect(
        analytics.events.map((event) => event.eventName),
        contains('voice_upload_failed'),
      );
    });

    test('消息发送失败不会误判为完成', () async {
      final uploadManager = _ImmediateUploadManager(
        assetId: 'media_001',
      );
      final analytics = _FakeAnalyticsService();
      final writer = _TrackingMessageWriter(shouldFail: true);
      final container = ProviderContainer(
        overrides: [
          mediaUploadManagerProvider.overrideWithValue(uploadManager),
          chatRepositoryCompositionProvider.overrideWithValue(
            MockChatRepository(),
          ),
          chatMessageCommandWriterProvider.overrideWithValue(writer),
          contentConfigRepositoryProvider.overrideWithValue(
            MockContentRepository(),
          ),
          activePersonaContextProvider.overrideWith(
            (ref) async => ActivePersonaContextViewData.fallback(
              subAccountId: 'voice_send_failure_user',
              ownerUserId: 'voice_send_failure_user',
              displayName: '发送失败测试用户',
              avatarUrl: '',
            ),
          ),
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
      expect(state.error, ChatText.chatVoicePendingRetry);
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
    this.assetId,
    this.error,
  }) : super(
         coordinator: ContentMediaUploadCoordinator(
           media: RecordingContentMediaFacet(),
         ),
         sourceReader: const LocalContentMediaSourceReader(),
         uploadStream:
             (
               _,
               _, {
               required contentLength,
               required contentType,
               required expectedSha256,
               Future<void>? abortTrigger,
             }) async {},
       );

  final UploadStatus status;
  final String? assetId;
  final String? error;
  int enqueueCount = 0;

  @override
  Future<UploadTask> enqueue(UploadTask task) async {
    enqueueCount++;
    task
      ..status = status
      ..assetId = assetId
      ..error = error;
    return task;
  }

  @override
  Stream<UploadTask> get onTaskUpdate => const Stream<UploadTask>.empty();

  @override
  void startOfflineMonitor() {}
}

class _TrackingMessageWriter implements ChatMessageCommandWriter {
  _TrackingMessageWriter({this.shouldFail = false});

  final bool shouldFail;
  int sendCount = 0;
  ChatSendMessageCommand? lastCommand;

  @override
  Future<ChatSendMessageResult> sendMessage(
    ChatSendMessageCommand command,
  ) async {
    sendCount++;
    if (shouldFail) {
      throw StateError('send failed');
    }
    lastCommand = command;
    return ChatSendMessageResult(
      messageId: 'msg_voice_$sendCount',
      seq: sendCount,
      timestamp: DateTime.utc(2026, 6, 6),
    );
  }
}
