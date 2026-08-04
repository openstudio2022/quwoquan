import 'package:quwoquan_app/cloud/runtime/generated/integration/integration_request_page_ids.g.dart';
import 'package:quwoquan_app/integration/external_integration/connector_connection/application/connector_management_facet.dart';
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
  });

  final GeneratedCloudOperationClient client;
  final ConnectorInvocationContextFactory invocationContext;

  @override
  Future<List<ConnectorDefinition>> listConnectorDefinitions({
    String? capability,
    int limit = 64,
  }) async {
    final result = await client
        .integrationConnectorDefinitionListConnectorDefinitions(
          ListConnectorDefinitionsQuery(capability: capability, limit: limit),
          context: invocationContext(
            IntegrationRequestPageIds.listConnectorDefinitions,
          ),
        );
    return result.items;
  }

  @override
  Future<ConnectorDefinition> getConnectorDefinition({
    required String connectorId,
  }) {
    return client.integrationConnectorDefinitionGetConnectorDefinition(
      GetConnectorDefinitionQuery(connectorId: connectorId),
      context: invocationContext(
        IntegrationRequestPageIds.getConnectorDefinition,
      ),
    );
  }

  @override
  Future<List<ConnectorConnectionView>> listConnectorConnections({
    int limit = 64,
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
    int limit = 32,
  }) async {
    final result = await client
        .integrationConnectorInvocationListConnectorInvocations(
          ListConnectorInvocationsQuery(
            connectionId: connectionId,
            limit: limit,
          ),
          context: invocationContext(
            IntegrationRequestPageIds.listConnectorInvocations,
          ),
        );
    return result.items;
  }

  @override
  Future<ConnectorInvocationView> getConnectorInvocation({
    required String invocationId,
  }) {
    return client.integrationConnectorInvocationGetConnectorInvocation(
      GetConnectorInvocationQuery(invocationId: invocationId),
      context: invocationContext(
        IntegrationRequestPageIds.getConnectorInvocation,
      ),
    );
  }
}
