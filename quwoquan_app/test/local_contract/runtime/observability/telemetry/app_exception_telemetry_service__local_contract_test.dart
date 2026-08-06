import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/observability/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/runtime/observability/runtime_log_ports.dart';
import 'package:quwoquan_app/runtime/observability/runtime_log_record.dart';
import 'package:quwoquan_app/runtime/observability/runtime_logger.dart';

void main() {
  RuntimeLogger logger(InMemoryRuntimeLogBuffer buffer) => RuntimeLogger(
    resource: const RuntimeLogResource(
      sourceType: 'app',
      environment: 'alpha',
      service: 'quwoquan_app',
      appVersion: 'test',
    ),
    buffer: buffer,
  );

  test('Logger 未绑定时异常采集安全跳过', () async {
    final service = AppExceptionTelemetryService();

    await service.recordGlobalException(
      source: 'widget_test',
      exceptionText: 'bootstrap unavailable',
      stackText: 'stack',
    );
    await service.flushPending();

    expect(service.lastFlushFailure, isNull);
  });

  test('全局异常进入统一加密缓冲而不写产品行为遥测', () async {
    final buffer = InMemoryRuntimeLogBuffer();
    final service = AppExceptionTelemetryService(logger: logger(buffer));

    await service.recordGlobalException(
      source: 'widget_test',
      exceptionText: 'boom',
      stackText:
          'Widget.build (/Users/test/private.dart:1)\n#1 token_12345678901234567890',
    );

    final record = (await buffer.pending()).single;
    expect(record.signal, 'app.exception.flutter');
    expect(record.kind, RuntimeLogKind.exception);
    expect(record.errorCode, 'APP.RUNTIME.uncaught_exception');
    expect(service.lastFlushFailure, isNull);
  });

  test('异常以稳定指纹去重且不保存原始调用栈', () async {
    final buffer = InMemoryRuntimeLogBuffer();
    final service = AppExceptionTelemetryService(logger: logger(buffer));
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

    final record = (await buffer.pending()).single;
    expect(record.fingerprint, isNotEmpty);
    expect(record.fingerprint, isNot(contains('/private/')));
    expect(record.attributes.toWire()['stackFrameCount'], '10');
    expect(service.lastFlushFailure, isNull);
  });

  test('已捕获异常携带结构化 RuntimeFailure 语义', () async {
    final buffer = InMemoryRuntimeLogBuffer();
    final service = AppExceptionTelemetryService(logger: logger(buffer));

    await service.recordHandledException(
      source: 'chat.send_outbox.init',
      error: StateError('storage unavailable'),
      stackTrace: StackTrace.current,
      operationId: 'SendMessage',
    );

    final record = (await buffer.pending()).single;
    final attributes = record.attributes.toWire();
    expect(record.correlation.operationId, 'SendMessage');
    expect(attributes['exceptionType'], 'StateError');
    expect(attributes['kind'], 'contract');
    expect(attributes['failurePoint'], 'APP.CONTRACT.invalid_response');
    expect(attributes['reason'], 'APP.CONTRACT.invalid_response');
  });

  test('无远端 exporter 时 flush 保留本地诊断记录', () async {
    final buffer = InMemoryRuntimeLogBuffer();
    final service = AppExceptionTelemetryService(logger: logger(buffer));

    await service.recordGlobalException(
      source: 'widget_test',
      exceptionText: 'boom',
      stackText: 'stack',
    );
    await service.flushPending();

    expect(await buffer.pending(), hasLength(1));
    expect(service.lastFlushFailure, isNull);
  });
}
