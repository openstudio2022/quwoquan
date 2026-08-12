import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/context/cloud_operation_header_factory.dart';
import 'package:quwoquan_app/runtime/transport/executor/generated_cloud_operation_executor.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/runtime/transport/cloud_json_transport.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

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
  return AppGeneratedCloudOperationExecutor(
    environment: environment ?? CloudRuntimeEnvironment.fromCompileTime(),
    transport: HttpCloudJsonTransport(httpClient),
    headerFactory: CloudOperationHeaderFactory(
      clientContextProvider: clientContextProvider,
    ),
    telemetrySink: telemetrySink,
  );
}
