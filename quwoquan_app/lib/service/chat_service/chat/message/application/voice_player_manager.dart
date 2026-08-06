import 'dart:async';

import 'package:audio_session/audio_session.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:just_audio/just_audio.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/observability/trackers/voice_message_observability.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/voice_message_interaction.dart';

/// Playback state for a single voice message.
class VoicePlaybackState {
  final String? activeMessageId;
  final bool isPlaying;
  final Duration position;
  final Duration duration;
  final String? failedMessageId;
  final String? error;

  const VoicePlaybackState({
    this.activeMessageId,
    this.isPlaying = false,
    this.position = Duration.zero,
    this.duration = Duration.zero,
    this.failedMessageId,
    this.error,
  });

  double get progress => duration.inMilliseconds > 0
      ? position.inMilliseconds / duration.inMilliseconds
      : 0;

  VoicePlaybackState copyWith({
    String? activeMessageId,
    bool? isPlaying,
    Duration? position,
    Duration? duration,
    String? failedMessageId,
    String? error,
    bool clearFailure = false,
  }) {
    return VoicePlaybackState(
      activeMessageId: activeMessageId ?? this.activeMessageId,
      isPlaying: isPlaying ?? this.isPlaying,
      position: position ?? this.position,
      duration: duration ?? this.duration,
      failedMessageId: clearFailure
          ? null
          : failedMessageId ?? this.failedMessageId,
      error: clearFailure ? null : error ?? this.error,
    );
  }
}

abstract class VoicePlaybackBackend {
  Stream<PlayerState> get playerStateStream;
  Stream<Duration> get positionStream;
  Stream<Duration?> get durationStream;

  Future<void> configure();
  Future<void> setSource(AudioSource source);
  Future<void> play();
  Future<void> pause();
  Future<void> stop();
  Future<void> seek(Duration position);
  Future<void> dispose();
}

class JustAudioVoicePlaybackBackend implements VoicePlaybackBackend {
  JustAudioVoicePlaybackBackend({AudioPlayer? player})
    : _player = player ?? AudioPlayer();

  final AudioPlayer _player;

  @override
  Stream<PlayerState> get playerStateStream => _player.playerStateStream;

  @override
  Stream<Duration> get positionStream => _player.positionStream;

  @override
  Stream<Duration?> get durationStream => _player.durationStream;

  @override
  Future<void> configure() async {
    final session = await AudioSession.instance;
    await session.configure(const AudioSessionConfiguration.speech());
  }

  @override
  Future<void> setSource(AudioSource source) => _player.setAudioSource(source);

  @override
  Future<void> play() => _player.play();

  @override
  Future<void> pause() => _player.pause();

  @override
  Future<void> stop() => _player.stop();

  @override
  Future<void> seek(Duration position) => _player.seek(position);

  @override
  Future<void> dispose() => _player.dispose();
}

final voicePlaybackBackendProvider = Provider<VoicePlaybackBackend>((ref) {
  return JustAudioVoicePlaybackBackend();
});

class VoicePlaybackSourceResult {
  const VoicePlaybackSourceResult({
    required this.source,
    required this.cacheHit,
  });

  final AudioSource source;
  final bool cacheHit;
}

final voicePlaybackSourceResolverProvider =
    Provider<Future<VoicePlaybackSourceResult> Function(String url)>((ref) {
      final downloadCache = ref.read(mediaDownloadCacheProvider);
      return (url) async {
        final cacheHit = downloadCache.isCached(url);
        final localPath = await downloadCache.getFile(url);
        return VoicePlaybackSourceResult(
          source: localPath != null
              ? AudioSource.file(localPath)
              : AudioSource.uri(Uri.parse(url)),
          cacheHit: cacheHit,
        );
      };
    });

