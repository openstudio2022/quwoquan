import 'package:quwoquan_app/service/circle_service/circle_management/gathering/domain/gathering_models.dart';

enum GatheringJourneyExperienceKind {
  photo,
  video,
  voice,
  text,
  checkIn,
  postReference,
}

enum GatheringJourneyExperienceVisibility { participants, public }

final class GatheringJourneyExperienceTarget {
  const GatheringJourneyExperienceTarget({
    required this.planItemId,
    this.dayIndex,
  });

  final String planItemId;
  final int? dayIndex;
}

/// 用户确认后写入 Circle owner 的 Experience reference。
final class GatheringJourneyExperienceInput {
  const GatheringJourneyExperienceInput({
    required this.idempotencyKey,
    required this.gatheringId,
    required this.kind,
    required this.sourceRef,
    required this.sourceVersion,
    required this.sourceDigest,
    required this.visibility,
    this.target,
    this.capturedAt,
  });

  final String idempotencyKey;
  final String gatheringId;
  final GatheringJourneyExperienceKind kind;
  final GatheringCanonicalObjectRef sourceRef;
  final int sourceVersion;
  final String sourceDigest;
  final GatheringJourneyExperienceVisibility visibility;
  final GatheringJourneyExperienceTarget? target;
  final DateTime? capturedAt;
}

final class GatheringJourneyExperience {
  const GatheringJourneyExperience({
    required this.experienceId,
    required this.gatheringId,
    required this.version,
    required this.kind,
    required this.sourceRef,
    required this.sourceVersion,
    required this.sourceDigest,
    required this.visibility,
    required this.createdAt,
    this.target,
  });

  final String experienceId;
  final String gatheringId;
  final int version;
  final GatheringJourneyExperienceKind kind;
  final GatheringCanonicalObjectRef sourceRef;
  final int sourceVersion;
  final String sourceDigest;
  final GatheringJourneyExperienceVisibility visibility;
  final GatheringJourneyExperienceTarget? target;
  final DateTime createdAt;
}

final class RemoveGatheringJourneyExperienceInput {
  const RemoveGatheringJourneyExperienceInput({
    required this.idempotencyKey,
    required this.gatheringId,
    required this.experienceId,
    required this.expectedVersion,
    required this.reasonRef,
  });

  final String idempotencyKey;
  final String gatheringId;
  final String experienceId;
  final int expectedVersion;
  final String reasonRef;
}

abstract interface class GatheringJourneyExperienceWriter {
  Future<GatheringJourneyExperience> put(GatheringJourneyExperienceInput input);

  Future<void> remove(RemoveGatheringJourneyExperienceInput input);
}
