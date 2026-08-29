import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/observability/analytics.dart';
import 'package:quwoquan_app/runtime/observability/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_pages.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../support/runtime/observability/recording_app_telemetry_recorder.dart';

void main() {
  test('页面失败漏斗保留恢复动作与端云关联标识', () {
    final analytics = _CapturingAnalyticsService();
    final observability = PageLifecycleObservability(
      analytics: analytics,
      telemetryRecorder: RecordingAppTelemetryRecorder(),
    );
    final failure = RuntimeFailure(
      code: 'CONTENT.SYSTEM.interaction_read_model_unavailable',
      origin: RuntimeFailureOrigin.remoteDependency,
      kind: RuntimeFailureKind.unavailable,
      nature: RuntimeFailureNature.transient,
      location: const RuntimeFailureLocation(
        businessObject: 'content.profile_interaction_activity_view',
        functionModule: 'list_received',
      ),
      context: const RuntimeFailureContext(),
      recovery: const RuntimeRecoveryDirective(
        action: 'retry',
        disruptionLevel: 'surface',
      ),
    );

    observability.recordPageState(
      pageName: 'profile',
      phase: 'blockingFailure',
      error: CloudException(
        type: CloudErrorType.server,
        message: 'read model unavailable',
        code: failure.code,
        runtimeFailure: failure,
        requestId: 'request-profile-1',
        traceId: 'trace-profile-1',
      ),
      durationMs: 320,
    );

    final properties = analytics.single.properties;
    expect(properties['sourceCode'], failure.code);
    expect(properties['failureKind'], 'unavailable');
    expect(properties['recoveryAction'], 'retry');
    expect(properties['disruptionLevel'], 'surface');
    expect(properties['requestId'], 'request-profile-1');
    expect(properties['traceId'], 'trace-profile-1');
    expect(properties['durationMs'], 320);
  });

  test('本地结构化失败从 context 读取关联标识', () {
    final analytics = _CapturingAnalyticsService();
    final observability = PageLifecycleObservability(
      analytics: analytics,
      telemetryRecorder: RecordingAppTelemetryRecorder(),
    );

    observability.recordPageState(
      pageName: 'create',
      phase: 'blockingFailure',
      error: const RuntimeFailure(
        code: 'CONTENT.SYSTEM.required_dependency_unavailable',
        origin: RuntimeFailureOrigin.localClient,
        kind: RuntimeFailureKind.unavailable,
        nature: RuntimeFailureNature.transient,
        location: RuntimeFailureLocation(
          businessObject: 'content.post',
          functionModule: 'publish',
        ),
        context: RuntimeFailureContext(
          attributes: <RuntimeContextAttribute>[
            RuntimeContextAttribute(
              key: 'requestId',
              value: 'request-create-1',
            ),
            RuntimeContextAttribute(key: 'traceId', value: 'trace-create-1'),
          ],
        ),
        recovery: RuntimeRecoveryDirective(
          action: 'retry',
          disruptionLevel: 'surface',
        ),
      ),
    );

    final properties = analytics.single.properties;
    expect(properties['requestId'], 'request-create-1');
    expect(properties['traceId'], 'trace-create-1');
  });

  test('媒体加载以 catalog payload 保留 canonical 页面、对象和失败维度', () async {
    final telemetry = RecordingAppTelemetryRecorder();
    final analytics = AnalyticsService.forTesting(telemetryReporter: telemetry);
    final observability = PageLifecycleObservability(
      analytics: analytics,
      telemetryRecorder: telemetry,
    );
    final failure = RuntimeFailure(
      code: 'CONTENT.SYSTEM.media_unavailable',
      origin: RuntimeFailureOrigin.remoteDependency,
      kind: RuntimeFailureKind.unavailable,
      nature: RuntimeFailureNature.transient,
      location: const RuntimeFailureLocation(
        businessObject: 'content.media_asset',
        functionModule: 'load_image',
      ),
      context: const RuntimeFailureContext(
        attributes: <RuntimeContextAttribute>[
          RuntimeContextAttribute(key: 'requestId', value: 'request-media-1'),
          RuntimeContextAttribute(key: 'traceId', value: 'trace-media-1'),
        ],
      ),
      recovery: const RuntimeRecoveryDirective(
        action: 'retry',
        disruptionLevel: 'surface',
      ),
    );

    observability.recordMediaLoad(
      mediaType: 'image',
      result: 'failure',
      pageName: PageNames.workBrowser,
      surfaceId: AppUiSurfaces.workBrowser.id,
      objectType: 'contentPost',
      objectId: 'post-42',
      copyKey: 'imageLoadFailed',
      error: failure,
      durationMs: 420,
      candidatesTried: 2,
      mediaFailureKind: 'http404',
      userScene: 'unavailable',
      retryable: false,
    );
    await Future<void>.delayed(Duration.zero);

    final recorded = telemetry.recorded.single;
    expect(recorded.eventType, PageLifecycleEventNames.mediaLoadState);
    expect(recorded.pageName, PageNames.workBrowser);
    expect(recorded.extensions, <String, Object?>{
      'mediaType': 'image',
      'result': 'failure',
      'durationMs': 420,
      'candidatesTried': 2,
      'surfaceId': AppUiSurfaces.workBrowser.id,
      'objectType': 'contentPost',
      'objectId': 'post-42',
      'copyKey': 'imageLoadFailed',
      'failReasonCode': failure.code,
      'recoveryAction': 'retry',
      'requestId': 'request-media-1',
      'traceId': 'trace-media-1',
      'mediaFailureKind': 'http404',
      'userScene': 'unavailable',
      'retryable': false,
    });
  });
}

final class _CapturingAnalyticsService extends AnalyticsService {
  _CapturingAnalyticsService() : super.forTesting();

  final List<AnalyticsEvent> events = <AnalyticsEvent>[];

  AnalyticsEvent get single => events.single;

  @override
  Future<void> trackEvent(AnalyticsEvent event) async {
    events.add(event);
  }
}
