// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
// readiness_case: connector_connection_list_connector_connections_app_local
// readiness_case: connector_connection_get_connector_connection_app_local
// readiness_case: connector_connection_create_connector_connection_app_local
// readiness_case: connector_connection_revoke_connector_connection_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/connector_connection/adapters/connector_management_remote.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/connector_definition/application/public/connector_definition_reader.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/connector_invocation/application/public/connector_invocation_reader.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'Connection list/get/create/revoke 各自只走 canonical generated operation',
    () async {
      final executor = _ConnectionExecutor();
      final adapter = RemoteConnectorManagementFacet(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: (clientPageId, {idempotencyKey}) =>
            CloudOperationInvocationContext(
              surfaceId: AppUiSurfaces.assistantSkills.id,
              routeId: AppUiSurfaces.assistantSkills.routeId,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
              actor: const CloudOperationActorContext(
                accountId: 'connector-account',
                personaId: 'connector-persona',
              ),
            ),
        definitionReader: const _UnusedDefinitionReader(),
        invocationReader: const _UnusedInvocationReader(),
      );

      final listed = await adapter.listConnectorConnections(limit: 12);
      final fetched = await adapter.getConnectorConnection(
        connectionId: 'connection-calendar',
      );
      final created = await adapter.createConnectorConnection(
        connectorId: 'system-calendar',
        requestedCapabilities: const <String>['calendar.event.create'],
        grantReceiptRef: 'grant-receipt-1',
        idempotencyKey: 'connection-create-1',
      );
      final revoked = await adapter.revokeConnectorConnection(
        connectionId: 'connection-calendar',
        expectedRevision: 3,
        idempotencyKey: 'connection-revoke-1',
      );

      expect(listed.single.connectionId, 'connection-calendar');
      expect(fetched.connectionId, 'connection-calendar');
      expect(created.status, ConnectorConnectionStatus.active);
      expect(revoked.status, ConnectorConnectionStatus.revoked);
      expect(executor.operationIds, <String>[
        AppCloudOperationIds
            .integrationConnectorConnectionListConnectorConnections,
        AppCloudOperationIds
            .integrationConnectorConnectionGetConnectorConnection,
        AppCloudOperationIds
            .integrationConnectorConnectionCreateConnectorConnection,
        AppCloudOperationIds
            .integrationConnectorConnectionRevokeConnectorConnection,
      ]);
      expect(executor.payloads[0].queryParameters, <String, String>{
        'limit': '12',
      });
      expect(executor.payloads[1].pathParameters, <String, String>{
        'connectionId': 'connection-calendar',
      });
      expect(executor.payloads[2].body, <String, Object?>{
        'connectorId': 'system-calendar',
        'requestedCapabilities': <String>['calendar.event.create'],
        'grantReceiptRef': 'grant-receipt-1',
      });
      expect(executor.contexts[2].idempotencyKey, 'connection-create-1');
      expect(executor.payloads[3].pathParameters, <String, String>{
        'connectionId': 'connection-calendar',
      });
      expect(executor.payloads[3].body, <String, Object?>{
        'expectedRevision': 3,
      });
      expect(executor.contexts[3].idempotencyKey, 'connection-revoke-1');
    },
  );

  test('Connection view 拒绝受保护凭证字段', () {
    expect(
      () => decodeConnectorConnectionView(<String, Object?>{
        ..._connectionWire(),
        'credentialRef': 'protected://must-not-cross-app-wire',
      }),
      throwsFormatException,
    );
  });
}

Map<String, Object?> _connectionWire({
  String status = 'active',
  int revision = 3,
}) => <String, Object?>{
  'connectionId': 'connection-calendar',
  'connectorId': 'system-calendar',
  'grantedCapabilities': <String>['calendar.event.create'],
  'status': status,
  'freshnessAt': '2026-08-08T08:00:00Z',
  if (status == 'revoked') 'revokedAt': '2026-08-08T08:01:00Z',
  'revision': revision,
  'createdAt': '2026-08-08T07:00:00Z',
  'updatedAt': '2026-08-08T08:01:00Z',
};

final class _ConnectionExecutor implements CloudOperationExecutor {
  final operationIds = <String>[];
  final contexts = <CloudOperationInvocationContext>[];
  final payloads = <CloudOperationRequestPayload>[];

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    operationIds.add(operation.canonicalOperationId);
    contexts.add(context);
    payloads.add(requestEncoder());
    final response = switch (operation.canonicalOperationId) {
      AppCloudOperationIds
          .integrationConnectorConnectionListConnectorConnections =>
        <String, Object?>{
          'items': <Object?>[_connectionWire()],
        },
      AppCloudOperationIds
          .integrationConnectorConnectionCreateConnectorConnection =>
        <String, Object?>{'connection': _connectionWire(), 'replayed': false},
      AppCloudOperationIds
          .integrationConnectorConnectionRevokeConnectorConnection =>
        <String, Object?>{
          'connection': _connectionWire(status: 'revoked', revision: 4),
          'replayed': false,
        },
      _ => _connectionWire(),
    };
    return responseDecoder(response);
  }
}

final class _UnusedDefinitionReader implements ConnectorDefinitionReader {
  const _UnusedDefinitionReader();

  @override
  Future<ConnectorDefinition> getConnectorDefinition({
    required String connectorId,
  }) => throw StateError('definition reader must not be called');

  @override
  Future<List<ConnectorDefinition>> listConnectorDefinitions({
    String? capability,
    int limit = connectorDefinitionListDefaultLimit,
  }) => throw StateError('definition reader must not be called');
}

final class _UnusedInvocationReader implements ConnectorInvocationProcessQuery {
  const _UnusedInvocationReader();

  @override
  Future<ConnectorInvocationView> getConnectorInvocation({
    required String invocationId,
  }) => throw StateError('invocation reader must not be called');

  @override
  Future<List<ConnectorInvocationView>> listConnectorInvocations({
    String? connectionId,
    int limit = connectorInvocationListDefaultLimit,
  }) => throw StateError('invocation reader must not be called');
}
