import 'dart:async';

import 'package:audio_session/audio_session.dart';
import 'package:flutter_riverpod/legacy.dart';
import 'package:just_audio/just_audio.dart';
import 'package:quwoquan_app/cloud/media/media_download_cache.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

/// Playback state for a single voice message.
class VoicePlaybackState {
  final String? activeMessageId;
  final bool isPlaying;
  final Duration position;
  final Duration duration;

  const VoicePlaybackState({
    this.activeMessageId,
    this.isPlaying = false,
    this.position = Duration.zero,
    this.duration = Duration.zero,
  });

  double get progress =>
      duration.inMilliseconds > 0
          ? position.inMilliseconds / duration.inMilliseconds
          : 0;

  VoicePlaybackState copyWith({
    String? activeMessageId,
    bool? isPlaying,
    Duration? position,
    Duration? duration,
  }) {
    return VoicePlaybackState(
      activeMessageId: activeMessageId ?? this.activeMessageId,
      isPlaying: isPlaying ?? this.isPlaying,
      position: position ?? this.position,
      duration: duration ?? this.duration,
    );
  }
}

/// Global singleton voice player: ensures only one voice message plays at a time.
class VoicePlayerManager extends StateNotifier<VoicePlaybackState> {
  VoicePlayerManager(this._downloadCache) : super(const VoicePlaybackState()) {
    _init();
  }

  final MediaDownloadCache _downloadCache;
  final AudioPlayer _player = AudioPlayer();
  StreamSubscription<PlayerState>? _playerStateSub;
  StreamSubscription<Duration>? _positionSub;
  StreamSubscription<Duration?>? _durationSub;

  Future<void> _init() async {
    final session = await AudioSession.instance;
    await session.configure(const AudioSessionConfiguration.speech());

    _playerStateSub = _player.playerStateStream.listen((playerState) {
      if (playerState.processingState == ProcessingState.completed) {
        state = state.copyWith(
          isPlaying: false,
          position: state.duration,
        );
      } else {
        state = state.copyWith(isPlaying: playerState.playing);
      }
    });

    _positionSub = _player.positionStream.listen((pos) {
      state = state.copyWith(position: pos);
    });

    _durationSub = _player.durationStream.listen((dur) {
      if (dur != null) {
        state = state.copyWith(duration: dur);
      }
    });
  }

  /// Play or resume a voice message. Stops any currently playing message.
  Future<void> play(String messageId, String url) async {
    if (state.activeMessageId == messageId && state.isPlaying) {
      await pause();
      return;
    }

    if (state.activeMessageId != messageId) {
      await _player.stop();
      state = const VoicePlaybackState();

      final localPath = await _downloadCache.getFile(url);
      final source = localPath != null
          ? AudioSource.file(localPath)
          : AudioSource.uri(Uri.parse(url));

      await _player.setAudioSource(source);
      state = state.copyWith(activeMessageId: messageId);
    }

    await _player.play();
  }

  Future<void> pause() async {
    await _player.pause();
  }

  Future<void> stop() async {
    await _player.stop();
    state = const VoicePlaybackState();
  }

  Future<void> seek(Duration position) async {
    await _player.seek(position);
  }

  @override
  void dispose() {
    _playerStateSub?.cancel();
    _positionSub?.cancel();
    _durationSub?.cancel();
    _player.dispose();
    super.dispose();
  }
}

/// Global voice player manager provider.
final voicePlayerManagerProvider =
    StateNotifierProvider<VoicePlayerManager, VoicePlaybackState>(
  (ref) {
    final cache = ref.watch(mediaDownloadCacheProvider);
    return VoicePlayerManager(cache);
  },
);
