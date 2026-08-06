import 'dart:async';

import 'package:quwoquan_app/assistant/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_service.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/observability/cloud_operation_telemetry.dart';

final class AppCloudOperationTelemetrySink
    implements CloudOperationTelemetrySink {
  const AppCloudOperationTelemetrySink({
    required this.clientContextProvider,
    this.logService,
  });

  final AppLogService? logService;
  final CloudClientContextProvider clientContextProvider;

  @override
  void record(CloudOperationTelemetryEvent event) {
    final service = logService ?? AppLogService.instance;
    final context = clientContextProvider.snapshot();
    unawaited(
      service.writeEvent(
        logType: AppLogType.cloudApi,
        level: event.succeeded ? AppLogLevel.info : AppLogLevel.error,
        payload: <String, dynamic>{
          'event': 'cloud_operation',
          'operationId': event.canonicalOperationId,
          'surfaceId': event.surfaceId,
          'method': event.method,
          // 只能记录模板，禁止实例 URL、token 或 presigned query。
          'route': event.pathTemplate,
          'durMs': event.elapsed.inMilliseconds,
          'attempt': event.attempt,
          if (event.statusCode != null) 'status': event.statusCode,
          if (event.failureCode != null) 'errorCode': event.failureCode,
          if (event.retryReason != null) 'retryReason': event.retryReason,
          if (event.recoveryAction != null)
            'recoveryAction': event.recoveryAction,
          if (event.disruptionLevel != null)
            'disruptionLevel': event.disruptionLevel,
          'cacheSource': event.cacheSource,
          if (event.traceId != null) 'traceId': event.traceId,
          'result': event.succeeded ? 'ok' : 'failed',
        },
        context: AppLogContext(
          sessionId: context.sessionId,
          requestId: event.requestId ?? '',
          traceId: event.traceId ?? '',
          sourceDomain: 'cloud',
          component: 'generated_operation_executor',
          target: event.pathTemplate,
          action: event.canonicalOperationId,
        ),
        hasError: !event.succeeded,
      ),
    );
  }
}
