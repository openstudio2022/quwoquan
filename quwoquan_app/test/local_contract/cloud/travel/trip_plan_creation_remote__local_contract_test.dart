// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-plan-revision/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_plan_creation_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'direct and template create use typed operations and frozen keys',
    () async {
      final executor = _CreationExecutor();
      final facet = RemoteTripPlanCreationFacet(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: _context,
      );

      await facet.create(
        CreateTripPlanCommand(title: '西湖七日同行', items: const []),
        idempotencyKey: 'trip-create-1',
      );
      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.travelTripPlanCreateTripPlan,
      );
      expect(executor.context?.surfaceId, AppUiSurfaces.travelTrips.id);
      expect(executor.context?.idempotencyKey, 'trip-create-1');
      expect(executor.body, containsPair('title', '西湖七日同行'));
      expect(executor.body, containsPair('items', <Object?>[]));

      await facet.createFromTemplate(
        CreateTripPlanFromTemplateCommand(templateId: 'template-1'),
        idempotencyKey: 'template-create-1',
      );
      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.travelTripPlanCreateTripPlanFromTemplate,
      );
      expect(executor.context?.surfaceId, AppUiSurfaces.travelTemplates.id);
      expect(executor.context?.idempotencyKey, 'template-create-1');
      expect(executor.pathParameters, <String, String>{
        'templateId': 'template-1',
      });
    },
  );
}

CloudOperationInvocationContext _context(
  AppUiSurface surface,
  String clientPageId, {
  String? idempotencyKey,
}) => CloudOperationInvocationContext(
  surfaceId: surface.id,
  routeId: surface.routeId,
  clientPageId: clientPageId,
  idempotencyKey: idempotencyKey,
  actor: const CloudOperationActorContext(
    accountId: 'account-1',
    personaId: 'persona-1',
  ),
);

final class _CreationExecutor implements CloudOperationExecutor {
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
  Object? body;
  Map<String, String> pathParameters = const <String, String>{};

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    this.operation = operation;
    this.context = context;
    final request = requestEncoder();
    body = request.body;
    pathParameters = request.pathParameters;
    return responseDecoder(<String, Object?>{
      'tripId': 'trip-1',
      'version': 1,
      'currentRevisionId': 'revision-1',
      'currentRevisionNumber': 1,
      'status': 'planning',
      'idempotentReplay': false,
    });
  }
}
