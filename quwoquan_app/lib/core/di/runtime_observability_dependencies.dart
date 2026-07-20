import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/core/di/cloud_http_client_provider.dart';
import 'package:quwoquan_app/core/observability/runtime_log_ports.dart';
import 'package:quwoquan_app/core/observability/runtime_log_record.dart';
import 'package:quwoquan_app/core/observability/runtime_log_transport.dart';
import 'package:quwoquan_app/core/observability/runtime_diagnostics.dart';
import 'package:quwoquan_app/core/observability/runtime_logger.dart';
import 'package:quwoquan_app/core/observability/secure_runtime_log_buffer.dart';

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
            httpClient: ref.watch(cloudHttpClientProvider),
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
  diagnostics.install();
  ref.onDispose(diagnostics.dispose);
  return diagnostics;
});
