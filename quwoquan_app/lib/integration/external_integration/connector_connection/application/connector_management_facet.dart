import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

abstract interface class ConnectorManagementFacet {
  Future<List<ConnectorDefinition>> listConnectorDefinitions({
    String? capability,
    int limit = 64,
  });

  Future<ConnectorDefinition> getConnectorDefinition({
    required String connectorId,
  });

  Future<List<ConnectorConnectionView>> listConnectorConnections({
    int limit = 64,
  });

  Future<ConnectorConnectionView> getConnectorConnection({
    required String connectionId,
  });

  Future<ConnectorConnectionView> createConnectorConnection({
    required String connectorId,
    required List<String> requestedCapabilities,
    required String grantReceiptRef,
    required String idempotencyKey,
  });

  Future<ConnectorConnectionView> revokeConnectorConnection({
    required String connectionId,
    required int expectedRevision,
    required String idempotencyKey,
  });

  Future<List<ConnectorInvocationView>> listConnectorInvocations({
    String? connectionId,
    int limit = 32,
  });

  Future<ConnectorInvocationView> getConnectorInvocation({
    required String invocationId,
  });
}