/// Global singleton voice player: ensures only one voice message plays at a time.
class VoicePlayerManager extends Notifier<VoicePlaybackState>
    implements VoicePlaybackControl {
  StreamSubscription<PlayerState>? _playerStateSub;
  StreamSubscription<Duration>? _positionSub;
  StreamSubscription<Duration?>? _durationSub;
  bool _scheduledInit = false;

  Future<VoicePlaybackSourceResult> Function(String url) get _sourceResolver =>
      ref.read(voicePlaybackSourceResolverProvider);
  VoicePlaybackBackend get _backend => ref.read(voicePlaybackBackendProvider);
  VoiceMessageObservability get _observability =>
      ref.read(voiceMessageObservabilityProvider);

  @override
  VoicePlaybackState build() {
    final backend = _backend;
    ref.onDispose(() {
      _playerStateSub?.cancel();
      _positionSub?.cancel();
      _durationSub?.cancel();
      backend.dispose();
    });
    if (!_scheduledInit) {
      _scheduledInit = true;
      Future<void>.microtask(_init);
    }
    return const VoicePlaybackState();
  }

  Future<void> _init() async {
    await _backend.configure();

    _playerStateSub = _backend.playerStateStream.listen((playerState) {
      if (playerState.processingState == ProcessingState.completed) {
        state = state.copyWith(isPlaying: false, position: state.duration);
      } else {
        state = state.copyWith(isPlaying: playerState.playing);
      }
    });

    _positionSub = _backend.positionStream.listen((pos) {
      state = state.copyWith(position: pos);
    });

    _durationSub = _backend.durationStream.listen((dur) {
      if (dur != null) {
        state = state.copyWith(duration: dur);
      }
    });
  }

  /// Play or resume a voice message. Stops any currently playing message.
  Future<void> play(String messageId, String url) async {
    final resolvedUrl = url.trim();
    if (resolvedUrl.isEmpty) {
      _observability.trackAction(
        eventName: VoiceMessageEventNames.playbackFailed,
        messageId: messageId,
        failureKind: 'empty_url',
      );
      state = state.copyWith(
        activeMessageId: messageId,
        isPlaying: false,
        failedMessageId: messageId,
        error: ChatText.chatVoicePlayUnavailable,
      );
      return;
    }
    if (state.activeMessageId == messageId && state.isPlaying) {
      await pause();
      return;
    }

    try {
      if (state.activeMessageId != messageId) {
        await _backend.stop();
        state = const VoicePlaybackState();

        final sourceResult = await _sourceResolver(resolvedUrl);

        await _backend.setSource(sourceResult.source);
        state = state.copyWith(activeMessageId: messageId, clearFailure: true);
        _observability.trackAction(
          eventName: VoiceMessageEventNames.playbackStarted,
          messageId: messageId,
          cacheHit: sourceResult.cacheHit,
        );
      }

      await _backend.play();
    } catch (error) {
      await _backend.stop();
      _observability.trackAction(
        eventName: VoiceMessageEventNames.playbackFailed,
        messageId: messageId,
        failureKind: error.runtimeType.toString(),
      );
      state = VoicePlaybackState(
        activeMessageId: messageId,
        failedMessageId: messageId,
        error: ChatText.chatVoicePlayUnavailable,
      );
    }
  }

  Future<void> pause() async {
    await _backend.pause();
    _observability.trackAction(
      eventName: VoiceMessageEventNames.playbackPaused,
      messageId: state.activeMessageId,
    );
  }

  @override
  Future<void> stop() async {
    final messageId = state.activeMessageId;
    await _backend.stop();
    state = const VoicePlaybackState();
    _observability.trackAction(
      eventName: VoiceMessageEventNames.playbackStopped,
      messageId: messageId,
    );
  }

  Future<void> seek(Duration position) async {
    await _backend.seek(position);
  }
}

/// Global voice player manager provider.
final voicePlayerManagerProvider =
    NotifierProvider<VoicePlayerManager, VoicePlaybackState>(
      VoicePlayerManager.new,
    );
