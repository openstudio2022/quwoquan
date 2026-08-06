import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/transport/media/media_candidate_failure.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/media_playback_failure.dart';
import 'package:quwoquan_app/runtime/observability/trackers/feed_performance_observability.dart';

import '../../../../support/runtime/observability/recording_app_telemetry_recorder.dart';

/// 任务 B · FeedPerformanceObservability 单元测试。
///
/// 直接覆盖 façade -> typed Reporter，防止性能事实再次被
/// dynamic analytics/local-only denylist 丢弃。
void main() {
  late RecordingAppTelemetryRecorder ops;
  late FeedPerformanceObservability observability;

  setUp(() {
    ops = RecordingAppTelemetryRecorder();
    observability = FeedPerformanceObservability(telemetry: ops);
  });

  List<RecordedAppTelemetry> eventsNamed(String name) {
    return ops.recorded
        .where(
          (event) =>
              event.action == name || event.extensions['operationId'] == name,
        )
        .toList();
  }

  group('首屏 TTI', () {
    test('请求 -> 首帧 上报一次首屏可交互耗时', () async {
      observability.markFeedRequested('recommend');
      observability.markFirstContentReady('recommend', itemCount: 8);

      final tti = eventsNamed(FeedPerformanceMetricNames.firstScreenTtiMs);
      expect(tti, hasLength(1));
      expect(tti.first.eventType, equals('performance_sample'));
      expect(tti.first.extensions.containsKey('channelId'), isFalse);
      expect(tti.first.extensions['durationMs'], isA<int>());
      expect((tti.first.extensions['durationMs']! as int) >= 0, isTrue);
    });

    test('未先 markFeedRequested 时首帧不上报（无计时起点）', () async {
      observability.markFirstContentReady('recommend', itemCount: 3);

      expect(eventsNamed(FeedPerformanceMetricNames.firstScreenTtiMs), isEmpty);
    });

    test('同一 channel 重复首帧只上报一次', () async {
      observability.markFeedRequested('recommend');
      observability.markFirstContentReady('recommend', itemCount: 8);
      observability.markFeedRequested('recommend');
      observability.markFirstContentReady('recommend', itemCount: 12);

      expect(
        eventsNamed(FeedPerformanceMetricNames.firstScreenTtiMs),
        hasLength(1),
      );
    });

    test('resetChannel 后可重新计时并再次上报', () async {
      observability.markFeedRequested('recommend');
      observability.markFirstContentReady('recommend', itemCount: 8);
      observability.resetChannel('recommend');
      observability.markFeedRequested('recommend');
      observability.markFirstContentReady('recommend', itemCount: 4);

      expect(
        eventsNamed(FeedPerformanceMetricNames.firstScreenTtiMs),
        hasLength(2),
      );
    });

    test('空白 channelId 被忽略', () async {
      observability.markFeedRequested('   ');
      observability.markFirstContentReady('   ', itemCount: 8);

      expect(eventsNamed(FeedPerformanceMetricNames.firstScreenTtiMs), isEmpty);
    });
  });

  group('加载失败归因', () {
    test('同一 channel::errorCode 去重，不同 errorCode 各上报一次', () async {
      observability.recordFeedLoadFailed(
        channelId: 'recommend',
        errorCode: 'CONTENT.DEPENDENCY.UNAVAILABLE',
        operation: 'queryFeed',
        surface: 'home_feed',
        hasCache: false,
      );
      observability.recordFeedLoadFailed(
        channelId: 'recommend',
        errorCode: 'CONTENT.DEPENDENCY.UNAVAILABLE',
        operation: 'queryFeed',
        surface: 'home_feed',
        hasCache: false,
      );
      observability.recordFeedLoadFailed(
        channelId: 'recommend',
        errorCode: 'GATEWAY.DEPENDENCY.TIMEOUT',
        operation: 'queryFeed',
        surface: 'home_feed',
        hasCache: false,
      );

      final failures = ops.recorded
          .where((event) => event.eventType == 'operation_result')
          .toList();
      expect(failures, hasLength(2));
      expect(
        failures.map((event) => event.extensions['failReasonCode']).toSet(),
        equals(<String>{
          'CONTENT.DEPENDENCY.UNAVAILABLE',
          'GATEWAY.DEPENDENCY.TIMEOUT',
        }),
      );
      expect(failures.first.extensions['operationId'], equals('queryFeed'));
      expect(failures.first.extensions['surfaceId'], equals('home_feed'));
      expect(failures.first.extensions['hasCache'], isFalse);
      expect(failures.first.extensions['result'], equals('failed'));
    });

    test('首屏成功后复位失败去重，相同 errorCode 可再次上报', () async {
      observability.recordFeedLoadFailed(
        channelId: 'recommend',
        errorCode: 'CONTENT.DEPENDENCY.UNAVAILABLE',
        operation: 'queryFeed',
        surface: 'home_feed',
        hasCache: false,
      );
      observability.markFeedRequested('recommend');
      observability.markFirstContentReady('recommend', itemCount: 6);
      observability.recordFeedLoadFailed(
        channelId: 'recommend',
        errorCode: 'CONTENT.DEPENDENCY.UNAVAILABLE',
        operation: 'queryFeed',
        surface: 'home_feed',
        hasCache: false,
      );

      expect(
        ops.recorded.where((event) => event.eventType == 'operation_result'),
        hasLength(2),
      );
    });

    test('空 errorCode 归一化为 canonical unknown error', () async {
      observability.recordFeedLoadFailed(
        channelId: 'recommend',
        errorCode: '   ',
        operation: 'queryFeed',
        surface: 'home_feed',
        hasCache: true,
      );

      final failures = ops.recorded
          .where((event) => event.eventType == 'operation_result')
          .toList();
      expect(failures, hasLength(1));
      expect(
        failures.first.extensions['failReasonCode'],
        equals('APP.SYSTEM.unknown_error'),
      );
      expect(failures.first.extensions['hasCache'], isTrue);
    });
  });

  group('视频自动播放', () {
    test('启动成功上报耗时与命中候选源序号', () async {
      observability.recordVideoPlaybackStarted(
        contentId: 'video_001',
        startupMs: 420,
        candidateIndex: 1,
        autoPlay: true,
      );

      final started = eventsNamed(
        FeedPerformanceMetricNames.videoAutoplayStartupMs,
      );
      expect(started, hasLength(1));
      expect(started.first.extensions.containsKey('contentId'), isFalse);
      expect(started.first.extensions['durationMs'], equals(420));
      expect(started.first.extensions['result'], equals('ok'));
    });

    test('候选源全部失败上报失败归因', () async {
      observability.recordVideoPlaybackFailed(
        contentId: 'video_002',
        candidatesTried: 3,
        failureKind: MediaCandidateFailureKind.noPlayableSource.name,
        userScene: VideoPlaybackUserScene.temporary.name,
        retryable: true,
        autoPlay: true,
      );

      final failed = eventsNamed(
        FeedPerformanceMetricNames.videoAutoplayFailed,
      );
      expect(failed, hasLength(1));
      expect(failed.first.extensions.containsKey('contentId'), isFalse);
      expect(
        failed.first.extensions['failReasonCode'],
        equals('noPlayableSource'),
      );
      expect(failed.first.extensions['result'], equals('failed'));
    });
  });

  group('资源与长滑指标', () {
    test('图片缓存、视频 controller 和下载队列进入 typed reporter', () async {
      observability.recordImageCacheBudget(
        profile: 'compact',
        currentSizeBytes: 1024,
        maxSizeBytes: 2048,
      );
      observability.recordActiveVideoControllerCount(
        surfaceId: 'works_immersive_viewer',
        activeCount: 1,
      );
      observability.recordMediaDownloadQueue(
        profile: 'compact',
        activeDownloads: 1,
        queuedDownloads: 2,
        inflightDownloads: 3,
        cacheSizeBytes: 4096,
      );

      final resources = ops.recorded
          .where((event) => event.eventType == 'home_feed_resource_snapshot')
          .toList(growable: false);
      expect(resources, hasLength(3));
      expect(
        resources.map((event) => event.extensions['resourceKind']).toSet(),
        <Object?>{
          'image_cache_bytes',
          'active_video_controllers',
          'media_downloads',
        },
      );
      expect(resources.first.extensions['currentValue'], 1024);
      expect(resources.first.extensions['limitValue'], 2048);
      expect(resources.first.extensions['result'], 'within_budget');
      expect(
        resources.every((event) => !event.extensions.containsKey('contentId')),
        isTrue,
      );
    });
  });
}
