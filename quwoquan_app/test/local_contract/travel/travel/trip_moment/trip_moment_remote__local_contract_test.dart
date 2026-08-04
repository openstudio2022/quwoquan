// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-moment-content-link/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/travel/travel/trip_moment/adapters/trip_moment_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'moment create freezes typed target, body and idempotency context',
    () async {
      final executor = _MomentExecutor();
      final facet = RemoteTripMomentFacet(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: _context,
      );

      final result = await facet.create(
        CreateTripMomentRequest(
          tripId: 'trip-1',
          revisionNumber: 3,
          dayIndex: 1,
          itemId: 'item-1',
          kind: TripMomentKind.text,
          inlineText: '飞来峰傍晚人少',
          capturedAt: DateTime.utc(2026, 8, 2, 10),
          visibility: TripMomentVisibility.tripMembers,
          assignmentStatus: TripMomentAssignmentStatus.confirmed,
          sourceVersion: 0,
        ),
        idempotencyKey: 'moment-intent-1',
      );

      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.travelTripMomentCreateTripMoment,
      );
      expect(executor.context?.surfaceId, AppUiSurfaces.travelTimeline.id);
      expect(executor.context?.idempotencyKey, 'moment-intent-1');
      expect(executor.pathParameters, <String, String>{'tripId': 'trip-1'});
      expect(executor.body, containsPair('revisionNumber', 3));
      expect(executor.body, containsPair('itemId', 'item-1'));
      expect(executor.body, containsPair('visibility', 'trip_members'));
      expect(result.momentId, 'moment-1');
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
      personaId: 'persona-1',
    ),
  );
}

final class _MomentExecutor implements CloudOperationExecutor {
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
    return responseDecoder(_momentWire());
  }
}

Map<String, Object?> _momentWire() => <String, Object?>{
  'momentId': 'moment-1',
  'version': 1,
  'tripId': 'trip-1',
  'revisionNumber': 3,
  'dayIndex': 1,
  'itemId': 'item-1',
  'kind': 'text',
  'inlineText': '飞来峰傍晚人少',
  'capturedAt': '2026-08-02T10:00:00Z',
  'visibility': 'trip_members',
  'assignmentStatus': 'confirmed',
  'attributionPersonaId': 'persona-1',
  'sourceVersion': 0,
  'status': 'active',
  'createdAt': '2026-08-02T10:00:00Z',
  'updatedAt': '2026-08-02T10:00:00Z',
};
