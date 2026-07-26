// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/analytics-metric-dictionary/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/analytics/analytics.dart';

import '../../../support/recording_app_telemetry_recorder.dart';

void main() {
  group('AnalyticsService', () {
    test('façade 事件只投影到强类型 product_action', () async {
      final remote = RecordingAppTelemetryRecorder();
      final analytics = AnalyticsService.forTesting(telemetryReporter: remote);

      await analytics.initialize(const AnalyticsConfig());
      await analytics.trackEvent(
        const AnalyticsEvent(
          eventType: 'article_reader_metric',
          eventName: 'article_reader_open_ms',
          properties: <String, dynamic>{'postId': 'post_001'},
        ),
      );

      expect(remote.recorded, hasLength(1));
      expect(remote.recorded.first.eventType, equals('product_action'));
      expect(
        remote.recorded.first.extensions['journey'],
        equals('article_reader_metric'),
      );
      expect(
        remote.recorded.first.extensions['action'],
        equals('article_reader_open_ms'),
      );
      expect(remote.recorded.first.extensions.containsKey('postId'), isFalse);
    });
  });
}
