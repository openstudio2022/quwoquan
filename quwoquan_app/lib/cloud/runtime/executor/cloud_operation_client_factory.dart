import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_operation_header_factory.dart';
import 'package:quwoquan_app/cloud/runtime/executor/generated_cloud_operation_executor.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/cloud/runtime/transport/cloud_json_transport.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

GeneratedCloudOperationClient buildGeneratedCloudOperationClient({
  required CloudHttpClient httpClient,
  required CloudClientContextProvider clientContextProvider,
  required CloudOperationTelemetrySink telemetrySink,
  CloudRuntimeEnvironment? environment,
}) {
  final executor = AppGeneratedCloudOperationExecutor(
    environment: environment ?? CloudRuntimeEnvironment.fromCompileTime(),
    transport: HttpCloudJsonTransport(httpClient),
    headerFactory: CloudOperationHeaderFactory(
      clientContextProvider: clientContextProvider,
    ),
    telemetrySink: telemetrySink,
  );
  return GeneratedCloudOperationClient(executor);
}
