import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:video_player_platform_interface/video_player_platform_interface.dart';

final class FakeVideoPlayerPlatform extends VideoPlayerPlatform {
  FakeVideoPlayerPlatform({
    this.duration = const Duration(seconds: 125),
    this.size = const Size(540, 960),
  });

  final Duration duration;
  final Size size;
  final List<Duration> seekTargets = <Duration>[];
  final List<DataSource> createdDataSources = <DataSource>[];
  final Set<String> failCreateForUris = <String>{};
  int playCount = 0;
  int pauseCount = 0;
  int disposeCount = 0;
  bool failNextSeek = false;
  bool failNextPositionReadback = false;
  Completer<void>? initializeCompleter;
  Completer<void>? disposeCompleter;
  Completer<void>? seekCompleter;
  int _nextPlayerId = 1;
  final Map<int, Duration> _positions = <int, Duration>{};

  @override
  Future<void> init() async {}

  @override
  Future<int?> create(DataSource dataSource) {
    return createWithOptions(
      VideoCreationOptions(
        dataSource: dataSource,
        viewType: VideoViewType.textureView,
      ),
    );
  }

  @override
  Future<int?> createWithOptions(VideoCreationOptions options) async {
    createdDataSources.add(options.dataSource);
    if (failCreateForUris.contains(options.dataSource.uri)) {
      throw StateError('injected create failure for ${options.dataSource.uri}');
    }
    final playerId = _nextPlayerId++;
    _positions[playerId] = Duration.zero;
    return playerId;
  }

  @override
  Stream<VideoEvent> videoEventsFor(int playerId) async* {
    final initialization = initializeCompleter;
    if (initialization != null) {
      await initialization.future;
    }
    yield VideoEvent(
      eventType: VideoEventType.initialized,
      duration: duration,
      size: size,
      rotationCorrection: 0,
    );
  }

  @override
  Future<void> dispose(int playerId) async {
    disposeCount += 1;
    final pending = disposeCompleter;
    if (pending != null) {
      await pending.future;
    }
    _positions.remove(playerId);
  }

  @override
  Future<void> play(int playerId) async {
    playCount += 1;
  }

  @override
  Future<void> pause(int playerId) async {
    pauseCount += 1;
  }

  @override
  Future<void> seekTo(int playerId, Duration position) async {
    seekTargets.add(position);
    if (failNextSeek) {
      failNextSeek = false;
      throw StateError('injected seek failure');
    }
    final pending = seekCompleter;
    if (pending != null) {
      await pending.future;
    }
    _positions[playerId] = position;
  }

  @override
  Future<Duration> getPosition(int playerId) async {
    if (failNextPositionReadback) {
      failNextPositionReadback = false;
      throw StateError('injected position readback failure');
    }
    return _positions[playerId] ?? Duration.zero;
  }

  @override
  Future<void> setLooping(int playerId, bool looping) async {}

  @override
  Future<void> setVolume(int playerId, double volume) async {}

  @override
  Future<void> setPlaybackSpeed(int playerId, double speed) async {}

  @override
  Future<void> setMixWithOthers(bool mixWithOthers) async {}

  @override
  Future<void> setAllowBackgroundPlayback(bool allowBackgroundPlayback) async {}

  @override
  Future<void> setWebOptions(
    int playerId,
    VideoPlayerWebOptions options,
  ) async {}

  @override
  Widget buildViewWithOptions(VideoViewOptions options) {
    return const SizedBox.shrink();
  }
}
