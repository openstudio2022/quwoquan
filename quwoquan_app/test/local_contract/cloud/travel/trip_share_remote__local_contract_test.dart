// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-shared-timeline/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_share_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'create share snapshot keeps canonical source digest and intent key',
    () async {
      final executor = _RecordingExecutor();
      final facet = RemoteTripShareFacet(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: _context,
      );

      final result = await facet.createSnapshot(
        CreateTripShareSnapshotRequest(
          tripId: 'trip-1',
          sourceRevisionId: 'revision-3',
          sourceDigest: 'sha256:timeline',
          scope: TripShareSnapshotScope.day,
          dayIndex: 1,
          momentIds: const <String>['moment-1'],
          visibility: TripShareSnapshotVisibility.public,
        ),
        idempotencyKey: 'share-intent-1',
      );

      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.travelTripShareSnapshotCreateTripShareSnapshot,
      );
      expect(executor.context?.surfaceId, AppUiSurfaces.travelShare.id);
      expect(executor.context?.idempotencyKey, 'share-intent-1');
      expect(executor.body, containsPair('sourceDigest', 'sha256:timeline'));
      expect(result.visibility, TripShareSnapshotVisibility.public);
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

final class _RecordingExecutor implements CloudOperationExecutor {
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
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
    body = requestEncoder().body;
    return responseDecoder(_shareWire());
  }
}

Map<String, Object?> _shareWire() => <String, Object?>{
  'id': 'snapshot-1',
  'version': 1,
  'tripId': 'trip-1',
  'sourceRevisionId': 'revision-3',
  'sourceRevisionNumber': 3,
  'sourceDigest': 'sha256:timeline',
  'scope': 'day',
  'dayIndex': 1,
  'momentIds': <Object?>['moment-1'],
  'visibility': 'public',
  'privacyPolicyDigest': 'sha256:privacy',
  'items': <Object?>[],
  'moments': <Object?>[],
  'contentLinks': <Object?>[],
  'routeStops': <Object?>[],
  'createdByPersonaId': 'persona-1',
  'status': 'active',
  'createdAt': '2026-08-02T10:00:00Z',
};
