import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/di/app_cloud_client_context_provider.dart';
import 'package:quwoquan_app/runtime/di/app_cloud_operation_telemetry_sink.dart';
import 'package:quwoquan_app/runtime/di/cloud_http_client_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final cloudClientContextProvider = Provider<CloudClientContextProvider>((ref) {
  return const AppCloudClientContextProvider();
});

final cloudRuntimeEnvironmentProvider = Provider<CloudRuntimeEnvironment>((
  ref,
) {
  return CloudRuntimeEnvironment.fromCompileTime();
});

/// 全 App 唯一 authenticated generated operation client composition。
///
/// 放在独立 DI 边界，使遥测、实时连接与页面 Facet 复用同一执行器装配，避免
/// 各子系统重新拼接 HTTP、鉴权、重试或 decoder。
final generatedCloudOperationClientProvider =
    Provider<GeneratedCloudOperationClient>((ref) {
      final clientContext = ref.watch(cloudClientContextProvider);
      return buildGeneratedCloudOperationClient(
        httpClient: ref.watch(cloudHttpClientProvider),
        clientContextProvider: clientContext,
        environment: ref.watch(cloudRuntimeEnvironmentProvider),
        telemetrySink: AppCloudOperationTelemetrySink(
          clientContextProvider: clientContext,
        ),
      );
    });

/// 登录 bootstrap 专用 generated client：永不读取、等待或附加既有 bearer。
final unauthenticatedGeneratedCloudOperationClientProvider =
    Provider<GeneratedCloudOperationClient>((ref) {
      final clientContext = ref.watch(cloudClientContextProvider);
      return buildGeneratedCloudOperationClient(
        httpClient: ref.watch(unauthenticatedCloudHttpClientProvider),
        clientContextProvider: clientContext,
        environment: ref.watch(cloudRuntimeEnvironmentProvider),
        telemetrySink: AppCloudOperationTelemetrySink(
          clientContextProvider: clientContext,
        ),
      );
    });
