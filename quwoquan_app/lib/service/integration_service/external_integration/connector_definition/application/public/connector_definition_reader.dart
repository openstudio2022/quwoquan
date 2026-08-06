import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ConnectorDefinition;

const int connectorDefinitionListDefaultLimit = 64;

/// ConnectorDefinition 对象的公开读取端口。
abstract interface class ConnectorDefinitionReader {
  Future<List<ConnectorDefinition>> listConnectorDefinitions({
    String? capability,
    int limit = connectorDefinitionListDefaultLimit,
  });

  Future<ConnectorDefinition> getConnectorDefinition({
    required String connectorId,
  });
}
