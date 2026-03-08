import 'package:flutter_riverpod/flutter_riverpod.dart';

enum AudioOutput {
  earpiece,
  speaker,
  bluetooth;

  String get label => switch (this) {
        AudioOutput.earpiece => '听筒',
        AudioOutput.speaker => '扬声器',
        AudioOutput.bluetooth => '蓝牙',
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
  final bool isBluetoothAvailable;

  const MediaDeviceState({
    this.audioOutput = AudioOutput.earpiece,
    this.cameraPosition = CameraPosition.front,
    this.isMicAvailable = true,
    this.isCameraAvailable = true,
    this.isSpeakerAvailable = true,
    this.isBluetoothAvailable = false,
  });

  MediaDeviceState copyWith({
    AudioOutput? audioOutput,
    CameraPosition? cameraPosition,
    bool? isMicAvailable,
    bool? isCameraAvailable,
    bool? isSpeakerAvailable,
    bool? isBluetoothAvailable,
  }) {
    return MediaDeviceState(
      audioOutput: audioOutput ?? this.audioOutput,
      cameraPosition: cameraPosition ?? this.cameraPosition,
      isMicAvailable: isMicAvailable ?? this.isMicAvailable,
      isCameraAvailable: isCameraAvailable ?? this.isCameraAvailable,
      isSpeakerAvailable: isSpeakerAvailable ?? this.isSpeakerAvailable,
      isBluetoothAvailable: isBluetoothAvailable ?? this.isBluetoothAvailable,
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
  int get hashCode =>
      Object.hash(audioOutput, cameraPosition, isMicAvailable, isCameraAvailable);
}

class MediaDeviceNotifier extends Notifier<MediaDeviceState> {
  @override
  MediaDeviceState build() => const MediaDeviceState();

  void setAudioOutput(AudioOutput output) {
    state = state.copyWith(audioOutput: output);
  }

  void toggleSpeaker() {
    final next = state.audioOutput == AudioOutput.speaker
        ? AudioOutput.earpiece
        : AudioOutput.speaker;
    state = state.copyWith(audioOutput: next);
  }

  void flipCamera() {
    state = state.copyWith(
      cameraPosition: state.cameraPosition.toggle(),
    );
  }

  void setBluetoothAvailable(bool available) {
    state = state.copyWith(isBluetoothAvailable: available);
    if (!available && state.audioOutput == AudioOutput.bluetooth) {
      state = state.copyWith(audioOutput: AudioOutput.earpiece);
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
