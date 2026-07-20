// Copyright 2013 The Flutter Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import 'package:pigeon/pigeon.dart';

@ConfigurePigeon(
  PigeonOptions(
    dartOut: 'lib/src/messages.g.dart',
    kotlinOut:
        'android/src/main/kotlin/io/flutter/plugins/videoplayer/Messages.kt',
    kotlinOptions: KotlinOptions(package: 'io.flutter.plugins.videoplayer'),
    copyrightHeader: 'pigeons/copyright.txt',
  ),
)
/// Pigeon equivalent of video_platform_interface's VideoFormat.
enum PlatformVideoFormat { dash, hls, ss }

/// Pigeon equivalent of Player's playback state.
/// https://developer.android.com/media/media3/exoplayer/listening-to-player-events#playback-state
enum PlatformPlaybackState { idle, buffering, ready, ended, unknown }

sealed class PlatformVideoEvent {}

/// Sent when the video is initialized and ready to play.
class InitializationEvent extends PlatformVideoEvent {
  /// The video duration in milliseconds.
  late final int duration;

  /// The width of the video in pixels.
  late final int width;

  /// The height of the video in pixels.
  late final int height;

  /// The rotation that should be applied during playback.
  late final int rotationCorrection;
}

/// Sent when the video state changes.
///
/// Corresponds to ExoPlayer's onPlaybackStateChanged.
class PlaybackStateChangeEvent extends PlatformVideoEvent {
  late final PlatformPlaybackState state;
}

/// Sent when the video starts or stops playing.
///
/// Corresponds to ExoPlayer's onIsPlayingChanged.
class IsPlayingStateEvent extends PlatformVideoEvent {
  late final bool isPlaying;
}

/// Sent when audio tracks change.
///
/// This includes when the selected audio track changes after calling selectAudioTrack.
/// Corresponds to ExoPlayer's onTracksChanged.
class AudioTrackChangedEvent extends PlatformVideoEvent {
  /// The ID of the newly selected audio track, if any.
  late final String? selectedTrackId;
}

/// Sent when ExoPlayer has rendered the first video frame for this player.
///
/// This is a real surface/first-frame signal and must not be confused with
/// controller initialize / READY state transitions.
class RenderedFirstFrameEvent extends PlatformVideoEvent {
  /// Native elapsed time from prepare to the rendered frame.
  late final int ttffMs;
}

/// Sent when a seek request has produced a newly rendered frame near the target.
///
/// The seek command Future completing is never enough; settle requires native
/// render evidence after DISCONTINUITY_REASON_SEEK.
class SeekSettledEvent extends PlatformVideoEvent {
  /// Target position that was requested, in milliseconds.
  late final int targetPositionMs;

  /// Observed playback position when the settle frame was rendered, in milliseconds.
  late final int settledPositionMs;

  /// Native elapsed time from the seek request to the settle frame.
  late final int settleMs;
}

/// Reports a batch of video frames dropped by the active renderer.
class DroppedVideoFramesEvent extends PlatformVideoEvent {
  late final int droppedFrames;
  late final int elapsedMs;
}

/// Reports one audio output underrun from the active renderer.
class AudioUnderrunEvent extends PlatformVideoEvent {
  late final int bufferSize;
  late final int bufferSizeMs;
  late final int elapsedSinceLastFeedMs;
}

/// Reports frame-processing samples used as the dropped-frame denominator.
class VideoFrameProcessingEvent extends PlatformVideoEvent {
  late final int processedFrames;
}

/// Reports the actual broad-compatibility renderer configuration.
///
/// It deliberately carries no brand, model, or other device fingerprint.
class PlaybackDiagnosticsEvent extends PlatformVideoEvent {
  late final String rendererMode;
  late final String decoderQueueMode;
  late final bool decoderFallbackEnabled;
}

/// Information passed to the platform view creation.
class PlatformVideoViewCreationParams {
  const PlatformVideoViewCreationParams({required this.playerId});

  final int playerId;
}

class CreationOptions {
  CreationOptions({required this.uri, required this.httpHeaders});
  String uri;
  PlatformVideoFormat? formatHint;
  Map<String, String> httpHeaders;
  String? userAgent;
}

class TexturePlayerIds {
  TexturePlayerIds({required this.playerId, required this.textureId});

  final int playerId;
  final int textureId;
}

class PlaybackState {
  PlaybackState({required this.playPosition, required this.bufferPosition});

  /// The current playback position, in milliseconds.
  final int playPosition;

  /// The current buffer position, in milliseconds.
  final int bufferPosition;
}

/// Represents an audio track in a video.
class AudioTrackMessage {
  AudioTrackMessage({
    required this.id,
    required this.label,
    required this.language,
    required this.isSelected,
    this.bitrate,
    this.sampleRate,
    this.channelCount,
    this.codec,
  });

  String id;
  String label;
  String language;
  bool isSelected;
  int? bitrate;
  int? sampleRate;
  int? channelCount;
  String? codec;
}

/// Raw audio track data from ExoPlayer Format objects.
class ExoPlayerAudioTrackData {
  ExoPlayerAudioTrackData({
    required this.groupIndex,
    required this.trackIndex,
    this.label,
    this.language,
    required this.isSelected,
    this.bitrate,
    this.sampleRate,
    this.channelCount,
    this.codec,
  });

  int groupIndex;
  int trackIndex;
  String? label;
  String? language;
  bool isSelected;
  int? bitrate;
  int? sampleRate;
  int? channelCount;
  String? codec;
}

/// Container for raw audio track data from Android ExoPlayer.
class NativeAudioTrackData {
  NativeAudioTrackData({this.exoPlayerTracks});

  /// ExoPlayer-based tracks
  List<ExoPlayerAudioTrackData>? exoPlayerTracks;
}

@HostApi()
abstract class AndroidVideoPlayerApi {
  void initialize();
  // Creates a new player using a platform view for rendering and returns its
  // ID.
  int createForPlatformView(CreationOptions options);
  // Creates a new player using a texture for rendering and returns its IDs.
  TexturePlayerIds createForTextureView(CreationOptions options);
  void dispose(int playerId);
  void setMixWithOthers(bool mixWithOthers);
  String getLookupKeyForAsset(String asset, String? packageName);
}

@HostApi()
abstract class VideoPlayerInstanceApi {
  /// Sets whether to automatically loop playback of the video.
  void setLooping(bool looping);

  /// Sets the volume, with 0.0 being muted and 1.0 being full volume.
  void setVolume(double volume);

  /// Sets the playback speed as a multiple of normal speed.
  void setPlaybackSpeed(double speed);

  /// Begins playback if the video is not currently playing.
  void play();

  /// Pauses playback if the video is currently playing.
  void pause();

  /// Seeks to the given playback position, in milliseconds.
  void seekTo(int position);

  /// Returns the current playback position, in milliseconds.
  int getCurrentPosition();

  /// Returns the current buffer position, in milliseconds.
  int getBufferedPosition();

  /// Gets the available audio tracks for the video.
  NativeAudioTrackData getAudioTracks();

  /// Selects which audio track is chosen for playback from its [groupIndex] and [trackIndex]
  void selectAudioTrack(int groupIndex, int trackIndex);
}

@EventChannelApi()
abstract class VideoEventChannel {
  PlatformVideoEvent videoEvents();
}
