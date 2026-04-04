import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_event_repository.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';

void main() {
  group('AnalyticsService', () {
    test('remote 模式下会将 façade 事件上报到 ops 统一事件仓储', () async {
      final remote = MockOpsEventRepository();
      final analytics = AnalyticsService.forTesting(
        mode: AppDataSourceMode.remote,
        eventRepository: remote,
      );

      await analytics.initialize(const AnalyticsConfig());
      await analytics.trackEvent(
        const AnalyticsEvent(
          eventType: 'article_reader_metric',
          eventName: 'article_reader_open_ms',
          properties: <String, dynamic>{'postId': 'post_001'},
        ),
      );

      expect(remote.recorded, hasLength(1));
      expect(remote.recorded.first.eventType, equals('article_reader_metric'));
      expect(
        remote.recorded.first.targetKey,
        equals('article_reader_metric.article_reader_open_ms'),
      );
      expect(remote.recorded.first.source, equals('analytics_facade'));
    });
  });
}
