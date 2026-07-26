import 'dart:async';
import 'dart:collection';

import 'package:quwoquan_app/application/content/media/video_preview_track_query.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';

final class RemoteVideoPreviewTrackQuery implements VideoPreviewTrackQuery {
  RemoteVideoPreviewTrackQuery({
    required CloudHttpClient httpClient,
    required MediaDeliveryResolver mediaDeliveryResolver,
    required AppTelemetryRecorder telemetry,
  }) : this._(httpClient, mediaDeliveryResolver, telemetry);

  RemoteVideoPreviewTrackQuery._(
    this._httpClient,
    this._mediaDeliveryResolver,
    this._telemetry,
  );

  final CloudHttpClient _httpClient;
  final MediaDeliveryResolver _mediaDeliveryResolver;
  final AppTelemetryRecorder _telemetry;
  final LinkedHashMap<String, Future<VideoPreviewTrackManifest>>
  _manifestCache = LinkedHashMap<String, Future<VideoPreviewTrackManifest>>();

  @override
  Future<VideoPreviewTrackManifest> loadManifest(
    VideoPreviewTrackDescriptor descriptor,
  ) {
    final key =
        '${descriptor.assetId}|${descriptor.assetVersion}|'
        '${descriptor.trackVersion}|${descriptor.manifestReference.cacheIdentity}';
    final cached = _manifestCache.remove(key);
    if (cached != null) {
      _manifestCache[key] = cached;
      return cached;
    }
    final pending = _fetchManifest(descriptor);
    _manifestCache[key] = pending;
    while (_manifestCache.length > 8) {
      _manifestCache.remove(_manifestCache.keys.first);
    }
    return pending.catchError((Object error) {
      _manifestCache.remove(key);
      throw error;
    });
  }

  Future<VideoPreviewTrackManifest> _fetchManifest(
    VideoPreviewTrackDescriptor descriptor,
  ) async {
    final stopwatch = Stopwatch()..start();
    try {
      final manifest = await _decodeManifest(descriptor);
      unawaited(_recordLoadOutcome('success', stopwatch.elapsedMilliseconds));
      return manifest;
    } catch (error) {
      unawaited(
        _recordLoadOutcome(
          'failure',
          stopwatch.elapsedMilliseconds,
          failReasonCode: error.runtimeType.toString(),
        ),
      );
      rethrow;
    }
  }

