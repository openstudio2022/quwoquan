import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/transport/cloud_request_headers.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/di/cloud_http_client_provider.dart';
import 'package:quwoquan_app/runtime/di/ops_event_record_dependencies.dart';
import 'package:quwoquan_app/runtime/observability/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/runtime/observability/app_log_service.dart';
import 'package:quwoquan_app/runtime/observability/app_observability_ports.dart';
import 'package:quwoquan_app/runtime/observability/runtime_log_ports.dart';
import 'package:quwoquan_app/runtime/observability/runtime_log_record.dart';
import 'package:quwoquan_app/service/product_ops_service/product_ops/event_record/adapters/runtime_log_transport_remote.dart';
import 'package:quwoquan_app/runtime/observability/runtime_diagnostics.dart';
import 'package:quwoquan_app/runtime/observability/runtime_logger.dart';
import 'package:quwoquan_app/runtime/observability/secure_runtime_log_buffer.dart';

/// alpha 只保留本地加密证据；beta/gamma/prod 从单一 metadata operation 装配
/// runtime log exporter，业务调用点不可自行拼接 HTTP。
final runtimeLogBufferProvider = Provider<RuntimeLogBuffer>((ref) {
  return SecureRuntimeLogBuffer();
});

final runtimeLoggerProvider = Provider<RuntimeLogger>((ref) {
  final logger = RuntimeLogger(
    resource: RuntimeLogResource(
      sourceType: 'app',
      environment: CloudRuntimeConfig.appRuntimeEnv,
      service: 'quwoquan_app',
      appVersion: CloudRequestHeaders.appVersion,
    ),
    buffer: ref.watch(runtimeLogBufferProvider),
    transport: CloudRuntimeConfig.appRuntimeEnv == 'alpha'
        ? null
        : CloudRuntimeLogTransport(
            writer: ref.watch(opsEventRecordBatchWriterProvider),
          ),
  );
  final latencyDispatcher = ref.watch(runtimeApiLatencyDispatcherProvider);
  latencyDispatcher.bind(logger);
  ref.onDispose(() {
    latencyDispatcher.unbind(logger);
    logger.dispose();
  });
  return logger;
});

final runtimeDiagnosticsProvider = Provider<AppRuntimeDiagnostics>((ref) {
  final diagnostics = AppRuntimeDiagnostics(ref.watch(runtimeLoggerProvider));
  ref.onDispose(diagnostics.dispose);
  return diagnostics;
});

/// 异常遥测的唯一 production 绑定点。
///
/// 业务对象只依赖 [ExceptionTelemetryPort]，不再直调
/// `AppExceptionTelemetryService.instance`。这里返回 composition root 已经
/// `bind(logger:)` 过的那一个实例，保持「未绑定 logger 时静默丢弃」的既有
/// 运行时语义不变，同时让 local_contract 能 override 成测试树内的 double。
final exceptionTelemetryPortProvider = Provider<ExceptionTelemetryPort>((ref) {
  return AppExceptionTelemetryService.instance;
});

/// 结构化事件日志的唯一 production 绑定点。
final appEventLogPortProvider = Provider<AppEventLogPort>((ref) {
  return AppLogService.instance;
});
