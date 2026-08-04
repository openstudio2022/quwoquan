import 'dart:async';
import 'dart:collection';

import 'package:quwoquan_app/content/media/media_asset/application/video_preview_track_query.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_cloud_contracts/generated/content_preview_track_contracts.dart';

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
    final wire = PreviewTrackManifestWire.fromWire(decoded);
    // 预览轨道身份是 (assetId, trackVersion)。manifest.assetVersion 记录处理
    // 结果落库的聚合版本；发布前的封面命令会继续推进聚合版本，因此消费侧
    // 描述符的 assetVersion 允许领先，但 manifest 版本不得超过描述符版本。
    if (wire.assetId != descriptor.assetId ||
        wire.trackVersion != descriptor.trackVersion ||
        wire.assetVersion > descriptor.assetVersion) {
      throw const FormatException('preview manifest version binding mismatch');
    }
    if (wire.accessPolicy != PreviewTrackAccessPolicy.public) {
      throw const FormatException(
        'preview manifest access contract is invalid',
      );
    }
    final sprites = <String, VideoPreviewTrackSprite>{};
    for (final entry in wire.sprites) {
      if (sprites.containsKey(entry.spriteId)) {
        throw const FormatException(
          'preview manifest sprite identity is invalid',
        );
      }
      final reference = _mediaDeliveryResolver.resolve(
        entry.publicSliceKey,
        kind: MediaDeliveryKind.video,
        assetId: wire.assetId,
        version: wire.assetVersion,
        sha256: entry.sha256,
      );
      sprites[entry.spriteId] = VideoPreviewTrackSprite(
        spriteId: entry.spriteId,
        reference: reference,
        sha256: entry.sha256,
        width: entry.width,
        height: entry.height,
      );
    }
    final frames = <VideoPreviewTrackFrame>[];
    var previousTimeMs = -1;
    for (final entry in wire.frames) {
      final sprite = sprites[entry.spriteId];
      if (sprite == null ||
          entry.timeMs <= previousTimeMs ||
          entry.x + entry.width > sprite.width ||
          entry.y + entry.height > sprite.height) {
        throw const FormatException('preview manifest frame crop is invalid');
      }
      previousTimeMs = entry.timeMs;
      frames.add(
        VideoPreviewTrackFrame(
          timeMs: entry.timeMs,
          sprite: sprite,
          x: entry.x,
          y: entry.y,
          width: entry.width,
          height: entry.height,
        ),
      );
    }
    return VideoPreviewTrackManifest(
      assetId: wire.assetId,
      assetVersion: wire.assetVersion,
      trackVersion: wire.trackVersion,
      processorProfile: wire.processorProfile,
      accessPolicy: wire.accessPolicy.wireName,
      frameIntervalMs: wire.frameIntervalMs,
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
}
