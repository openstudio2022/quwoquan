import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/platform/call_audio_session_gateway.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_session_provider.dart';

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

/// 本地视频预览镜像决策的单一真相源。
///
/// 业界默认预期：本地前置摄像头预览水平镜像（照镜子）；翻转到后摄或
/// 渲染远端参与者画面时不镜像。所有本地预览渲染必须消费本函数。
bool shouldMirrorLocalPreview({
  required bool isLocal,
  required CameraPosition cameraPosition,
}) => isLocal && cameraPosition == CameraPosition.front;

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
  MediaDeviceState build() {
    // 耳机拔出（becomingNoisy）防外放：立即切回听筒。路由归本 notifier
    // 收口，保证 UI 的 AudioOutput 状态与实际输出一致。
    final sub = ref
        .read(callAudioSessionGatewayProvider)
        .events
        .listen((event) {
          if (event == CallAudioSessionEvent.becameNoisy &&
              state.audioOutput == AudioOutput.speaker) {
            unawaited(setAudioOutput(AudioOutput.earpiece));
          }
        });
    ref.onDispose(sub.cancel);
    return const MediaDeviceState();
  }

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
