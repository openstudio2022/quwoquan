import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_event_repository.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/core/trackers/feed_performance_observability.dart';

/// 任务 B · FeedPerformanceObservability 单元测试。
///
/// 复用真实 [AnalyticsService] remote 出口 + [MockOpsEventRepository]，
/// 既验证度量逻辑，又顺带覆盖 façade -> ops 仓储的端云上报链路（与
/// analytics_service_test 同一断言口径）。
void main() {
  late MockOpsEventRepository ops;
  late AnalyticsService analytics;
  late FeedPerformanceObservability observability;

  setUp(() async {
    ops = MockOpsEventRepository();
    analytics = AnalyticsService.forTesting(
      mode: AppDataSourceMode.remote,
      eventRepository: ops,
    );
    await analytics.initialize(const AnalyticsConfig());
    observability = FeedPerformanceObservability(analytics: analytics);
  });

  List<OpsEventRecordInput> eventsNamed(String name) {
    return ops.recorded.where((event) => event.eventName == name).toList();
  }

  group('首屏 TTI', () {
    test('请求 -> 首帧 上报一次首屏可交互耗时', () async {
      observability.markFeedRequested('recommend');
      observability.markFirstContentReady('recommend', itemCount: 8);

      final tti = eventsNamed(FeedPerformanceMetricNames.firstScreenTtiMs);
      expect(tti, hasLength(1));
      expect(tti.first.eventType, equals('feed_metric'));
      expect(tti.first.payload['channelId'], equals('recommend'));
      expect(tti.first.payload['itemCount'], equals(8));
      expect(tti.first.payload['durationMs'], isA<int>());
      expect((tti.first.payload['durationMs'] as int) >= 0, isTrue);
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
    test('同一 channel::reason 去重，不同 reason 各上报一次', () async {
      observability.recordFeedLoadFailed(
        channelId: 'recommend',
        reason: 'page_load',
      );
      observability.recordFeedLoadFailed(
        channelId: 'recommend',
        reason: 'page_load',
      );
      observability.recordFeedLoadFailed(
        channelId: 'recommend',
        reason: 'timeout',
      );

      final failures = eventsNamed(FeedPerformanceMetricNames.feedLoadFailed);
      expect(failures, hasLength(2));
      expect(
        failures.map((event) => event.payload['reason']).toSet(),
        equals(<String>{'page_load', 'timeout'}),
      );
      expect(failures.first.payload['result'], equals('failed'));
    });

    test('首屏成功后复位失败去重，相同 reason 可再次上报', () async {
      observability.recordFeedLoadFailed(
        channelId: 'recommend',
        reason: 'page_load',
      );
      observability.markFeedRequested('recommend');
      observability.markFirstContentReady('recommend', itemCount: 6);
      observability.recordFeedLoadFailed(
        channelId: 'recommend',
        reason: 'page_load',
      );

      expect(
        eventsNamed(FeedPerformanceMetricNames.feedLoadFailed),
        hasLength(2),
      );
    });

    test('空 reason 归一化为 unknown', () async {
      observability.recordFeedLoadFailed(channelId: 'recommend', reason: '   ');

      final failures = eventsNamed(FeedPerformanceMetricNames.feedLoadFailed);
      expect(failures, hasLength(1));
      expect(failures.first.payload['reason'], equals('unknown'));
    });
  });

  group('视频自动播放', () {
    test('启动成功上报耗时与命中候选源序号', () async {
      observability.recordVideoPlaybackStarted(
        contentId: 'video_001',
        startupMs: 420,
        candidateIndex: 1,
      );

      final started = eventsNamed(
        FeedPerformanceMetricNames.videoAutoplayStartupMs,
      );
      expect(started, hasLength(1));
      expect(started.first.payload['contentId'], equals('video_001'));
      expect(started.first.payload['durationMs'], equals(420));
      expect(started.first.payload['candidateIndex'], equals(1));
      expect(started.first.payload['result'], equals('ok'));
    });

    test('候选源全部失败上报失败归因', () async {
      observability.recordVideoPlaybackFailed(
        contentId: 'video_002',
        candidatesTried: 3,
      );

      final failed = eventsNamed(
        FeedPerformanceMetricNames.videoAutoplayFailed,
      );
      expect(failed, hasLength(1));
      expect(failed.first.payload['contentId'], equals('video_002'));
      expect(failed.first.payload['candidatesTried'], equals(3));
      expect(failed.first.payload['result'], equals('failed'));
    });
  });
}
