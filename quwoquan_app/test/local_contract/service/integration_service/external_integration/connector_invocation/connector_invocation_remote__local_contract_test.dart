// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
// readiness_case: connector_invocation_get_connector_invocation_app_local
// readiness_case: connector_invocation_list_connector_invocations_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/connector_invocation/adapters/connector_invocation_remote.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('Invocation list/get 各自只走 canonical generated operation', () async {
    final executor = _InvocationExecutor();
    final reader = RemoteConnectorInvocationReader(
      client: GeneratedCloudOperationClient(executor),
      invocationContext: (clientPageId) => CloudOperationInvocationContext(
        surfaceId: AppUiSurfaces.assistantSkills.id,
        routeId: AppUiSurfaces.assistantSkills.routeId,
        clientPageId: clientPageId,
        actor: const CloudOperationActorContext(personaId: 'connector-reader'),
      ),
    );

    final listed = await reader.listConnectorInvocations(
      connectionId: 'connection-calendar',
      limit: 8,
    );
    final fetched = await reader.getConnectorInvocation(
      invocationId: 'invocation-calendar',
    );

    expect(listed.single.invocationId, 'invocation-calendar');
    expect(fetched.status, ConnectorInvocationStatus.completed);
    expect(executor.operationIds, <String>[
      AppCloudOperationIds
          .integrationConnectorInvocationListConnectorInvocations,
      AppCloudOperationIds.integrationConnectorInvocationGetConnectorInvocation,
    ]);
    expect(executor.payloads.first.queryParameters, <String, String>{
      'connectionId': 'connection-calendar',
      'limit': '8',
    });
    expect(executor.payloads.last.pathParameters, <String, String>{
      'invocationId': 'invocation-calendar',
    });
  });
}

final class _InvocationExecutor implements CloudOperationExecutor {
  final List<String> operationIds = <String>[];
  final List<CloudOperationRequestPayload> payloads =
      <CloudOperationRequestPayload>[];

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    operationIds.add(operation.canonicalOperationId);
    payloads.add(requestEncoder());
    final invocation = <String, Object?>{
      'invocationId': 'invocation-calendar',
      'connectionId': 'connection-calendar',
      'capability': 'calendar.event.create',
      'status': 'completed',
      'recoveryAction': 'none',
      'revision': 2,
      'createdAt': '2026-08-02T08:59:00Z',
      'updatedAt': '2026-08-02T09:00:00Z',
      'completedAt': '2026-08-02T09:00:00Z',
    };
    return responseDecoder(
      operation.canonicalOperationId ==
              AppCloudOperationIds
                  .integrationConnectorInvocationListConnectorInvocations
          ? <String, Object?>{
              'items': <Object?>[invocation],
            }
          : invocation,
    );
  }
}
