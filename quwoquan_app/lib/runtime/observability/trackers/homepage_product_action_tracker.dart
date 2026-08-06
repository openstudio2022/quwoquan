import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/observability/trackers/journey_event_tracker.dart';

const String homepageProductJourney = 'entity_homepage';

Future<void> trackHomepageProductAction(
  JourneyEventTracker tracker, {
  required String action,
  required String pageName,
  required String result,
  required DateTime startedAt,
  String homepageId = '',
  Object? error,
}) {
  final failure = error == null ? null : runtimeFailureFromError(error);
  final sourceCode = failure?.code.trim() ?? '';
  final failReasonCode = error == null
      ? ''
      : (sourceCode.isNotEmpty ? sourceCode : error.runtimeType.toString());
  return tracker.trackAction(
    journey: homepageProductJourney,
    action: action,
    pageName: pageName,
    targetType: homepageId.isEmpty ? '' : 'homepage',
    targetKey: homepageId,
    entityType: homepageId.isEmpty ? '' : 'homepage',
    entityId: homepageId,
    payload: <String, dynamic>{
      'result': result,
      'durationMs': DateTime.now().difference(startedAt).inMilliseconds,
      if (failReasonCode.isNotEmpty) 'failReasonCode': failReasonCode,
    },
  );
}
