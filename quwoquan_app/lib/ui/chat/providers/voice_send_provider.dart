import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/media/media_upload_manager.dart';
import 'package:quwoquan_app/cloud/media/upload_policy.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_message_provider.dart';
import 'package:quwoquan_app/ui/chat/widgets/voice/voice_recorder.dart';
import 'package:quwoquan_app/cloud/runtime/errors/runtime_error_display.dart';

/// Orchestrates: record result → upload → send voice message.
enum VoiceSendStatus { idle, uploading, sending, completed, failed }

class VoiceSendState {
  final VoiceSendStatus status;
  final String? error;
  final double uploadProgress;

  const VoiceSendState({
    this.status = VoiceSendStatus.idle,
    this.error,
    this.uploadProgress = 0,
  });

  VoiceSendState copyWith({
    VoiceSendStatus? status,
    String? error,
    double? uploadProgress,
  }) {
    return VoiceSendState(
      status: status ?? this.status,
      error: error,
      uploadProgress: uploadProgress ?? this.uploadProgress,
    );
  }
}

class VoiceSendNotifier extends Notifier<VoiceSendState> {
  VoiceSendNotifier(this.conversationId);

  final String conversationId;

  MediaUploadManager get _uploadManager => ref.read(mediaUploadManagerProvider);
  ChatMessageNotifier get _messageNotifier =>
      ref.read(chatMessageProvider(conversationId).notifier);

  @override
  VoiceSendState build() => const VoiceSendState();

  /// Takes a recording result, uploads to OSS, then sends a voice message.
  Future<void> sendVoice(VoiceRecordResult result) async {
    state = state.copyWith(status: VoiceSendStatus.uploading, error: null);

    try {
      final task = UploadTask(
        localPath: result.filePath,
        category: MediaCategory.chatVoice,
        contentType: 'audio/mp4',
        fileSize: result.fileSize,
        ownerId: 'current_user',
        fileName: result.filePath.split('/').last,
        completionMetadata: {'durationMs': result.durationMs},
      );

      final enqueued = await _uploadManager.enqueue(task);

      await for (final update in _uploadManager.onTaskUpdate) {
        if (update.localPath != enqueued.localPath) continue;

        if (update.status == UploadStatus.completed) {
          state = state.copyWith(status: VoiceSendStatus.sending);

          final mediaPayload = <String, dynamic>{
            'url': update.cdnUrl ?? '',
            'mediaId': update.assetId,
            'mimeType': 'audio/mp4',
            'fileSizeBytes': result.fileSize,
            'durationMs': result.durationMs,
            'waveform': result.waveform,
            'codec': 'aac',
          };

          await _messageNotifier.sendMessage(
            'audio',
            '',
            mediaUrl: update.cdnUrl,
            media: mediaPayload,
          );

          state = state.copyWith(status: VoiceSendStatus.completed);
          return;
        }

        if (update.status == UploadStatus.failed) {
          state = state.copyWith(
            status: VoiceSendStatus.failed,
            error: update.error ?? '上传失败',
          );
          return;
        }
      }
    } catch (e) {
      state = state.copyWith(
        status: VoiceSendStatus.failed,
        error: runtimeErrorDisplayMessage(e),
      );
    }
  }

  void reset() {
    state = const VoiceSendState();
  }
}

/// Creates a VoiceSendNotifier for a specific conversation.
final voiceSendProvider =
    NotifierProvider.family<VoiceSendNotifier, VoiceSendState, String>(
      VoiceSendNotifier.new,
    );