  Future<VideoPreviewTrackManifest> _decodeManifest(
    VideoPreviewTrackDescriptor descriptor,
  ) async {
    final decoded = await _httpClient.getJson(
      descriptor.manifestReference.deliveryUri,
      headers: const <String, String>{'Accept': 'application/json'},
    );
    final root = _object(decoded, 'preview manifest');
    if (_string(root, 'schema') != 'quwoquan.content.preview_track_manifest') {
      throw const FormatException('preview manifest schema is invalid');
    }
    final assetId = _string(root, 'assetId');
    final assetVersion = _integer(root, 'assetVersion');
    final trackVersion = _integer(root, 'trackVersion');
    // 预览轨道身份是 (assetId, trackVersion)。manifest.assetVersion 记录处理
    // 结果落库的聚合版本；发布前的封面命令会继续推进聚合版本，因此消费侧
    // 描述符的 assetVersion 允许领先，但 manifest 版本不得超过描述符版本。
    if (assetId != descriptor.assetId ||
        trackVersion != descriptor.trackVersion ||
        assetVersion < 1 ||
        assetVersion > descriptor.assetVersion) {
      throw const FormatException('preview manifest version binding mismatch');
    }
    final processorProfile = _string(root, 'processorProfile');
    final accessPolicy = _string(root, 'accessPolicy');
    if (processorProfile.isEmpty || accessPolicy != 'public') {
      throw const FormatException(
        'preview manifest access contract is invalid',
      );
    }
    final frameIntervalMs = _integer(root, 'frameIntervalMs');
    if (frameIntervalMs < 1000 || frameIntervalMs > 30000) {
      throw const FormatException('preview manifest frame interval is invalid');
    }
    final spriteEntries = _objects(root, 'sprites');
    if (spriteEntries.isEmpty || spriteEntries.length > 64) {
      throw const FormatException('preview manifest sprites are invalid');
    }
    final sprites = <String, VideoPreviewTrackSprite>{};
    for (final entry in spriteEntries) {
      final spriteId = _string(entry, 'spriteId');
      final sha256 = _string(entry, 'sha256');
      final width = _positiveInteger(entry, 'width');
      final height = _positiveInteger(entry, 'height');
      final publicSliceKey = _string(entry, 'publicSliceKey');
      if (spriteId.isEmpty ||
          sprites.containsKey(spriteId) ||
          !RegExp(r'^sha256:[0-9a-f]{64}$').hasMatch(sha256)) {
        throw const FormatException(
          'preview manifest sprite identity is invalid',
        );
      }
      final reference = _mediaDeliveryResolver.resolve(
        publicSliceKey,
        kind: MediaDeliveryKind.video,
        assetId: assetId,
        version: assetVersion,
        sha256: sha256,
      );
      sprites[spriteId] = VideoPreviewTrackSprite(
        spriteId: spriteId,
        reference: reference,
        sha256: sha256,
        width: width,
        height: height,
      );
    }
    final frameEntries = _objects(root, 'frames');
    if (frameEntries.isEmpty || frameEntries.length > 1000) {
      throw const FormatException('preview manifest frames are invalid');
    }
    final frames = <VideoPreviewTrackFrame>[];
    var previousTimeMs = -1;
    for (final entry in frameEntries) {
      final timeMs = _integer(entry, 'timeMs');
      final sprite = sprites[_string(entry, 'spriteId')];
      final x = _integer(entry, 'x');
      final y = _integer(entry, 'y');
      final width = _positiveInteger(entry, 'width');
      final height = _positiveInteger(entry, 'height');
      if (sprite == null ||
          timeMs < 0 ||
          timeMs > 3600000 ||
          timeMs <= previousTimeMs ||
          x < 0 ||
          y < 0 ||
          x + width > sprite.width ||
          y + height > sprite.height) {
        throw const FormatException('preview manifest frame crop is invalid');
      }
      previousTimeMs = timeMs;
      frames.add(
        VideoPreviewTrackFrame(
          timeMs: timeMs,
          sprite: sprite,
          x: x,
          y: y,
          width: width,
          height: height,
        ),
      );
    }
    return VideoPreviewTrackManifest(
      assetId: assetId,
      assetVersion: assetVersion,
      trackVersion: trackVersion,
      processorProfile: processorProfile,
      accessPolicy: accessPolicy,
      frameIntervalMs: frameIntervalMs,
      sprites: sprites.values.toList(growable: false),
      frames: frames,
    );
  }

  Future<void> _recordLoadOutcome(
    String result,
    int durationMs, {
    String? failReasonCode,
  }) async {
    await _telemetry.record(
      AppTelemetryPayload.videoPreviewTrackLoad(
        result: result,
        durationMs: durationMs,
        failReasonCode: failReasonCode,
      ),
    );
  }

  Map<String, Object?> _object(Object? value, String label) {
    if (value is! Map) {
      throw FormatException('$label must be an object');
    }
    return value.map(
      (key, child) => MapEntry(key.toString(), child as Object?),
    );
  }

  List<Map<String, Object?>> _objects(Map<String, Object?> source, String key) {
    final raw = source[key];
    if (raw is! List) {
      throw FormatException('preview manifest $key must be an array');
    }
    return raw
        .map((entry) => _object(entry, 'preview manifest $key entry'))
        .toList(growable: false);
  }

  String _string(Map<String, Object?> source, String key) {
    final value = source[key];
    if (value is! String || value.trim().isEmpty) {
      throw FormatException('preview manifest $key must be a non-empty string');
    }
    return value.trim();
  }

  int _integer(Map<String, Object?> source, String key) {
    final value = source[key];
    if (value is! num || value.isNaN || value.isInfinite) {
      throw FormatException('preview manifest $key must be an integer');
    }
    final integer = value.toInt();
    if (integer.toDouble() != value.toDouble()) {
      throw FormatException('preview manifest $key must be an integer');
    }
    return integer;
  }

  int _positiveInteger(Map<String, Object?> source, String key) {
    final value = _integer(source, key);
    if (value <= 0) {
      throw FormatException('preview manifest $key must be positive');
    }
    return value;
  }
}
