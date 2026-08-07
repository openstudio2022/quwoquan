import 'package:quwoquan_app/service/integration_service/external_integration/connector_invocation/application/public/connector_invocation_reader.dart';
import 'package:quwoquan_app/runtime/transport/generated/integration/integration_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ConnectorInvocationProcessQueryContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

final class RemoteConnectorInvocationReader
    implements ConnectorInvocationProcessQuery {
  const RemoteConnectorInvocationReader({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ConnectorInvocationProcessQueryContextFactory invocationContext;

  @override
  Future<List<ConnectorInvocationView>> listConnectorInvocations({
    String? connectionId,
    int limit = connectorInvocationListDefaultLimit,
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
