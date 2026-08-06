import 'package:quwoquan_app/travel/travel/trip_plan_placement/application/trip_plan_placement_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class TripPlacementPutIntent {
  const TripPlacementPutIntent(this.request, this.idempotencyKey);

  final PutTripPlanPlacementRequest request;
  final String idempotencyKey;
}

final class TripPlacementRemovalIntent {
  const TripPlacementRemovalIntent(this.request, this.idempotencyKey);

  final RemoveTripPlanPlacementRequest request;
  final String idempotencyKey;
}

/// 仅冻结 Travel command 需要的 canonical surface reference/version；挂载授权仍由
/// 服务端 Reader 校验。
final class TripPlanPlacementCoordinator {
  TripPlanPlacementCoordinator(this._facet, this._idempotencyKeyFactory);

  final TripPlanPlacementFacet _facet;
  final String Function(String scope) _idempotencyKeyFactory;

  TripPlacementPutIntent preparePlacement({
    required String tripId,
    required TripPlacementSurfaceKind surfaceKind,
    required String surfaceId,
    required int sourceVersion,
    TripPlanPlacementSlice? current,
  }) {
    final normalizedTripId = tripId.trim();
    final normalizedSurfaceId = surfaceId.trim();
    if (normalizedTripId.isEmpty ||
        normalizedSurfaceId.isEmpty ||
        sourceVersion <= 0) {
      throw ArgumentError('Canonical identity and source version are required');
    }
    if (current != null &&
        (current.tripId != normalizedTripId ||
            current.surfaceKind != surfaceKind ||
            current.surfaceId != normalizedSurfaceId)) {
      throw ArgumentError('Current placement does not own the target');
    }
    return TripPlacementPutIntent(
      PutTripPlanPlacementRequest(
        tripId: normalizedTripId,
        surfaceKind: surfaceKind,
        surfaceId: normalizedSurfaceId,
        sourceVersion: sourceVersion,
        expectedVersion: current?.version ?? 0,
      ),
      _nextKey('placement-put'),
    );
  }

  TripPlacementRemovalIntent preparePlacementRemoval({
    required TripPlanPlacementSlice current,
    required int sourceVersion,
  }) {
    if (current.tripId.trim().isEmpty ||
        current.surfaceId.trim().isEmpty ||
        current.version <= 0 ||
        sourceVersion <= 0 ||
        current.status != TripPlanPlacementStatus.active) {
      throw ArgumentError('Active placement and source version are required');
    }
    return TripPlacementRemovalIntent(
      RemoveTripPlanPlacementRequest(
        tripId: current.tripId,
        surfaceKind: current.surfaceKind,
        surfaceId: current.surfaceId,
        sourceVersion: sourceVersion,
        expectedVersion: current.version,
      ),
      _nextKey('placement-remove'),
    );
  }

  Future<TripPlanPlacementSlice> putPlacement(TripPlacementPutIntent intent) =>
      _facet.putPlacement(
        intent.request,
        idempotencyKey: intent.idempotencyKey,
      );

  Future<TripPlanPlacementSlice> removePlacement(
    TripPlacementRemovalIntent intent,
  ) => _facet.removePlacement(
    intent.request,
    idempotencyKey: intent.idempotencyKey,
  );

  String _nextKey(String scope) {
    final key = _idempotencyKeyFactory(scope).trim();
    if (key.isEmpty) {
      throw StateError('Trip placement idempotency key must not be blank');
    }
    return key;
  }
}
