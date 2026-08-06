// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
// readiness_case: connector_definition_get_connector_definition_app_local
// readiness_case: connector_definition_list_connector_definitions_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/connector_definition/adapters/connector_definition_remote.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('Definition list/get 各自只走 canonical generated operation', () async {
    final executor = _DefinitionExecutor();
    final reader = RemoteConnectorDefinitionReader(
      client: GeneratedCloudOperationClient(executor),
      invocationContext: (clientPageId) => CloudOperationInvocationContext(
        surfaceId: AppUiSurfaces.assistantSkills.id,
        routeId: AppUiSurfaces.assistantSkills.routeId,
        clientPageId: clientPageId,
        actor: const CloudOperationActorContext(personaId: 'connector-reader'),
      ),
    );

    final listed = await reader.listConnectorDefinitions(
      capability: 'calendar.event.create',
      limit: 12,
    );
    final fetched = await reader.getConnectorDefinition(
      connectorId: 'system_calendar',
    );

    expect(listed.single.connectorId, 'system_calendar');
    expect(fetched.connectorId, 'system_calendar');
    expect(executor.operationIds, <String>[
      AppCloudOperationIds
          .integrationConnectorDefinitionListConnectorDefinitions,
      AppCloudOperationIds.integrationConnectorDefinitionGetConnectorDefinition,
    ]);
    expect(executor.payloads.first.queryParameters, <String, String>{
      'capability': 'calendar.event.create',
      'limit': '12',
    });
    expect(executor.payloads.last.pathParameters, <String, String>{
      'connectorId': 'system_calendar',
    });
  });
}

final class _DefinitionExecutor implements CloudOperationExecutor {
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
    final definition = <String, Object?>{
      'connectorId': 'system_calendar',
      'displayName': '系统日历',
      'description': '用户确认后写入行程事件',
      'capabilities': <String>['calendar.event.create'],
      'authorizationMode': 'device_native',
      'confirmationPolicy': 'user_confirmation',
      'dataClassification': 'private',
      'supportedSurfaceKinds': <String>['personal'],
      'status': 'active',
      'releaseDigest':
          'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'publishedAt': '2026-08-02T08:00:00Z',
    };
    return responseDecoder(
      operation.canonicalOperationId ==
              AppCloudOperationIds
                  .integrationConnectorDefinitionListConnectorDefinitions
          ? <String, Object?>{
              'items': <Object?>[definition],
            }
          : definition,
    );
  }
}
