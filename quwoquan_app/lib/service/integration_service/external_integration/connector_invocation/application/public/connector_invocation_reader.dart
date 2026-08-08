import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ConnectorInvocationView;

const int connectorInvocationListDefaultLimit = 32;

/// ConnectorInvocation（process_manager）的公开读端口。
///
/// 命名遵循 `APP_PROCESS_PORT_NAMING` 的 `*ProcessQuery`。
abstract interface class ConnectorInvocationProcessQuery {
  Future<List<ConnectorInvocationView>> listConnectorInvocations({
    String? connectionId,
    int limit = connectorInvocationListDefaultLimit,
  });

  Future<ConnectorInvocationView> getConnectorInvocation({
    required String invocationId,
  });
}
