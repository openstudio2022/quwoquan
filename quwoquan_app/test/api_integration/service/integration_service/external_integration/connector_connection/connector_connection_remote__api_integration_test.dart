// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
// readiness_case: connector_connection_list_connector_connections_app_api
// readiness_case: connector_connection_get_connector_connection_app_api
// readiness_case: connector_connection_create_connector_connection_app_api
// readiness_case: connector_connection_revoke_connector_connection_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/integration_api_contract_harness.dart';

void main() {
  late ConnectorConnectionApiInputs inputs;
  IntegrationApiContractHarness? harness;

  setUpAll(() async {
    inputs = ConnectorConnectionApiInputs.fromEnvironment();
    harness = await IntegrationApiContractHarness.createForConnectorConnection(
      inputs,
    );
  });
  tearDownAll(() async => harness?.close());

  test(
    'production Remote 通过真实 Gamma gateway create→list→get→revoke 并保留观测身份',
    () async {
      final api = harness!;
      ConnectorConnectionView? created;
      ConnectorConnectionView? revoked;
      try {
        created = await api.connections.createConnectorConnection(
          connectorId: inputs.connectorId,
          requestedCapabilities: inputs.requestedCapabilities,
          grantReceiptRef: inputs.grantReceiptRef,
          idempotencyKey: inputs.createIdempotencyKey(),
        );
        expect(created.status, ConnectorConnectionStatus.active);
        expect(created.connectorId, inputs.connectorId);
        expect(
          created.grantedCapabilities,
          containsAll(inputs.requestedCapabilities),
        );
        expect(created.revision, greaterThan(0));

        final listed = await api.connections.listConnectorConnections();
        final listedConnection = listed.singleWhere(
          (connection) => connection.connectionId == created!.connectionId,
        );
        expect(listedConnection.toWire(), created.toWire());

        final fetched = await api.connections.getConnectorConnection(
          connectionId: created.connectionId,
        );
        expect(fetched.toWire(), created.toWire());
      } finally {
        if (created != null) {
          revoked = await api.connections.revokeConnectorConnection(
            connectionId: created.connectionId,
            expectedRevision: created.revision,
            idempotencyKey: inputs.revokeIdempotencyKey(created),
          );
        }
      }

      expect(revoked, isNotNull);
      expect(revoked!.status, ConnectorConnectionStatus.revoked);
      expect(revoked.revokedAt, isNotNull);
      expect(revoked.revision, greaterThan(created.revision));

      final events = await api.telemetry.waitForEvents(minimumCount: 4);
      final connectionEvents = events
          .where(
            (event) => <String>{
              AppCloudOperationIds
                  .integrationConnectorConnectionCreateConnectorConnection,
              AppCloudOperationIds
                  .integrationConnectorConnectionListConnectorConnections,
              AppCloudOperationIds
                  .integrationConnectorConnectionGetConnectorConnection,
              AppCloudOperationIds
                  .integrationConnectorConnectionRevokeConnectorConnection,
            }.contains(event.canonicalOperationId),
          )
          .toList(growable: false);
      expect(
        connectionEvents.map((event) => event.canonicalOperationId),
        <String>[
          AppCloudOperationIds
              .integrationConnectorConnectionCreateConnectorConnection,
          AppCloudOperationIds
              .integrationConnectorConnectionListConnectorConnections,
          AppCloudOperationIds
              .integrationConnectorConnectionGetConnectorConnection,
          AppCloudOperationIds
              .integrationConnectorConnectionRevokeConnectorConnection,
        ],
      );
      expect(connectionEvents.every((event) => event.succeeded), isTrue);
      expect(
        connectionEvents.every(
          (event) => event.requestId.isNotEmpty && event.traceId.isNotEmpty,
        ),
        isTrue,
      );
    },
  );
}
