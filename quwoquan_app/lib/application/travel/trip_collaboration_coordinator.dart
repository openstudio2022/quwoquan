import 'package:quwoquan_app/application/travel/trip_collaboration_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class TripMembershipPutIntent {
  const TripMembershipPutIntent(this.request, this.idempotencyKey);

  final PutTripMembershipRequest request;
  final String idempotencyKey;
}

final class TripMembershipDepartureIntent {
  const TripMembershipDepartureIntent(this.request, this.idempotencyKey);

  final DepartTripMembershipRequest request;
  final String idempotencyKey;
}

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

/// 仅冻结 Travel command 需要的 canonical reference/version。Chat/Circle/Gathering
/// 的成员权威仍由服务端 Reader 校验，App 不把本地名单当授权。
final class TripCollaborationCoordinator {
  TripCollaborationCoordinator(this._facet, this._idempotencyKeyFactory);

  final TripCollaborationFacet _facet;
  final String Function(String scope) _idempotencyKeyFactory;

  TripMembershipPutIntent prepareMembership({
    required String tripId,
    required String personaId,
    required TripMembershipRole role,
    required TripMembershipSourceKind sourceKind,
    required int sourceVersion,
    TripMembershipSourceRef? sourceObjectRef,
    TripMembershipSlice? current,
  }) {
    final normalizedTripId = tripId.trim();
    final normalizedPersonaId = personaId.trim();
    _validateIdentity(normalizedTripId, normalizedPersonaId, sourceVersion);
    if (current != null &&
        (current.tripId != normalizedTripId ||
            current.personaId != normalizedPersonaId)) {
      throw ArgumentError('Current membership does not own the target');
    }
    _validateMembershipSource(sourceKind, sourceObjectRef);
    return TripMembershipPutIntent(
      PutTripMembershipRequest(
        tripId: normalizedTripId,
        personaId: normalizedPersonaId,
        role: role,
        sourceKind: sourceKind,
        sourceObjectRef: sourceObjectRef,
        sourceVersion: sourceVersion,
        expectedVersion: current?.version ?? 0,
      ),
      _nextKey('membership-put'),
    );
  }

  TripMembershipDepartureIntent prepareDeparture({
    required TripMembershipSlice current,
    required String reason,
  }) {
    final normalizedReason = reason.trim();
    if (current.tripId.trim().isEmpty ||
        current.personaId.trim().isEmpty ||
        current.version <= 0 ||
        current.state != TripMembershipState.active ||
        normalizedReason.isEmpty) {
      throw ArgumentError('Active membership and reason are required');
    }
    return TripMembershipDepartureIntent(
      DepartTripMembershipRequest(
        tripId: current.tripId,
        personaId: current.personaId,
        expectedVersion: current.version,
        reason: normalizedReason,
      ),
      _nextKey('membership-depart'),
    );
  }

  TripPlacementPutIntent preparePlacement({
    required String tripId,
    required TripPlacementSurfaceKind surfaceKind,
    required String surfaceId,
    required int sourceVersion,
    TripPlanPlacementSlice? current,
  }) {
    final normalizedTripId = tripId.trim();
    final normalizedSurfaceId = surfaceId.trim();
    _validateIdentity(normalizedTripId, normalizedSurfaceId, sourceVersion);
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

  Future<TripMembershipSlice> putMembership(TripMembershipPutIntent intent) =>
      _facet.putMembership(
        intent.request,
        idempotencyKey: intent.idempotencyKey,
      );

  Future<TripMembershipSlice> departMembership(
    TripMembershipDepartureIntent intent,
  ) => _facet.departMembership(
    intent.request,
    idempotencyKey: intent.idempotencyKey,
  );

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
      throw StateError('Trip collaboration idempotency key must not be blank');
    }
    return key;
  }
}

void _validateIdentity(String ownerId, String targetId, int sourceVersion) {
  if (ownerId.isEmpty || targetId.isEmpty || sourceVersion <= 0) {
    throw ArgumentError('Canonical identity and source version are required');
  }
}

void _validateMembershipSource(
  TripMembershipSourceKind sourceKind,
  TripMembershipSourceRef? sourceRef,
) {
  if (sourceKind == TripMembershipSourceKind.tripInvitation) {
    return;
  }
  if (sourceRef == null ||
      sourceRef.objectTypeRef.trim().isEmpty ||
      sourceRef.objectId.trim().isEmpty) {
    throw ArgumentError('Shared membership source reference is required');
  }
}
