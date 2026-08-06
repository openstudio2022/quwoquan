import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ConnectorInvocationView;

const int connectorInvocationListDefaultLimit = 32;

/// ConnectorInvocation 对象的公开读取端口。
abstract interface class ConnectorInvocationReader {
  Future<List<ConnectorInvocationView>> listConnectorInvocations({
    String? connectionId,
    int limit = connectorInvocationListDefaultLimit,
  });

  Future<ConnectorInvocationView> getConnectorInvocation({
    required String invocationId,
  });
}
