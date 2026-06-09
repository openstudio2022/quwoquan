import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_event_repository.dart';
import 'package:quwoquan_app/core/services/hive_runtime.dart';

void main() {
  tearDown(() {
    HiveRuntime.resetForTest();
  });

  test('Hive 未就绪时异常遥测降级跳过本地队列，不再抛异常', () async {
    HiveRuntime.debugEnsureInitializedHook = () async => false;
    final service = AppExceptionTelemetryService(
      eventRepository: MockOpsEventRepository(),
      queueBoxName: 'app_exception_queue_unavailable_test',
    );

    await service.recordGlobalException(
      source: 'widget_test',
      exceptionText: 'Hive unavailable during bootstrap',
      stackText: 'stack',
    );

    await service.flushPending();
  });
}
