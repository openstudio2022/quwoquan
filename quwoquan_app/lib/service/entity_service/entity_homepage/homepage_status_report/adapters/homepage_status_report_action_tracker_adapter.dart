import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_status_report/application/public/homepage_status_report_action_tracker.dart';
import 'package:quwoquan_app/runtime/observability/trackers/homepage_product_action_tracker.dart';
import 'package:quwoquan_app/runtime/observability/trackers/journey_event_tracker.dart';

/// 将 HomepageStatusReport 对象动作投影到统一 product-action telemetry。
final class HomepageStatusReportActionTrackerAdapter
    implements HomepageStatusReportActionTracker {
  const HomepageStatusReportActionTrackerAdapter({
    required this.journeyEventTracker,
  });

  final JourneyEventTracker journeyEventTracker;

  @override
  Future<void> trackSubmit({
    required String homepageId,
    required bool succeeded,
    required DateTime startedAt,
    Object? error,
  }) {
    return trackHomepageProductAction(
      journeyEventTracker,
      action: 'status_report_submit',
      pageName: 'homepageStatusReport',
      result: succeeded ? 'success' : 'failure',
      startedAt: startedAt,
      homepageId: homepageId,
      error: error,
    );
  }
}
