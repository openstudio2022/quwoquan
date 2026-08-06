import 'package:quwoquan_app/service/integration_service/external_integration/connector_definition/application/public/connector_definition_reader.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/connector_invocation/application/public/connector_invocation_reader.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

const int connectorConnectionListDefaultLimit = 64;

abstract interface class ConnectorManagementFacet
    implements ConnectorDefinitionReader, ConnectorInvocationReader {
  Future<List<ConnectorConnectionView>> listConnectorConnections({
    int limit = connectorConnectionListDefaultLimit,
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
}
