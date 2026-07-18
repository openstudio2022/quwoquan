import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_outbox.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';

import '../../../../../../support/recording_app_telemetry_recorder.dart';

void main() {
  test('Reporter 未绑定时异常采集安全跳过且不维护第二套队列', () async {
    final service = AppExceptionTelemetryService();

    await service.recordGlobalException(
      source: 'widget_test',
      exceptionText: 'bootstrap unavailable',
      stackText: 'stack',
    );
    await service.flushPending();

    expect(service.lastFlushFailure, isNull);
  });

  test('Reporter 拒绝时记录结构化 delivery degradation', () async {
    final recorder = RecordingAppTelemetryRecorder(
      recordResult: AppTelemetryRecordResult.rateLimited,
    );
    final service = AppExceptionTelemetryService(reporter: recorder);

    await service.recordGlobalException(
      source: 'widget_test',
      exceptionText: 'boom',
      stackText:
          'Widget.build (/Users/test/private.dart:1)\n#1 token_12345678901234567890',
    );

    expect(service.lastFlushFailure?.errorType, 'rateLimited');
    expect(service.lastFlushFailure?.queueDepth, 0);
  });

  test('异常使用 runtime_exception 强类型字段并裁剪方法栈', () async {
    final recorder = RecordingAppTelemetryRecorder();
    final service = AppExceptionTelemetryService(reporter: recorder);
    final stack = List<String>.generate(
      12,
      (index) =>
          '#$index Package.method$index (/private/user/input_$index.dart:1)',
    ).join('\n');

    await service.recordGlobalException(
      source: 'widget_test',
      exceptionText: 'boom',
      stackText: stack,
    );
    await service.recordGlobalException(
      source: 'widget_test',
      exceptionText: 'boom',
      stackText: stack,
    );

    expect(recorder.recorded, hasLength(1));
    final event = recorder.recorded.single;
    expect(event.eventType, 'runtime_exception');
    expect(event.extensions['errorCode'], 'APP.RUNTIME.uncaught_exception');
    final methods = event.extensions['callStack']! as List<String>;
    expect(methods, hasLength(10));
    expect(methods.join('\n'), isNot(contains('/private/')));
    expect(service.lastFlushFailure, isNull);
  });

  test('统一 Reporter flush 延迟时保留结构化失败状态', () async {
    final recorder = RecordingAppTelemetryRecorder(
      flushResult: AppTelemetryFlushResult.deferred,
    );
    final service = AppExceptionTelemetryService(reporter: recorder);

    await service.flushPending();

    expect(recorder.flushCount, 1);
    expect(service.lastFlushFailure?.errorType, 'deferred');
  });
}
