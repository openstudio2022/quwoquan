// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-guide-template-assignment/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_guide_assignment_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'guide transition uses typed task path, CAS body and intent key',
    () async {
      final executor = _GuideExecutor();
      final facet = RemoteTripGuideAssignmentFacet(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: _context,
      );

      final result = await facet.transition(
        TransitionTripGuideAssignmentRequest(
          tripId: 'trip-1',
          taskKey: 'collection-1',
          expectedVersion: 2,
          targetStatus: TripGuideAssignmentStatus.accepted,
        ),
        idempotencyKey: 'guide-intent-1',
      );

      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds
            .travelTripGuideAssignmentTransitionTripGuideAssignment,
      );
      expect(executor.context?.surfaceId, AppUiSurfaces.travelTimeline.id);
      expect(executor.context?.idempotencyKey, 'guide-intent-1');
      expect(executor.pathParameters, <String, String>{
        'tripId': 'trip-1',
        'taskKey': 'collection-1',
      });
      expect(executor.body, <String, Object?>{
        'expectedVersion': 2,
        'targetStatus': 'accepted',
      });
      expect(result.status, TripGuideAssignmentStatus.accepted);
    },
  );
}

CloudOperationInvocationContext _context(
  AppUiSurface surface,
  String clientPageId, {
  String? idempotencyKey,
}) {
  return CloudOperationInvocationContext(
    surfaceId: surface.id,
    routeId: surface.routeId,
    clientPageId: clientPageId,
    idempotencyKey: idempotencyKey,
    actor: const CloudOperationActorContext(
      accountId: 'account-1',
      personaId: 'persona-guide',
    ),
  );
}

final class _GuideExecutor implements CloudOperationExecutor {
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
      'id': 'assignment-1',
      'version': 3,
      'tripId': 'trip-1',
      'taskKey': 'collection-1',
      'assigneePersonaId': 'persona-guide',
      'role': 'licensed_guide',
      'taskKind': 'collection',
      'title': '集合与出发说明',
      'sourceRevisionNumber': 3,
      'attributionKind': 'professional_commentary',
      'attributionPersonaId': 'persona-guide',
      'publicQualificationPersonaId': 'persona-guide',
      'status': 'accepted',
      'createdByPersonaId': 'persona-organizer',
      'createdAt': '2026-08-02T10:00:00Z',
      'updatedAt': '2026-08-02T10:00:00Z',
    });
  }
}
