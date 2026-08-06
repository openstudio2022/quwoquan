import 'package:quwoquan_app/service/chat_service/chat/message/application/public/voice_recording.dart';

enum VoiceSendStatus { idle, uploading, sending, completed, failed }

final class VoiceSendState {
  const VoiceSendState({
    this.status = VoiceSendStatus.idle,
    this.error,
    this.uploadProgress = 0,
  });

  final VoiceSendStatus status;
  final String? error;
  final double uploadProgress;

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

abstract interface class VoiceSendController {
  Future<void> sendVoice(VoiceRecordResult result);

  void reset();
}

abstract interface class VoicePlaybackControl {
  Future<void> stop();
}
