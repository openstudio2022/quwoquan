// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/integration/external_integration/connector_connection/adapters/connector_management_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../support/assistant_remote_test_support.dart';

void main() {
  test(
    'Connector management uses generated contracts and redacted views',
    () async {
      final executor = _RecordingConnectorExecutor(<String, Object?>{
        AppCloudOperationIds
                .integrationConnectorDefinitionListConnectorDefinitions:
            <String, Object?>{
              'items': <Object?>[_definitionWire()],
            },
        AppCloudOperationIds
                .integrationConnectorConnectionListConnectorConnections:
            <String, Object?>{
              'items': <Object?>[_connectionWire()],
            },
        AppCloudOperationIds
                .integrationConnectorInvocationListConnectorInvocations:
            <String, Object?>{
              'items': <Object?>[_invocationWire()],
            },
        AppCloudOperationIds
                .integrationConnectorConnectionRevokeConnectorConnection:
            <String, Object?>{
              'connection': _connectionWire(status: 'revoked', revision: 4),
              'replayed': false,
            },
      });
      final adapter = RemoteConnectorManagementFacet(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: (clientPageId, {idempotencyKey}) =>
            CloudOperationInvocationContext(
              surfaceId: AppUiSurfaces.assistantSkills.id,
              routeId: AppUiSurfaces.assistantSkills.routeId,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
              actor: const CloudOperationActorContext(
                accountId: 'connector-test-account',
                personaId: 'connector-test-persona',
              ),
            ),
      );

      final definitions = await adapter.listConnectorDefinitions(
        capability: 'calendar.event.create',
      );
      final connections = await adapter.listConnectorConnections();
      final invocations = await adapter.listConnectorInvocations(
        connectionId: 'connection_calendar',
      );
      final revoked = await adapter.revokeConnectorConnection(
        connectionId: 'connection_calendar',
        expectedRevision: 3,
        idempotencyKey: 'connector-revoke-idempotency',
      );

      expect(definitions.single.displayName, '系统日历');
      expect(connections.single.connectionId, 'connection_calendar');
      expect(invocations.single.status, ConnectorInvocationStatus.completed);
      expect(revoked.status, ConnectorConnectionStatus.revoked);
      expect(
        executor.records.map((record) => record.operation.pathTemplate),
        <String>[
          '/integrations/connectors',
          '/integrations/connections',
          '/integrations/invocations',
          '/integrations/connections/{connectionId}/revoke',
        ],
      );
      expect(executor.records[0].payload.queryParameters, <String, String>{
        'capability': 'calendar.event.create',
        'limit': '64',
      });
      expect(executor.records[2].payload.queryParameters, <String, String>{
        'connectionId': 'connection_calendar',
        'limit': '32',
      });
      expect(
        executor.records[3].context.idempotencyKey,
        'connector-revoke-idempotency',
      );
      expect(executor.records[3].payload.pathParameters, <String, String>{
        'connectionId': 'connection_calendar',
      });
      expect(executor.records[3].payload.body, <String, Object?>{
        'expectedRevision': 3,
      });
    },
  );

  test(
    'Commercial block remains release evidence and does not suppress Remote evidence',
    () async {
      var requestCount = 0;
      final httpClient = CloudHttpClient(
        client: MockClient((request) async {
          requestCount += 1;
          return http.Response(
            jsonEncode(<String, Object?>{'items': <Object?>[]}),
            200,
            request: request,
            headers: const <String, String>{'content-type': 'application/json'},
          );
        }),
        authTokenProvider: const _ConnectorAuthTokenProvider(),
      );
      final adapter = RemoteConnectorManagementFacet(
        client: buildAssistantRemoteTestOperationClient(httpClient),
        invocationContext: (clientPageId, {idempotencyKey}) =>
            CloudOperationInvocationContext(
              surfaceId: AppUiSurfaces.assistantSkills.id,
              routeId: AppUiSurfaces.assistantSkills.routeId,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
              actor: const CloudOperationActorContext(
                accountId: 'connector-test-account',
                personaId: 'connector-test-persona',
              ),
            ),
      );

      expect(await adapter.listConnectorDefinitions(), isEmpty);
      expect(requestCount, 1);
    },
  );

  test('Connector views reject protected runtime fields', () {
    expect(
      () => decodeConnectorConnectionView(<String, Object?>{
        ..._connectionWire(),
        'credentialRef': 'protected://must-not-cross-app-wire',
      }),
      throwsFormatException,
    );
    expect(
      () => decodeConnectorInvocationView(<String, Object?>{
        ..._invocationWire(),
        'resultRef': 'protected://must-not-cross-app-wire',
      }),
      throwsFormatException,
    );
  });
}

Map<String, Object?> _definitionWire() => <String, Object?>{
  'connectorId': 'system_calendar',
  'displayName': '系统日历',
  'description': '用户确认后写入行程事件',
  'capabilities': <String>['calendar.event.create'],
  'authorizationMode': 'device_native',
  'confirmationPolicy': 'user_confirmation',
  'dataClassification': 'private',
  'supportedSurfaceKinds': <String>['personal'],
  'status': 'active',
  'releaseDigest': _sha256Digest(
    'system_calendar|active|calendar.event.create|personal',
  ),
  'publishedAt': '2026-08-02T08:00:00Z',
};

String _sha256Digest(String payload) =>
    'sha256:${sha256.convert(utf8.encode(payload))}';

Map<String, Object?> _connectionWire({
  String status = 'active',
  int revision = 3,
}) => <String, Object?>{
  'connectionId': 'connection_calendar',
  'connectorId': 'system_calendar',
  'grantedCapabilities': <String>['calendar.event.create'],
  'status': status,
  'freshnessAt': '2026-08-02T09:00:00Z',
  if (status == 'revoked') 'revokedAt': '2026-08-02T09:01:00Z',
  'revision': revision,
  'createdAt': '2026-08-01T08:00:00Z',
  'updatedAt': '2026-08-02T09:01:00Z',
};

Map<String, Object?> _invocationWire() => <String, Object?>{
  'invocationId': 'invocation_calendar',
  'connectionId': 'connection_calendar',
  'capability': 'calendar.event.create',
  'status': 'completed',
  'recoveryAction': 'none',
  'revision': 2,
  'createdAt': '2026-08-02T08:59:00Z',
  'updatedAt': '2026-08-02T09:00:00Z',
  'completedAt': '2026-08-02T09:00:00Z',
};

final class _ConnectorAuthTokenProvider implements CloudAuthTokenProvider {
  const _ConnectorAuthTokenProvider();

  @override
  Future<String?> getAccessToken() async => 'connector-test-token';
}

final class _ConnectorExecutionRecord {
  const _ConnectorExecutionRecord({
    required this.operation,
    required this.context,
    required this.payload,
  });

  final CloudOperationContract operation;
  final CloudOperationInvocationContext context;
  final CloudOperationRequestPayload payload;
}

final class _RecordingConnectorExecutor implements CloudOperationExecutor {
  _RecordingConnectorExecutor(this.responses);

  final Map<String, Object?> responses;
  final List<_ConnectorExecutionRecord> records = <_ConnectorExecutionRecord>[];

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    final payload = requestEncoder();
    records.add(
      _ConnectorExecutionRecord(
        operation: operation,
        context: context,
        payload: payload,
      ),
    );
    if (!responses.containsKey(operation.canonicalOperationId)) {
      throw StateError(
        'missing response for ${operation.canonicalOperationId}',
      );
    }
    return responseDecoder(responses[operation.canonicalOperationId]);
  }
}
