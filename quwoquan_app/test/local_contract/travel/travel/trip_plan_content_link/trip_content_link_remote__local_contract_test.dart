// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-moment-content-link/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/travel/travel/trip_plan_content_link/adapters/trip_content_link_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'content link put/remove use timeline typed paths bodies and keys',
    () async {
      final executor = _ContentLinkExecutor();
      final facet = RemoteTripContentLinkFacet(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: _context,
      );

      await facet.put(
        PutTripPlanContentLinkRequest(
          tripId: 'trip-1',
          postId: 'post-1',
          expectedVersion: 0,
          revisionNumber: 3,
          targetKind: TripPlanContentLinkTargetKind.item,
          dayIndex: 1,
          itemId: 'item-1',
          visibility: TripPlanContentLinkVisibility.tripMembers,
          sourceVersion: 7,
        ),
        idempotencyKey: 'put-intent-1',
      );
      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.travelTripPlanContentLinkPutTripPlanContentLink,
      );
      expect(executor.context?.surfaceId, AppUiSurfaces.travelTimeline.id);
      expect(executor.context?.idempotencyKey, 'put-intent-1');
      expect(executor.pathParameters, <String, String>{
        'tripId': 'trip-1',
        'postId': 'post-1',
      });
      expect(executor.body, containsPair('revisionNumber', 3));
      expect(executor.body, containsPair('targetKind', 'item'));
      expect(executor.body, containsPair('itemId', 'item-1'));
      expect(executor.body, containsPair('sourceVersion', 7));

      await facet.remove(
        RemoveTripPlanContentLinkRequest(
          tripId: 'trip-1',
          postId: 'post-1',
          expectedVersion: 2,
          reason: '行程已调整',
        ),
        idempotencyKey: 'remove-intent-1',
      );
      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.travelTripPlanContentLinkRemoveTripPlanContentLink,
      );
      expect(executor.context?.surfaceId, AppUiSurfaces.travelTimeline.id);
      expect(executor.context?.idempotencyKey, 'remove-intent-1');
      expect(executor.body, containsPair('expectedVersion', 2));
      expect(executor.body, containsPair('reason', '行程已调整'));
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

final class _ContentLinkExecutor implements CloudOperationExecutor {
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
    return responseDecoder(_contentLinkWire());
  }
}

Map<String, Object?> _contentLinkWire() => <String, Object?>{
  'linkId': 'link-1',
  'version': 2,
  'tripId': 'trip-1',
  'postId': 'post-1',
  'revisionNumber': 3,
  'targetKind': 'item',
  'dayIndex': 1,
  'itemId': 'item-1',
  'visibility': 'trip_members',
  'linkedByPersonaId': 'persona-1',
  'sourceVersion': 7,
  'status': 'active',
  'createdAt': '2026-08-02T10:00:00Z',
  'updatedAt': '2026-08-02T10:00:00Z',
};
