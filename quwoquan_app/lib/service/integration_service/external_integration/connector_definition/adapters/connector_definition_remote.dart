import 'package:quwoquan_app/service/integration_service/external_integration/connector_definition/application/public/connector_definition_reader.dart';
import 'package:quwoquan_app/runtime/transport/generated/integration/integration_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ConnectorDefinitionInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

final class RemoteConnectorDefinitionReader
    implements ConnectorDefinitionReader {
  const RemoteConnectorDefinitionReader({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ConnectorDefinitionInvocationContextFactory invocationContext;

  @override
  Future<List<ConnectorDefinition>> listConnectorDefinitions({
    String? capability,
    int limit = connectorDefinitionListDefaultLimit,
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
}
