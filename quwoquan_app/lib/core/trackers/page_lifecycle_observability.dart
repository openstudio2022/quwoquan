import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

class PageLifecycleEventNames {
  const PageLifecycleEventNames._();

  static const String pageLifecycleState = 'page_lifecycle_state';
  static const String pageRefreshState = 'page_refresh_state';
  static const String listAppendState = 'list_append_state';
  static const String mediaLoadState = 'media_load_state';
}

class PageLifecycleObservability {
  PageLifecycleObservability({required this.analytics});

  final AnalyticsService analytics;

  void recordPageState({
    required String pageName,
    required String phase,
    String? route,
    String? surface,
    String source = 'online',
    String? copyKey,
    Object? error,
    int? durationMs,
    int? retryCount,
    bool? hasCache,
    int? cacheAgeMs,
    int? itemCount,
    String? requestId,
    String? traceId,
    String? waitMode,
  }) {
    final properties = <String, dynamic>{
      'pageName': pageName,
      'phase': phase,
      'source': source,
    };
    if (route != null) properties['route'] = route;
    if (surface != null) properties['surface'] = surface;
    if (copyKey != null) properties['copyKey'] = copyKey;
    if (durationMs != null) properties['durationMs'] = durationMs;
    if (retryCount != null) properties['retryCount'] = retryCount;
    if (hasCache != null) properties['hasCache'] = hasCache;
    if (cacheAgeMs != null) properties['cacheAgeMs'] = cacheAgeMs;
    if (itemCount != null) properties['itemCount'] = itemCount;
    if (requestId != null) properties['requestId'] = requestId;
    if (traceId != null) properties['traceId'] = traceId;
    if (waitMode != null) properties['waitMode'] = waitMode;
    properties.addAll(_failureProperties(error));
    _track(
      eventName: PageLifecycleEventNames.pageLifecycleState,
      properties: properties,
    );
  }

  void recordRefresh({
    required String pageName,
    required String result,
    required bool retained,
    String? copyKey,
    Object? error,
    int? itemCount,
  }) {
    final properties = <String, dynamic>{
      'pageName': pageName,
      'result': result,
      'retained': retained,
    };
    if (copyKey != null) properties['copyKey'] = copyKey;
    if (itemCount != null) properties['itemCount'] = itemCount;
    properties.addAll(_failureProperties(error));
    _track(
      eventName: PageLifecycleEventNames.pageRefreshState,
      properties: properties,
    );
  }

  void recordAppend({
    required String pageName,
    required String result,
    required bool cursorPresent,
    required bool hasMore,
    int? itemCountBefore,
    int? itemCountAfter,
    String? copyKey,
    Object? error,
  }) {
    final properties = <String, dynamic>{
      'pageName': pageName,
      'result': result,
      'cursorPresent': cursorPresent,
      'hasMore': hasMore,
    };
    if (itemCountBefore != null) {
      properties['itemCountBefore'] = itemCountBefore;
    }
    if (itemCountAfter != null) {
      properties['itemCountAfter'] = itemCountAfter;
    }
    if (copyKey != null) properties['copyKey'] = copyKey;
    properties.addAll(_failureProperties(error));
    _track(
      eventName: PageLifecycleEventNames.listAppendState,
      properties: properties,
    );
  }

  void recordMediaLoad({
    required String mediaType,
    required String result,
    String? pageName,
    String? entityId,
    String? copyKey,
    Object? error,
    int? durationMs,
    int? candidatesTried,
    String? mediaFailureKind,
    String? userScene,
    bool? retryable,
  }) {
    final properties = <String, dynamic>{
      'mediaType': mediaType,
      'result': result,
    };
    if (pageName != null) properties['pageName'] = pageName;
    if (entityId != null) properties['entityId'] = entityId;
    if (copyKey != null) properties['copyKey'] = copyKey;
    if (durationMs != null) properties['durationMs'] = durationMs;
    if (candidatesTried != null) {
      properties['candidatesTried'] = candidatesTried;
    }
    if (mediaFailureKind != null) {
      properties['mediaFailureKind'] = mediaFailureKind;
    }
    if (userScene != null) properties['userScene'] = userScene;
    if (retryable != null) properties['retryable'] = retryable;
    properties.addAll(_failureProperties(error));
    _track(
      eventName: PageLifecycleEventNames.mediaLoadState,
      properties: properties,
    );
  }

  void _track({
    required String eventName,
    required Map<String, dynamic> properties,
  }) {
    unawaited(
      analytics.trackEvent(
        AnalyticsEvent(
          eventType: 'page_lifecycle',
          eventName: eventName,
          properties: properties,
        ),
      ),
    );
  }

  Map<String, dynamic> _failureProperties(Object? error) {
    if (error == null) {
      return const <String, dynamic>{};
    }
    final sourceCode = _sourceCode(error);
    final failureKind = _failureKind(error);
    final properties = <String, dynamic>{};
    if (sourceCode != null) properties['sourceCode'] = sourceCode;
    if (failureKind != null) properties['failureKind'] = failureKind.name;
    return properties;
  }

  String? _sourceCode(Object error) {
    if (error is CloudException && (error.code?.trim().isNotEmpty ?? false)) {
      return error.code!.trim();
    }
    if (error is UiErrorSemantic &&
        (error.sourceCode ?? '').trim().isNotEmpty) {
      return error.sourceCode!.trim();
    }
    if (error is RuntimeFailureBase && error.code.trim().isNotEmpty) {
      return error.code.trim();
    }
    return null;
  }

  RuntimeFailureKind? _failureKind(Object error) {
    if (error is UiErrorSemantic) {
      return error.failureKind;
    }
    if (error is RuntimeFailureBase) {
      return error.kind;
    }
    if (error is CloudException) {
      return error.runtimeFailure.kind;
    }
    return null;
  }
}

final pageLifecycleObservabilityProvider = Provider<PageLifecycleObservability>(
  (ref) {
    return PageLifecycleObservability(analytics: ref.read(analyticsProvider));
  },
);
