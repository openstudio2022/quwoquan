import 'dart:collection';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/services.dart';
import 'package:video_thumbnail/video_thumbnail.dart';

class VideoFrameCandidate {
  const VideoFrameCandidate({required this.path, required this.timeMs});

  final String path;
  final int timeMs;
}

class VideoEditExportResult {
  const VideoEditExportResult({
    required this.videoPath,
    required this.coverPath,
    required this.durationMs,
  });

  final String videoPath;
  final String coverPath;
  final int durationMs;
}

class IosVideoEditingService {
  IosVideoEditingService();

  static const MethodChannel _channel = MethodChannel('quwoquan/video_editing');
  static const int _kMinDenseFrameCount = 24;
  static const int _kMaxCacheEntries = 18;
  static final LinkedHashMap<String, List<VideoFrameCandidate>> _frameCache =
      LinkedHashMap<String, List<VideoFrameCandidate>>();

  Future<List<VideoFrameCandidate>> extractFrames({
    required String videoPath,
    required int startMs,
    required int endMs,
    int frameCount = 12,
    int maxDimension = 360,
  }) async {
    final safeStartMs = math.max(startMs, 0);
    final safeEndMs = endMs <= safeStartMs ? safeStartMs + 1000 : endMs;
    final requestedFrameCount = frameCount.clamp(1, 48);
    final cacheKey = '$videoPath|$safeStartMs|$safeEndMs|$maxDimension';
    final cachedFrames = _frameCache.remove(cacheKey);
    if (cachedFrames != null && cachedFrames.isNotEmpty) {
      _frameCache[cacheKey] = cachedFrames;
      if (cachedFrames.length >= requestedFrameCount) {
        return _sampleFrames(cachedFrames, requestedFrameCount);
      }
    }
    final denseFrameCount = math.max(
      requestedFrameCount,
      math.max(cachedFrames?.length ?? 0, _kMinDenseFrameCount),
    );
    late final List<VideoFrameCandidate> denseFrames;
    if (Platform.isIOS) {
      try {
        final response = await _channel.invokeMethod<List<dynamic>>(
          'extractVideoFrames',
          <String, dynamic>{
            'sourcePath': videoPath,
            'startMs': safeStartMs,
            'endMs': safeEndMs,
            'frameCount': denseFrameCount,
            'maxDimension': maxDimension,
          },
        );
        denseFrames = (response ?? const <dynamic>[])
            .whereType<Map>()
            .map(
              (entry) => VideoFrameCandidate(
                path: (entry['path'] ?? '').toString(),
                timeMs: (entry['timeMs'] as num?)?.toInt() ?? 0,
              ),
            )
            .where((item) => item.path.trim().isNotEmpty)
            .toList(growable: false);
        _rememberCache(cacheKey, denseFrames);
        return _sampleFrames(denseFrames, requestedFrameCount);
      } on MissingPluginException {
        // Fall through for tests and unsupported hosts.
      } on PlatformException {
        // Fall through so preview frames still work on dev hosts.
      }
    }
    denseFrames = await _extractFramesFallback(
      videoPath: videoPath,
      startMs: safeStartMs,
      endMs: safeEndMs,
      frameCount: denseFrameCount,
      maxDimension: maxDimension,
    );
    _rememberCache(cacheKey, denseFrames);
    return _sampleFrames(denseFrames, requestedFrameCount);
  }

  Future<VideoEditExportResult> exportEdit({
    required String sourcePath,
    required int trimStartMs,
    required int trimEndMs,
    required bool muted,
    required int coverTimeMs,
  }) async {
    if (Platform.isIOS) {
      try {
        final response = await _channel.invokeMapMethod<String, dynamic>(
          'exportVideoEdit',
          <String, dynamic>{
            'sourcePath': sourcePath,
            'trimStartMs': trimStartMs,
            'trimEndMs': trimEndMs,
            'muted': muted,
            'coverTimeMs': coverTimeMs,
          },
        );
        if (response != null) {
          return VideoEditExportResult(
            videoPath: (response['videoPath'] ?? '').toString(),
            coverPath: (response['coverPath'] ?? '').toString(),
            durationMs: (response['durationMs'] as num?)?.toInt() ?? 0,
          );
        }
      } on MissingPluginException {
        // Ignore and fall back below.
      }
    }

    if (trimStartMs <= 0 && trimEndMs <= 0 && !muted) {
      final coverPath = await _generateCover(
        videoPath: sourcePath,
        timeMs: coverTimeMs,
      );
      return VideoEditExportResult(
        videoPath: sourcePath,
        coverPath: coverPath ?? '',
        durationMs: 0,
      );
    }

    throw UnsupportedError('当前环境不支持原生视频裁切与静音导出');
  }

  Future<List<VideoFrameCandidate>> _extractFramesFallback({
    required String videoPath,
    required int startMs,
    required int endMs,
    required int frameCount,
    required int maxDimension,
  }) async {
    final safeFrameCount = frameCount.clamp(1, 20);
    final safeEndMs = endMs <= startMs ? startMs + 1000 : endMs;
    final step = safeFrameCount == 1
        ? 0
        : ((safeEndMs - startMs) / (safeFrameCount - 1)).round();
    final frames = <VideoFrameCandidate>[];
    for (int index = 0; index < safeFrameCount; index++) {
      final timeMs = startMs + step * index;
      final path = await _generateCover(
        videoPath: videoPath,
        timeMs: timeMs,
        maxDimension: maxDimension,
      );
      if (path == null || path.trim().isEmpty) {
        continue;
      }
      frames.add(VideoFrameCandidate(path: path, timeMs: timeMs));
    }
    return frames;
  }

  List<VideoFrameCandidate> _sampleFrames(
    List<VideoFrameCandidate> frames,
    int requestedCount,
  ) {
    if (frames.isEmpty || requestedCount >= frames.length) {
      return frames;
    }
    if (requestedCount <= 1) {
      return <VideoFrameCandidate>[frames[frames.length ~/ 2]];
    }
    final sampled = <VideoFrameCandidate>[];
    for (int index = 0; index < requestedCount; index++) {
      final sourceIndex = ((frames.length - 1) * index / (requestedCount - 1))
          .round()
          .clamp(0, frames.length - 1);
      sampled.add(frames[sourceIndex]);
    }
    return sampled.toList(growable: false);
  }

  void _rememberCache(String key, List<VideoFrameCandidate> frames) {
    if (frames.isEmpty) {
      return;
    }
    _frameCache.remove(key);
    _frameCache[key] = frames;
    while (_frameCache.length > _kMaxCacheEntries) {
      _frameCache.remove(_frameCache.keys.first);
    }
  }

  Future<String?> _generateCover({
    required String videoPath,
    required int timeMs,
    int maxDimension = 360,
  }) {
    return VideoThumbnail.thumbnailFile(
      video: videoPath,
      timeMs: timeMs.clamp(0, 999999999),
      imageFormat: ImageFormat.JPEG,
      quality: 90,
      maxHeight: maxDimension,
    );
  }
}
