import 'package:quwoquan_app/app/app_startup_runtime.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/ops/product_ops/event_record/application/startup_telemetry.dart';
import 'package:quwoquan_app/ops/product_ops/event_record/adapters/startup_telemetry_remote.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/ops_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_visit_append_writer.dart';
import 'package:quwoquan_app/core/di/app_cloud_client_context_provider.dart';
import 'package:quwoquan_app/core/di/app_cloud_operation_telemetry_sink.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// ops domain 的 production Remote adapter 种类。
///
/// 只有本文件可以命名 `Remote*` 实现；Provider 侧只声明 typed port 泛型。
enum OpsProductionAdapter { visitAppend }

/// 启动遥测的 production 装配：冷启动阶段还没有 ProviderScope，只能由 runtime
/// bootstrap 直接调用；装配内容仍归 ops domain 所有，不写回 `app_bootstrap.dart`。
void configureStartupTelemetryRuntime() {
  const clientContext = AppCloudClientContextProvider();
  StartupTelemetryRuntime.instance.configure(
    StartupTelemetryReporter(
      journal: StartupJournal(SharedPreferencesStartupJournalStore()),
      transport: RemoteStartupTelemetryTransport(
        client: buildGeneratedCloudOperationClient(
          httpClient: CloudHttpClient(),
          clientContextProvider: clientContext,
          telemetrySink: const AppCloudOperationTelemetrySink(
            clientContextProvider: clientContext,
          ),
        ),
        invocationContext: () => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.appShell.id,
          routeId: AppUiSurfaces.appShell.routeId,
          clientPageId: OpsRequestPageIds.reportStartupEventBatch,
          actor: const CloudOperationActorContext(),
        ),
      ),
      platform: platformWireName(currentAppPlatform),
      runtimeEnv: CloudRuntimeConfig.appRuntimeEnv,
      appVersion: const String.fromEnvironment(
        'APP_VERSION',
        defaultValue: '0.0.0',
      ),
      initialAttemptId: AppStartupRuntime.instance.startupAttemptId,
    ),
  );
}

/// ops domain 的唯一 production 装配入口。
final class OpsProductionComposition {
  const OpsProductionComposition._();

  static T generatedAdapter<T>(
    OpsProductionAdapter adapter, {
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
  }) {
    final dynamic context = invocationContext;
    final Object result = switch (adapter) {
      OpsProductionAdapter.visitAppend => RemoteOpsVisitAppendWriter(
        client: client,
        invocationContext: context,
      ),
    };
    return result as T;
  }
}
