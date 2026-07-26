import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

const String homepageProductJourney = 'entity_homepage';

Future<void> trackHomepageProductAction(
  WidgetRef ref, {
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
  return ref
      .read(journeyEventTrackerProvider)
      .trackAction(
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
