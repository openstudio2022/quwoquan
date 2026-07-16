import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/media/media_upload_manager.dart';
import 'package:quwoquan_app/cloud/media/upload_policy.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/trackers/voice_message_observability.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_message_provider.dart';
import 'package:quwoquan_app/ui/chat/widgets/voice/voice_recorder.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/ui/chat/models/chat_message_media_view_data.dart';

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
  VoiceMessageObservability get _observability =>
      ref.read(voiceMessageObservabilityProvider);

  @override
  VoiceSendState build() => const VoiceSendState();

  /// Takes a recording result, uploads to OSS, then sends a voice message.
  Future<void> sendVoice(VoiceRecordResult result) async {
    state = state.copyWith(status: VoiceSendStatus.uploading, error: null);
    _observability.trackAction(
      eventName: VoiceMessageEventNames.uploadStarted,
      conversationId: conversationId,
      durationMs: result.durationMs,
      fileSizeBytes: result.fileSize,
      waveformSamples: result.waveform.length,
    );

    try {
      if (result.fileSize <= 0 || result.filePath.trim().isEmpty) {
        _observability.trackAction(
          eventName: VoiceMessageEventNames.recordInvalid,
          conversationId: conversationId,
          durationMs: result.durationMs,
          fileSizeBytes: result.fileSize,
          waveformSamples: result.waveform.length,
          failureKind: 'invalid_recording',
        );
        state = state.copyWith(
          status: VoiceSendStatus.failed,
          error: UITextConstants.chatVoiceRecordUnavailable,
        );
        return;
      }
      final task = UploadTask(
        localPath: result.filePath,
        category: MediaCategory.chatVoice,
        contentType: 'audio/mp4',
        fileSize: result.fileSize,
      );

      final enqueued = await _uploadManager.enqueue(task);
      if (enqueued.status == UploadStatus.failed) {
        _trackUploadFailed(enqueued.error);
        state = state.copyWith(
          status: VoiceSendStatus.failed,
          error: _userFacingVoiceFailureMessage(enqueued.error),
        );
        return;
      }
      if (enqueued.status == UploadStatus.completed) {
        await _sendUploadedVoice(enqueued, result);
        return;
      }

      await for (final update in _uploadManager.onTaskUpdate) {
        if (update.localPath != enqueued.localPath) continue;
        if (update.status == UploadStatus.uploading) {
          state = state.copyWith(uploadProgress: 0.5);
        }

        if (update.status == UploadStatus.completed) {
          await _sendUploadedVoice(update, result);
          return;
        }

        if (update.status == UploadStatus.failed) {
          _trackUploadFailed(update.error);
          state = state.copyWith(
            status: VoiceSendStatus.failed,
            error: _userFacingVoiceFailureMessage(update.error),
          );
          return;
        }
      }
    } catch (e) {
      _observability.trackAction(
        eventName: VoiceMessageEventNames.sendFailed,
        conversationId: conversationId,
        durationMs: result.durationMs,
        fileSizeBytes: result.fileSize,
        waveformSamples: result.waveform.length,
        failureKind: e.runtimeType.toString(),
      );
      state = state.copyWith(
        status: VoiceSendStatus.failed,
        error: _userFacingVoiceFailureMessage(e),
      );
    }
  }

  Future<void> _sendUploadedVoice(
    UploadTask update,
    VoiceRecordResult result,
  ) async {
    state = state.copyWith(status: VoiceSendStatus.sending);
    _observability.trackAction(
      eventName: VoiceMessageEventNames.uploadSucceeded,
      conversationId: conversationId,
      durationMs: result.durationMs,
      fileSizeBytes: result.fileSize,
      waveformSamples: result.waveform.length,
    );
    final cdnUrl = update.cdnUrl?.trim() ?? '';
    final assetId = update.assetId?.trim() ?? '';
    if (cdnUrl.isEmpty || assetId.isEmpty) {
      _trackUploadFailed(
        cdnUrl.isEmpty ? 'empty_cdn_url' : 'empty_media_asset_id',
      );
      state = state.copyWith(
        status: VoiceSendStatus.failed,
        error: UITextConstants.chatVoicePendingRetry,
      );
      return;
    }

    final mediaPayload = ChatMessageMediaViewData(
      deliveryUrl: cdnUrl,
      assetId: assetId,
      mediaType: 'audio',
      contentType: 'audio/mp4',
      fileSizeBytes: result.fileSize,
      durationMs: result.durationMs,
      waveform: _compactWaveform(result.waveform),
    );

    _observability.trackAction(
      eventName: VoiceMessageEventNames.sendStarted,
      conversationId: conversationId,
      durationMs: result.durationMs,
      fileSizeBytes: result.fileSize,
      waveformSamples: mediaPayload.waveform.length,
    );
    final sent = await _messageNotifier.sendMessage(
      'audio',
      '',
      media: mediaPayload,
    );
    if (!sent) {
      _observability.trackAction(
        eventName: VoiceMessageEventNames.sendFailed,
        conversationId: conversationId,
        durationMs: result.durationMs,
        fileSizeBytes: result.fileSize,
        waveformSamples: mediaPayload.waveform.length,
        failureKind: 'send_message_failed',
      );
      state = state.copyWith(
        status: VoiceSendStatus.failed,
        error: UITextConstants.chatVoicePendingRetry,
      );
      return;
    }

    _observability.trackAction(
      eventName: VoiceMessageEventNames.sendSucceeded,
      conversationId: conversationId,
      durationMs: result.durationMs,
      fileSizeBytes: result.fileSize,
      waveformSamples: mediaPayload.waveform.length,
    );
    state = state.copyWith(status: VoiceSendStatus.completed);
  }

  void reset() {
    state = const VoiceSendState();
  }

  String _userFacingVoiceFailureMessage(Object? raw) {
    if (raw is String) {
      final message = raw.trim();
      if (message.contains('文件大小') || message.contains('文件类型')) {
        return message;
      }
    }
    return UITextConstants.chatVoicePendingRetry;
  }

  void _trackUploadFailed(String? raw) {
    _observability.trackAction(
      eventName: VoiceMessageEventNames.uploadFailed,
      conversationId: conversationId,
      failureKind: (raw ?? '').trim().isEmpty ? 'unknown' : raw!.trim(),
    );
  }

  List<double> _compactWaveform(List<double> waveform) {
    const targetCount = 80;
    if (waveform.length <= targetCount) {
      return waveform.map((value) => value.clamp(0.0, 1.0)).toList();
    }
    final result = <double>[];
    final ratio = waveform.length / targetCount;
    for (var i = 0; i < targetCount; i++) {
      final start = (i * ratio).floor();
      final end = ((i + 1) * ratio).ceil().clamp(0, waveform.length);
      if (start >= end) {
        result.add(0.0);
        continue;
      }
      var sum = 0.0;
      for (var j = start; j < end; j++) {
        sum += waveform[j].clamp(0.0, 1.0).toDouble();
      }
      result.add(sum / (end - start));
    }
    return result;
  }
}

/// Creates a VoiceSendNotifier for a specific conversation.
final voiceSendProvider =
    NotifierProvider.family<VoiceSendNotifier, VoiceSendState, String>(
      VoiceSendNotifier.new,
    );
