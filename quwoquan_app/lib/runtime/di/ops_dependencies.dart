import 'package:quwoquan_app/runtime/shell/startup/app_startup_runtime.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/shell/recovery/recovery_operation_gateway.dart';
import 'package:quwoquan_app/runtime/observability/startup/startup_telemetry.dart';
import 'package:quwoquan_app/service/product_ops_service/product_ops/app_release/adapters/remote_app_release_recovery_reader.dart';
import 'package:quwoquan_app/service/product_ops_service/product_ops/app_release/application/app_release_recovery_reader.dart';
import 'package:quwoquan_app/service/product_ops_service/product_ops/event_record/adapters/startup_telemetry_remote.dart';
import 'package:quwoquan_app/service/product_ops_service/product_ops/recovery_failure/adapters/remote_recovery_failure_writer.dart';
import 'package:quwoquan_app/service/product_ops_service/product_ops/recovery_failure/application/recovery_failure_writer.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/generated/ops/ops_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/product_ops_service/product_ops/visit_record/adapters/ops_visit_append_writer.dart';
import 'package:quwoquan_app/runtime/di/app_cloud_client_context_provider.dart';
import 'package:quwoquan_app/runtime/di/app_cloud_operation_telemetry_sink.dart';
import 'package:quwoquan_app/runtime/platform/platform_target.dart';
import 'package:quwoquan_cloud_contracts/generated/ops_contracts.dart'
    as ops_contracts;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// ops domain 的 production Remote adapter 种类。
///
/// 只有本文件可以命名 `Remote*` 实现；Provider 侧只声明 typed port 泛型。
enum OpsProductionAdapter { visitAppend }

/// 启动恢复发生在普通 runtime config hydration 之前，只能安装一个按原生
/// effective launch manifest binding 构造的 Product Ops Remote facade。
void configureRecoveryRuntimeOperations() {
  final registry = RecoveryRuntimeOperationsRegistry.instance;
  if (registry.isConfigured) return;
  registry.configure((binding) {
    const clientContext = AppCloudClientContextProvider();
    final client = buildGeneratedCloudOperationClient(
      httpClient: CloudHttpClient(),
      clientContextProvider: clientContext,
      telemetrySink: const AppCloudOperationTelemetrySink(
        clientContextProvider: clientContext,
      ),
      environment: CloudRuntimeEnvironment(
        environment: binding.environment,
        gatewayBaseUri: binding.recoveryOrigin,
      ),
    );
    return _ProductOpsRecoveryRuntimeOperations(
      releaseReader: RemoteAppReleaseRecoveryReader(
        client: client,
        invocationContext: () =>
            _recoveryInvocationContext(OpsRequestPageIds.getAppRecoveryVersion),
      ),
      failureWriter: RemoteRecoveryFailureWriter(
        client: client,
        invocationContext: () =>
            _recoveryInvocationContext(OpsRequestPageIds.reportRecoveryFailure),
      ),
    );
  });
}

/// 恢复通道两个 operation 在 canonical 契约里都只绑定 `welcome`（启动/恢复面）。
/// 用 `appShell` 会在 header 工厂 fail-closed，恢复上报永远发不出去。
CloudOperationInvocationContext _recoveryInvocationContext(
  String clientPageId,
) => CloudOperationInvocationContext(
  surfaceId: AppUiSurfaces.welcome.id,
  clientPageId: clientPageId,
  actor: const CloudOperationActorContext(),
);

final class _ProductOpsRecoveryRuntimeOperations
    implements RecoveryRuntimeOperations {
  const _ProductOpsRecoveryRuntimeOperations({
    required this.releaseReader,
    required this.failureWriter,
  });

  final AppReleaseRecoveryReader releaseReader;
  final RecoveryFailureWriter failureWriter;

  @override
  Future<RecoveryVersionResponse> getVersion(
    RecoveryVersionRequest request,
  ) async {
    final facts = await releaseReader.read(
      AppReleaseRecoveryQuery(
        platform: request.platform,
        appVersion: request.appVersion,
        buildNumber: request.buildNumber,
      ),
    );
    return RecoveryVersionResponse(
      platform: switch (facts.platform) {
        AppReleaseRecoveryPlatform.android => RecoveryVersionPlatform.android,
        AppReleaseRecoveryPlatform.ios => RecoveryVersionPlatform.ios,
        AppReleaseRecoveryPlatform.web => RecoveryVersionPlatform.web,
      },
      latestVersion: facts.latestVersion,
      latestBuild: facts.latestBuild,
      minimumSupportedVersion: facts.minimumSupportedVersion,
      minimumSupportedBuild: facts.minimumSupportedBuild,
      updateState: switch (facts.updateState) {
        AppReleaseUpdateState.none => RecoveryUpdateState.none,
        AppReleaseUpdateState.available => RecoveryUpdateState.available,
        AppReleaseUpdateState.required => RecoveryUpdateState.required,
      },
      updateChannel: switch (facts.updateChannel) {
        AppReleaseRecoveryChannel.nativeUpdate =>
          RecoveryVersionChannel.nativeUpdate,
        AppReleaseRecoveryChannel.webOnly => RecoveryVersionChannel.webOnly,
      },
      updateUrl: facts.updateUrl,
      recoveryUrl: facts.recoveryUrl,
    );
  }

  @override
  Future<void> reportFailure(RecoveryFailurePayload payload) {
    return failureWriter.write(
      RecoveryFailureRecord(
        occurredAt: payload.occurredAt,
        appVersion: payload.appVersion,
        buildNumber: payload.buildNumber,
        platform: payload.platform,
        osVersion: payload.osVersion,
        deviceModel: payload.deviceModel,
        errorSource: payload.errorSource,
        errorType: payload.errorType,
        errorMessage: payload.errorMessage,
        stackTrace: payload.stackTrace,
      ),
    );
  }
}

/// runtime config 校验前只安装唯一 journal；此阶段绝不创建 Remote transport。
void initializeStartupTelemetryRuntime() {
  if (StartupTelemetryRuntime.instance.isInitialized) {
    return;
  }
  StartupTelemetryRuntime.instance.initialize(
    StartupTelemetryReporter(
      journal: StartupJournal(SharedPreferencesStartupJournalStore()),
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

/// runtime config 完成 canonical 校验后，才把同一个 journal 接到 generated Remote。
void attachStartupTelemetryTransport() {
  const clientContext = AppCloudClientContextProvider();
  StartupTelemetryRuntime.instance.attachTransport(
    RemoteStartupTelemetryTransport(
      client: buildGeneratedCloudOperationClient(
        httpClient: CloudHttpClient(),
        clientContextProvider: clientContext,
        telemetrySink: const AppCloudOperationTelemetrySink(
          clientContextProvider: clientContext,
        ),
      ),
      invocationContext: ({required bool recoveryBatch}) =>
          CloudOperationInvocationContext(
            surfaceId: recoveryBatch
                ? ops_contracts
                      .StartupRecoverySurface
                      .pageAppStartupRecovery
                      .wireName
                : AppUiSurfaces.appShell.id,
            routeId: recoveryBatch ? null : AppUiSurfaces.appShell.routeId,
            clientPageId: OpsRequestPageIds.reportStartupEventBatch,
            actor: const CloudOperationActorContext(),
          ),
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
