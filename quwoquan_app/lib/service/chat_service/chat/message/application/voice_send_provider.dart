import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_upload_queue.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/observability/trackers/voice_message_observability.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_message_provider.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/voice_recording.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/voice_message_interaction.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_media_view_data.dart';

/// Orchestrates: record result → upload → send voice message.
class VoiceSendNotifier extends Notifier<VoiceSendState>
    implements VoiceSendController {
  VoiceSendNotifier(this.conversationId);

  final String conversationId;

  MediaUploadQueue get _uploadManager => ref.read(mediaUploadQueueProvider);
  ChatMessageNotifier get _messageNotifier =>
      ref.read(chatMessageProvider(conversationId).notifier);
  VoiceMessageObservability get _observability =>
      ref.read(voiceMessageObservabilityProvider);

  @override
  VoiceSendState build() => const VoiceSendState();

  /// Takes a recording result, uploads to OSS, then sends a voice message.
  @override
  Future<void> sendVoice(VoiceRecordResult result) async {
    state = state.copyWith(status: VoiceSendStatus.uploading, error: null);
    _observability.trackVoiceEvent(
      eventName: VoiceMessageEventNames.uploadStarted,
      conversationId: conversationId,
      durationMs: result.durationMs,
      fileSizeBytes: result.fileSize,
      waveformSamples: result.waveform.length,
    );

    try {
      if (result.fileSize <= 0 || result.filePath.trim().isEmpty) {
        _observability.trackVoiceEvent(
          eventName: VoiceMessageEventNames.recordInvalid,
          conversationId: conversationId,
          durationMs: result.durationMs,
          fileSizeBytes: result.fileSize,
          waveformSamples: result.waveform.length,
          failureKind: 'invalid_recording',
        );
        state = state.copyWith(
          status: VoiceSendStatus.failed,
          error: ChatText.chatVoiceRecordUnavailable,
        );
        return;
      }
      final policyError = _uploadManager.validate(
        category: MediaCategory.chatVoice,
        fileSize: result.fileSize,
        mimeType: 'audio/mp4',
      );
      if (policyError != null) {
        _trackUploadFailed('upload_policy_rejected');
        state = state.copyWith(
          status: VoiceSendStatus.failed,
          error: policyError,
        );
        return;
      }
      final task = UploadTask(
        localPath: result.filePath,
        category: MediaCategory.chatVoice,
        mimeType: 'audio/mp4',
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
      _observability.trackVoiceEvent(
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
    _observability.trackVoiceEvent(
      eventName: VoiceMessageEventNames.uploadSucceeded,
      conversationId: conversationId,
      durationMs: result.durationMs,
      fileSizeBytes: result.fileSize,
      waveformSamples: result.waveform.length,
    );
    final assetId = update.assetId?.trim() ?? '';
    if (assetId.isEmpty) {
      _trackUploadFailed('empty_media_asset_id');
      state = state.copyWith(
        status: VoiceSendStatus.failed,
        error: ChatText.chatVoicePendingRetry,
      );
      return;
    }

    final mediaPayload = ChatMessageMediaViewData(
      // 仅用于本条乐观气泡；Message 命令只发送 assetId，服务端在 ready
      // 校验后投影 canonical delivery URL。
      deliveryUrl: update.localPath,
      assetId: assetId,
      mediaType: 'audio',
      mimeType: 'audio/mp4',
      fileSizeBytes: result.fileSize,
      durationMs: result.durationMs,
      waveform: _compactWaveform(result.waveform),
    );

    _observability.trackVoiceEvent(
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
      _observability.trackVoiceEvent(
        eventName: VoiceMessageEventNames.sendFailed,
        conversationId: conversationId,
        durationMs: result.durationMs,
        fileSizeBytes: result.fileSize,
        waveformSamples: mediaPayload.waveform.length,
        failureKind: 'send_message_failed',
      );
      state = state.copyWith(
        status: VoiceSendStatus.failed,
        error: ChatText.chatVoicePendingRetry,
      );
      return;
    }

    _observability.trackVoiceEvent(
      eventName: VoiceMessageEventNames.sendSucceeded,
      conversationId: conversationId,
      durationMs: result.durationMs,
      fileSizeBytes: result.fileSize,
      waveformSamples: mediaPayload.waveform.length,
    );
    state = state.copyWith(status: VoiceSendStatus.completed);
  }

  @override
  void reset() {
    state = const VoiceSendState();
  }

  String _userFacingVoiceFailureMessage(Object? _) {
    return ChatText.chatVoicePendingRetry;
  }

  void _trackUploadFailed(String? raw) {
    _observability.trackVoiceEvent(
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
