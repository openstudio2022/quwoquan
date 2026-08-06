import 'package:quwoquan_app/travel/travel/trip_membership/application/trip_membership_facet.dart';
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

/// 仅冻结 Travel command 需要的 canonical reference/version。Chat/Circle/Gathering
/// 的成员权威仍由服务端 Reader 校验，App 不把本地名单当授权。
final class TripMembershipCoordinator {
  TripMembershipCoordinator(this._facet, this._idempotencyKeyFactory);

  final TripMembershipFacet _facet;
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
    if (normalizedTripId.isEmpty ||
        normalizedPersonaId.isEmpty ||
        sourceVersion <= 0) {
      throw ArgumentError('Canonical identity and source version are required');
    }
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

  String _nextKey(String scope) {
    final key = _idempotencyKeyFactory(scope).trim();
    if (key.isEmpty) {
      throw StateError('Trip membership idempotency key must not be blank');
    }
    return key;
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
