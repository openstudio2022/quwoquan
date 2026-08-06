import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/transport/cloud_request_headers.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/di/cloud_http_client_provider.dart';
import 'package:quwoquan_app/runtime/di/ops_event_record_dependencies.dart';
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
