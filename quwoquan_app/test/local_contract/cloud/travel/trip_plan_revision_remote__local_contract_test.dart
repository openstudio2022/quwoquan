// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-plan-revision/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_plan_revision_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'revise and transition use timeline surface, CAS and frozen keys',
    () async {
      final executor = _RevisionExecutor();
      final facet = RemoteTripPlanRevisionFacet(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: _context,
      );

      await facet.revise(
        ReviseTripPlanCommand(
          tripId: 'trip-1',
          expectedRevisionNumber: 3,
          changeReason: '调整餐饮顺序',
          severity: TripRevisionSeverity.important,
          items: const <TripPlanItemInput>[],
        ),
        idempotencyKey: 'revision-intent-1',
      );
      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.travelTripPlanReviseTripPlan,
      );
      expect(executor.context?.surfaceId, AppUiSurfaces.travelTimeline.id);
      expect(executor.context?.idempotencyKey, 'revision-intent-1');
      expect(executor.pathParameters, <String, String>{'tripId': 'trip-1'});
      expect(executor.body, containsPair('expectedRevisionNumber', 3));

      await facet.transition(
        TransitionTripPlanCommand(
          tripId: 'trip-1',
          expectedRevisionNumber: 4,
          targetStatus: TripPlanStatus.active,
        ),
        idempotencyKey: 'transition-intent-1',
      );
      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.travelTripPlanTransitionTripPlan,
      );
      expect(executor.context?.idempotencyKey, 'transition-intent-1');
      expect(executor.body, containsPair('targetStatus', 'active'));
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

final class _RevisionExecutor implements CloudOperationExecutor {
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
  Map<String, String> pathParameters = const <String, String>{};
  Object? body;

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
    pathParameters = request.pathParameters;
    body = request.body;
    return responseDecoder(<String, Object?>{
      'tripId': 'trip-1',
      'version': 4,
      'currentRevisionId': 'revision-4',
      'currentRevisionNumber': 4,
      'status': 'planning',
      'idempotentReplay': false,
    });
  }
}
