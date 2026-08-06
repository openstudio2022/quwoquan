import 'package:quwoquan_app/service/circle_service/circle_management/gathering/domain/gathering_models.dart';

enum GatheringJourneyCapabilityKind { plan, map, calendar, experience }

enum GatheringJourneyCapabilityAvailability {
  available,
  notConfigured,
  unsupported,
  permissionDenied,
  temporarilyUnavailable,
}

final class GatheringJourneyCapability {
  const GatheringJourneyCapability({
    required this.kind,
    required this.availability,
    required this.sourceVersion,
    required this.sourceDigest,
  });

  final GatheringJourneyCapabilityKind kind;
  final GatheringJourneyCapabilityAvailability availability;
  final int sourceVersion;
  final String sourceDigest;

  bool get isAvailable =>
      availability == GatheringJourneyCapabilityAvailability.available;
}

/// Board 只读取 Circle owner 签发的 capability 状态，不维护第二份挂载关系。
abstract interface class GatheringJourneyCapabilityQuery {
  Future<List<GatheringJourneyCapability>> listForGathering(String gatheringId);
}

enum GatheringJourneyParticipationRole {
  organizer,
  participant,
  leader,
  assistant,
  guide,
  localExpert,
}

enum GatheringJourneyParticipationState { active, departed }

final class GatheringJourneyParticipation {
  const GatheringJourneyParticipation({
    required this.gatheringId,
    required this.personaId,
    required this.role,
    required this.state,
    required this.version,
    required this.sourceVersion,
    this.sourceRef,
  });

  final String gatheringId;
  final String personaId;
  final GatheringJourneyParticipationRole role;
  final GatheringJourneyParticipationState state;
  final int version;
  final int sourceVersion;
  final GatheringCanonicalObjectRef? sourceRef;
}

final class PutGatheringJourneyParticipationInput {
  const PutGatheringJourneyParticipationInput({
    required this.idempotencyKey,
    required this.gatheringId,
    required this.personaId,
    required this.role,
    required this.sourceVersion,
    required this.expectedVersion,
    this.sourceRef,
  });

  final String idempotencyKey;
  final String gatheringId;
  final String personaId;
  final GatheringJourneyParticipationRole role;
  final int sourceVersion;
  final int expectedVersion;
  final GatheringCanonicalObjectRef? sourceRef;
}

final class DepartGatheringJourneyParticipationInput {
  const DepartGatheringJourneyParticipationInput({
    required this.idempotencyKey,
    required this.gatheringId,
    required this.personaId,
    required this.expectedVersion,
    required this.reason,
  });

  final String idempotencyKey;
  final String gatheringId;
  final String personaId;
  final int expectedVersion;
  final String reason;
}

abstract interface class GatheringJourneyParticipationWriter {
  Future<GatheringJourneyParticipation> put(
    PutGatheringJourneyParticipationInput input,
  );

  Future<GatheringJourneyParticipation> depart(
    DepartGatheringJourneyParticipationInput input,
  );
}

enum GatheringJourneyPlacementState { active, removed }

final class GatheringJourneyPlacement {
  const GatheringJourneyPlacement({
    required this.gatheringId,
    required this.capabilityKind,
    required this.surfaceRef,
    required this.version,
    required this.sourceVersion,
    required this.state,
  });

  final String gatheringId;
  final GatheringJourneyCapabilityKind capabilityKind;
  final GatheringCanonicalObjectRef surfaceRef;
  final int version;
  final int sourceVersion;
  final GatheringJourneyPlacementState state;
}

final class PutGatheringJourneyPlacementInput {
  const PutGatheringJourneyPlacementInput({
    required this.idempotencyKey,
    required this.gatheringId,
    required this.capabilityKind,
    required this.surfaceRef,
    required this.sourceVersion,
    required this.expectedVersion,
  });

  final String idempotencyKey;
  final String gatheringId;
  final GatheringJourneyCapabilityKind capabilityKind;
  final GatheringCanonicalObjectRef surfaceRef;
  final int sourceVersion;
  final int expectedVersion;
}

final class RemoveGatheringJourneyPlacementInput {
  const RemoveGatheringJourneyPlacementInput({
    required this.idempotencyKey,
    required this.gatheringId,
    required this.capabilityKind,
    required this.surfaceRef,
    required this.sourceVersion,
    required this.expectedVersion,
  });

  final String idempotencyKey;
  final String gatheringId;
  final GatheringJourneyCapabilityKind capabilityKind;
  final GatheringCanonicalObjectRef surfaceRef;
  final int sourceVersion;
  final int expectedVersion;
}

abstract interface class GatheringJourneyPlacementQuery {
  Future<List<GatheringJourneyPlacement>> listForSurface(
    GatheringCanonicalObjectRef surfaceRef,
  );
}

abstract interface class GatheringJourneyPlacementWriter {
  Future<GatheringJourneyPlacement> put(
    PutGatheringJourneyPlacementInput input,
  );

  Future<GatheringJourneyPlacement> remove(
    RemoveGatheringJourneyPlacementInput input,
  );
}
