import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/application/content/media/video_preview_track_query.dart';
import 'package:quwoquan_app/cloud/remote/content/media/video_preview_track_remote.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import '../../../support/recording_app_telemetry_recorder.dart';

void main() {
  final telemetry = RecordingAppTelemetryRecorder();

  test('manifest 与 asset/version/track 绑定并按 descriptor 缓存', () async {
    var requestCount = 0;
    final resolver = _resolver();
    final descriptor = _descriptor(resolver);
    final query = RemoteVideoPreviewTrackQuery(
      httpClient: CloudHttpClient(
        client: MockClient((request) async {
          requestCount += 1;
          expect(request.headers['Accept'], 'application/json');
          return http.Response(jsonEncode(_manifestJson()), 200);
        }),
      ),
      mediaDeliveryResolver: resolver,
      telemetry: telemetry,
    );

    final first = await query.loadManifest(descriptor);
    final second = await query.loadManifest(descriptor);

    expect(identical(first, second), isTrue);
    expect(requestCount, 1);
    expect(first.assetId, 'media-canary-seek-125s');
    expect(first.assetVersion, 2);
    expect(first.trackVersion, 1);
    expect(first.sprites.single.reference.version, 2);
    expect(first.frameFor(const Duration(seconds: 9)).timeMs, 5000);
    expect(first.frameFor(const Duration(hours: 2)).timeMs, 10000);
    expect(telemetry.recorded.single.eventType, 'video_preview_track_load');
    expect(telemetry.recorded.single.extensions['result'], 'success');
  });

  test('落后于描述符的 manifest 版本合法（发布前封面命令会推进聚合版本）', () async {
    final resolver = _resolver();
    final descriptor = _descriptor(resolver);
    // 真实 UGC 时序：worker 在 v2 落 ready，随后 SelectManual/AutoCover 把聚合
    // 推进到 v3；发布投影下发 descriptor.assetVersion=3，而 manifest 仍记录
    // 处理落库时的 v2。轨道身份是 (assetId, trackVersion)，落后版本必须接受。
    final laggingQuery = RemoteVideoPreviewTrackQuery(
      httpClient: CloudHttpClient(
        client: MockClient(
          (_) async =>
              http.Response(jsonEncode(_manifestJson(assetVersion: 1)), 200),
        ),
      ),
      mediaDeliveryResolver: resolver,
      telemetry: telemetry,
    );
    final manifest = await laggingQuery.loadManifest(descriptor);
    expect(manifest.assetVersion, 1);
    expect(manifest.trackVersion, 1);
  });

  test('版本越界、track 失配或越界 crop 必须拒绝，不能将任意 sprite 交给 UI', () async {
    final resolver = _resolver();
    final descriptor = _descriptor(resolver);

    // manifest 版本领先描述符版本：处理结果不可能先于消费投影存在，拒绝。
    final aheadQuery = RemoteVideoPreviewTrackQuery(
      httpClient: CloudHttpClient(
        client: MockClient(
          (_) async =>
              http.Response(jsonEncode(_manifestJson(assetVersion: 9)), 200),
        ),
      ),
      mediaDeliveryResolver: resolver,
      telemetry: telemetry,
    );
    await expectLater(
      aheadQuery.loadManifest(descriptor),
      throwsA(isA<FormatException>()),
    );

    final trackMismatch = _manifestJson();
    trackMismatch['trackVersion'] = 2;
    final trackQuery = RemoteVideoPreviewTrackQuery(
      httpClient: CloudHttpClient(
        client: MockClient(
          (_) async => http.Response(jsonEncode(trackMismatch), 200),
        ),
      ),
      mediaDeliveryResolver: resolver,
      telemetry: telemetry,
    );
    await expectLater(
      trackQuery.loadManifest(descriptor),
      throwsA(isA<FormatException>()),
    );

    final invalidCrop = _manifestJson();
    final frames = invalidCrop['frames']! as List<Map<String, Object?>>;
    frames.first['x'] = 1000;
    final cropQuery = RemoteVideoPreviewTrackQuery(
      httpClient: CloudHttpClient(
        client: MockClient(
          (_) async => http.Response(jsonEncode(invalidCrop), 200),
        ),
      ),
      mediaDeliveryResolver: resolver,
      telemetry: telemetry,
    );
    await expectLater(
      cropQuery.loadManifest(descriptor),
      throwsA(isA<FormatException>()),
    );
  });
}

MediaDeliveryResolver _resolver() {
  return MediaDeliveryResolver(
    MediaEndpointConfig(
      avatarBaseUrl: 'https://avatar.example.test',
      imageBaseUrl: 'https://image.example.test',
      videoBaseUrl: 'https://video.example.test',
      attachmentBaseUrl: 'https://attachment.example.test',
    ),
  );
}

VideoPreviewTrackDescriptor _descriptor(MediaDeliveryResolver resolver) {
  return VideoPreviewTrackDescriptor(
    assetId: 'media-canary-seek-125s',
    assetVersion: 2,
    trackVersion: 1,
    manifestReference: resolver.resolve(
      'media/video/s/media-canary-seek-125s/v2/preview/manifest.json',
      kind: MediaDeliveryKind.video,
      assetId: 'media-canary-seek-125s',
      version: 2,
    ),
  );
}

Map<String, Object?> _manifestJson({int assetVersion = 2}) {
  const digest =
      'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
  return <String, Object?>{
    'schema': 'quwoquan.content.preview_track_manifest',
    'assetId': 'media-canary-seek-125s',
    'assetVersion': assetVersion,
    'trackVersion': 1,
    'processorProfile': 'media_canary_progressive_mp4',
    'accessPolicy': 'public',
    'frameIntervalMs': 5000,
    'sprites': <Map<String, Object?>>[
      <String, Object?>{
        'spriteId': 'sprite-000',
        'publicSliceKey':
            'media/video/s/media-canary-seek-125s/v$assetVersion/preview/sprite-000.webp',
        'sha256': digest,
        'width': 720,
        'height': 426,
      },
    ],
    'frames': <Map<String, Object?>>[
      for (var index = 0; index < 3; index += 1)
        <String, Object?>{
          'timeMs': index * 5000,
          'spriteId': 'sprite-000',
          'x': index * 240,
          'y': 0,
          'width': 240,
          'height': 426,
        },
    ],
  };
}
