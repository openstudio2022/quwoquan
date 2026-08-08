import 'package:quwoquan_app/runtime/transport/generated/integration/integration_request_page_ids.g.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/connector_connection/application/connector_management_facet.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/connector_definition/application/public/connector_definition_reader.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/connector_invocation/application/public/connector_invocation_reader.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ConnectorInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      String? idempotencyKey,
    });

final class RemoteConnectorManagementFacet implements ConnectorManagementFacet {
  const RemoteConnectorManagementFacet({
    required this.client,
    required this.invocationContext,
    required this.definitionReader,
    required this.invocationReader,
  });

  final GeneratedCloudOperationClient client;
  final ConnectorInvocationContextFactory invocationContext;
  final ConnectorDefinitionReader definitionReader;
  final ConnectorInvocationProcessQuery invocationReader;

  @override
  Future<List<ConnectorDefinition>> listConnectorDefinitions({
    String? capability,
    int limit = connectorDefinitionListDefaultLimit,
  }) => definitionReader.listConnectorDefinitions(
    capability: capability,
    limit: limit,
  );

  @override
  Future<ConnectorDefinition> getConnectorDefinition({
    required String connectorId,
  }) => definitionReader.getConnectorDefinition(connectorId: connectorId);

  @override
  Future<List<ConnectorConnectionView>> listConnectorConnections({
    int limit = connectorConnectionListDefaultLimit,
  }) async {
    final result = await client
        .integrationConnectorConnectionListConnectorConnections(
          ListConnectorConnectionsQuery(limit: limit),
          context: invocationContext(
            IntegrationRequestPageIds.listConnectorConnections,
          ),
        );
    return result.items;
  }

  @override
  Future<ConnectorConnectionView> getConnectorConnection({
    required String connectionId,
  }) {
    return client.integrationConnectorConnectionGetConnectorConnection(
      GetConnectorConnectionQuery(connectionId: connectionId),
      context: invocationContext(
        IntegrationRequestPageIds.getConnectorConnection,
      ),
    );
  }

  @override
  Future<ConnectorConnectionView> createConnectorConnection({
    required String connectorId,
    required List<String> requestedCapabilities,
    required String grantReceiptRef,
    required String idempotencyKey,
  }) async {
    final result = await client
        .integrationConnectorConnectionCreateConnectorConnection(
          CreateConnectorConnectionRequest(
            connectorId: connectorId,
            requestedCapabilities: requestedCapabilities,
            grantReceiptRef: grantReceiptRef,
          ),
          context: invocationContext(
            IntegrationRequestPageIds.createConnectorConnection,
            idempotencyKey: idempotencyKey,
          ),
        );
    return result.connection;
  }

  @override
  Future<ConnectorConnectionView> revokeConnectorConnection({
    required String connectionId,
    required int expectedRevision,
    required String idempotencyKey,
  }) async {
    final result = await client
        .integrationConnectorConnectionRevokeConnectorConnection(
          RevokeConnectorConnectionRequest(
            connectionId: connectionId,
            expectedRevision: expectedRevision,
          ),
          context: invocationContext(
            IntegrationRequestPageIds.revokeConnectorConnection,
            idempotencyKey: idempotencyKey,
          ),
        );
    return result.connection;
  }

  @override
  Future<List<ConnectorInvocationView>> listConnectorInvocations({
    String? connectionId,
    int limit = connectorInvocationListDefaultLimit,
  }) => invocationReader.listConnectorInvocations(
    connectionId: connectionId,
    limit: limit,
  );

  @override
  Future<ConnectorInvocationView> getConnectorInvocation({
    required String invocationId,
  }) => invocationReader.getConnectorInvocation(invocationId: invocationId);
}
