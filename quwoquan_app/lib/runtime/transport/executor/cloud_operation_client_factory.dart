import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/config/app_content_source.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/transport/executor/unavailable_cloud_operation_executor.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/context/cloud_operation_header_factory.dart';
import 'package:quwoquan_app/runtime/transport/executor/generated_cloud_operation_executor.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/runtime/transport/cloud_json_transport.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

CloudOperationExecutor? _installedCloudOperationExecutor;

void installCloudOperationExecutor(CloudOperationExecutor executor) {
  _installedCloudOperationExecutor = executor;
}

void clearInstalledCloudOperationExecutor() {
  _installedCloudOperationExecutor = null;
}

GeneratedCloudOperationClient buildGeneratedCloudOperationClient({
  required CloudHttpClient httpClient,
  required CloudClientContextProvider clientContextProvider,
  required CloudOperationTelemetrySink telemetrySink,
  CloudRuntimeEnvironment? environment,
}) {
  return GeneratedCloudOperationClient(
    buildGeneratedCloudOperationExecutor(
      httpClient: httpClient,
      clientContextProvider: clientContextProvider,
      telemetrySink: telemetrySink,
      environment: environment,
    ),
  );
}

CloudOperationExecutor buildGeneratedCloudOperationExecutor({
  required CloudHttpClient httpClient,
  required CloudClientContextProvider clientContextProvider,
  required CloudOperationTelemetrySink telemetrySink,
  CloudRuntimeEnvironment? environment,
}) {
  if (CloudRuntimeConfig.isHydrated &&
      CloudRuntimeConfig.contentSource == AppContentSource.bundledSnapshot) {
    // 已验信的离线 source 不可被显式在线参数升级，也不能把演练执行器交给在线请求。
    if (environment?.networkAccessAllowed ?? false) {
      return const UnavailableCloudOperationExecutor();
    }
    return _installedCloudOperationExecutor ??
        const UnavailableCloudOperationExecutor();
  }
  final selectedEnvironment =
      environment ?? CloudRuntimeEnvironment.fromCompileTime();
  if (!selectedEnvironment.networkAccessAllowed) {
    if (CloudRuntimeConfig.isHydrated) {
      // 在线 source 与离线参数矛盾时拒绝，不能恢复之前安装的本地演练状态。
      return const UnavailableCloudOperationExecutor();
    }
    return _installedCloudOperationExecutor ??
        const UnavailableCloudOperationExecutor();
  }
  return AppGeneratedCloudOperationExecutor(
    environment: selectedEnvironment,
    transport: HttpCloudJsonTransport(httpClient),
    headerFactory: CloudOperationHeaderFactory(
      clientContextProvider: clientContextProvider,
    ),
    telemetrySink: telemetrySink,
  );
}
