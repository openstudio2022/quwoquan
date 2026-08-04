import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/cloud/media/media_download_cache.dart';
import 'package:quwoquan_app/core/platform/video_player_controller_factory.dart';
import 'package:quwoquan_app/core/services/cache/cache_telemetry_sink.dart';
import 'package:video_player/video_player.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('MediaDownloadCache', () {
    test(
      'uses stable sha1 key and discovers existing file after restart',
      () async {
        final tempDir = await Directory.systemTemp.createTemp(
          'qwq_media_cache_test_',
        );
        addTearDown(() async {
          if (tempDir.existsSync()) {
            await tempDir.delete(recursive: true);
          }
        });
        var requestCount = 0;
        const url = 'https://cdn.example.com/video/post_1/preview.mp4';
        final expectedKey = sha1.convert(utf8.encode(url)).toString();
        final firstCache = MediaDownloadCache(
          client: MockClient((request) async {
            requestCount += 1;
            return http.Response.bytes(<int>[1, 2, 3, 4], 200);
          }),
          cacheDirectoryPathProvider: () async => tempDir.path,
          telemetrySink: const NoopCacheTelemetrySink(),
        );

        final firstPath = await firstCache.getFile(url);

        expect(firstPath, isNotNull);
        expect(firstPath, endsWith('$expectedKey.mp4'));
        expect(requestCount, 1);

        final restartedCache = MediaDownloadCache(
          client: MockClient((request) async {
            requestCount += 1;
            return http.Response.bytes(<int>[], 500);
          }),
          cacheDirectoryPathProvider: () async => tempDir.path,
          telemetrySink: const NoopCacheTelemetrySink(),
        );

        final restartedPath = await restartedCache.getCachedFilePath(url);

        expect(restartedPath, firstPath);
        expect(requestCount, 1);
      },
    );

    test('clear reports bytes and files through telemetry', () async {
      final tempDir = await Directory.systemTemp.createTemp(
        'qwq_media_cache_clear_test_',
      );
      addTearDown(() async {
        if (tempDir.existsSync()) {
          await tempDir.delete(recursive: true);
        }
      });
      final telemetry = _RecordingCacheTelemetrySink();
      final cache = MediaDownloadCache(
        client: MockClient((request) async {
          return http.Response.bytes(<int>[9, 8, 7], 200);
        }),
        cacheDirectoryPathProvider: () async => tempDir.path,
        telemetrySink: telemetry,
      );

      await cache.getFile('https://cdn.example.com/image/post_1/cover.jpg');
      await cache.clear();

      expect(cache.cachedFileCount, 0);
      expect(cache.currentCacheSizeBytes, 0);
      expect(telemetry.events.single.name, 'resource.bytes_cleared');
      expect(telemetry.events.single.attributes['bytes'], 3);
      expect(telemetry.events.single.attributes['files'], 1);
    });

    test('coalesces duplicate downloads for the same url', () async {
      final tempDir = await Directory.systemTemp.createTemp(
        'qwq_media_cache_dedupe_test_',
      );
      addTearDown(() async {
        if (tempDir.existsSync()) {
          await tempDir.delete(recursive: true);
        }
      });
      var requestCount = 0;
      final responseGate = Completer<void>();
      final cache = MediaDownloadCache(
        client: MockClient((request) async {
          requestCount += 1;
          await responseGate.future;
          return http.Response.bytes(<int>[1, 1, 2, 3], 200);
        }),
        cacheDirectoryPathProvider: () async => tempDir.path,
        telemetrySink: const NoopCacheTelemetrySink(),
      );
      const url = 'https://cdn.example.com/video/post_1/clip.mp4';

      final first = cache.getFile(url);
      final second = cache.getFile(url);
      await Future<void>.delayed(const Duration(milliseconds: 10));
      expect(cache.inflightDownloadCount, 1);
      responseGate.complete();

      final paths = await Future.wait(<Future<String?>>[first, second]);
      expect(paths[0], isNotNull);
      expect(paths[1], paths[0]);
      expect(requestCount, 1);
      expect(cache.inflightDownloadCount, 0);
    });

    test(
      'can cancel queued prefetch downloads without cancelling active getFile',
      () async {
        final tempDir = await Directory.systemTemp.createTemp(
          'qwq_media_cache_cancel_test_',
        );
        addTearDown(() async {
          if (tempDir.existsSync()) {
            await tempDir.delete(recursive: true);
          }
        });
        final responseGate = Completer<void>();
        final cache = MediaDownloadCache(
          maxConcurrentDownloads: 1,
          client: MockClient((request) async {
            await responseGate.future;
            return http.Response.bytes(<int>[4, 5, 6], 200);
          }),
          cacheDirectoryPathProvider: () async => tempDir.path,
          telemetrySink: const NoopCacheTelemetrySink(),
        );

        final active = cache.getFile(
          'https://cdn.example.com/video/active.mp4',
        );
        await Future<void>.delayed(const Duration(milliseconds: 10));
        cache.prefetch('https://cdn.example.com/video/prefetch.mp4');
        await Future<void>.delayed(const Duration(milliseconds: 10));
        expect(cache.activeDownloadCount, 1);
        expect(cache.queuedDownloadCount, 1);

        cache.cancelQueuedPrefetches();
        expect(cache.activeDownloadCount, 1);
        expect(cache.queuedDownloadCount, 0);
        expect(cache.inflightDownloadCount, 1);
        responseGate.complete();

        expect(await active, isNotNull);
        expect(cache.inflightDownloadCount, 0);
      },
    );

    test('local video source is resolved by platform factory boundary', () {
      final controllerHandle = AppVideoPlayerControllerFactory.localFilePath(
        '/tmp/qwq_cached_video.mp4',
      );
      addTearDown(controllerHandle.controller.dispose);

      expect(controllerHandle.controller.dataSourceType, DataSourceType.file);
    });
  });
}

class _RecordingCacheTelemetrySink implements CacheTelemetrySink {
  final events = <_TelemetryEvent>[];

  @override
  void record(String eventName, Map<String, Object?> attributes) {
    events.add(_TelemetryEvent(eventName, attributes));
  }
}

class _TelemetryEvent {
  const _TelemetryEvent(this.name, this.attributes);

  final String name;
  final Map<String, Object?> attributes;
}
