import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';

enum AudioOutput {
  earpiece,
  speaker;

  String get label => switch (this) {
    AudioOutput.earpiece => CallText.callAudioEarpiece,
    AudioOutput.speaker => CallText.callAudioSpeaker,
  };
}

enum CameraPosition {
  front,
  back;

  CameraPosition toggle() =>
      this == CameraPosition.front ? CameraPosition.back : CameraPosition.front;
}

class MediaDeviceState {
  final AudioOutput audioOutput;
  final CameraPosition cameraPosition;
  final bool isMicAvailable;
  final bool isCameraAvailable;
  final bool isSpeakerAvailable;

  const MediaDeviceState({
    this.audioOutput = AudioOutput.earpiece,
    this.cameraPosition = CameraPosition.front,
    this.isMicAvailable = true,
    this.isCameraAvailable = true,
    this.isSpeakerAvailable = true,
  });

  MediaDeviceState copyWith({
    AudioOutput? audioOutput,
    CameraPosition? cameraPosition,
    bool? isMicAvailable,
    bool? isCameraAvailable,
    bool? isSpeakerAvailable,
  }) {
    return MediaDeviceState(
      audioOutput: audioOutput ?? this.audioOutput,
      cameraPosition: cameraPosition ?? this.cameraPosition,
      isMicAvailable: isMicAvailable ?? this.isMicAvailable,
      isCameraAvailable: isCameraAvailable ?? this.isCameraAvailable,
      isSpeakerAvailable: isSpeakerAvailable ?? this.isSpeakerAvailable,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is MediaDeviceState &&
          runtimeType == other.runtimeType &&
          audioOutput == other.audioOutput &&
          cameraPosition == other.cameraPosition &&
          isMicAvailable == other.isMicAvailable &&
          isCameraAvailable == other.isCameraAvailable;

  @override
  int get hashCode => Object.hash(
    audioOutput,
    cameraPosition,
    isMicAvailable,
    isCameraAvailable,
  );
}

class MediaDeviceNotifier extends Notifier<MediaDeviceState> {
  @override
  MediaDeviceState build() => const MediaDeviceState();

  Future<void> setAudioOutput(AudioOutput output) async {
    final applied = await ref
        .read(callSessionProvider.notifier)
        .setSpeakerOn(output == AudioOutput.speaker);
    if (applied) {
      state = state.copyWith(audioOutput: output);
    }
  }

  Future<void> toggleSpeaker() async {
    final next = state.audioOutput == AudioOutput.speaker
        ? AudioOutput.earpiece
        : AudioOutput.speaker;
    await setAudioOutput(next);
  }

  Future<void> flipCamera() async {
    final applied = await ref.read(callSessionProvider.notifier).switchCamera();
    if (applied) {
      state = state.copyWith(cameraPosition: state.cameraPosition.toggle());
    }
  }

  void resetToDefaults() {
    state = const MediaDeviceState();
  }
}

final mediaDeviceProvider =
    NotifierProvider<MediaDeviceNotifier, MediaDeviceState>(
      MediaDeviceNotifier.new,
    );
